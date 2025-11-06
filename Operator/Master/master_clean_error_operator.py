# Operator/Master/master_clean_error_operator.py
import bpy
from bpy.types import Operator, Context

LOG_PREFIX = "[CleanError]"

# ------------------------------ Snapshot-Helfer ------------------------------

def _find_clip_editor_override() -> tuple[dict | None, bpy.types.MovieClip | None, str]:
    """Sucht einen gültigen CLIP_EDITOR und baut ein Override. Gibt (override, clip, debug_str) zurück."""
    wm = bpy.context.window_manager
    for window in wm.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type != 'CLIP_EDITOR':
                continue
            space = area.spaces.active
            if not (space and space.clip):
                continue
            # WINDOW-Region erzwingen
            region_window = None
            for r in area.regions:
                if r.type == 'WINDOW':
                    region_window = r
                    break
            if not region_window:
                continue

            override = {
                "window": window,
                "screen": screen,
                "area": area,
                "region": region_window,
                "space_data": space,
                "edit_movieclip": space.clip,
            }
            dbg = (f"win={getattr(window, 'as_pointer', lambda: None)()}, "
                   f"scr='{screen.name}', area=CLIP_EDITOR, region=WINDOW, "
                   f"clip='{space.clip.name}'")
            return override, space.clip, dbg
    return None, None, "kein CLIP_EDITOR mit aktivem Clip gefunden"


def _track_segment_stats(track: bpy.types.MovieTrackingTrack) -> tuple[int, int, int]:
    """
    Liefert (marker_count, first_frame, last_frame) für *sichtbare* Marker des Tracks.
    Hinweis: Wir betrachten alle Marker-Keys; CleanError löscht ggf. Segmente oder ganze Tracks.
    """
    frames = []
    try:
        for m in track.markers:
            # 'mute' auf Marker-Ebene existiert hier nicht; wir zählen alle Marker des Tracks
            # (Tracks können über is_muted stumm sein, aber Marker bleiben als Historie vorhanden)
            frames.append(int(m.frame))
    except Exception:
        pass
    if not frames:
        return 0, -1, -1
    frames.sort()
    return len(frames), frames[0], frames[-1]


def _snapshot_tracks(clip: bpy.types.MovieClip) -> dict:
    """
    Snapshot der Track-Landschaft:
    { name: {
        'is_muted': bool,
        'marker_count': int,
        'first_frame': int,
        'last_frame': int,
        'segment_len': int  # heuristisch: last-first+1 (wenn marker vorhanden)
    } }
    """
    snap = {}
    for t in clip.tracking.tracks:
        is_muted = False
        try:
            is_muted = bool(getattr(t, "is_muted", False))
        except Exception:
            is_muted = False

        mc, f0, f1 = _track_segment_stats(t)
        seg_len = (f1 - f0 + 1) if (mc > 0 and f0 >= 0 and f1 >= 0) else 0
        snap[t.name] = {
            "is_muted": is_muted,
            "marker_count": mc,
            "first_frame": f0,
            "last_frame": f1,
            "segment_len": seg_len,
        }
    return snap


def _diff_snapshots(before: dict, after: dict) -> dict:
    """
    Ermittelt Unterschiede zwischen Snapshots.
    Return:
    {
      'deleted': [names...],          # im After nicht mehr vorhanden
      'new': [names...],              # neu entstanden (sollte bei CleanError selten vorkommen)
      'muted_now': [names...],        # vorher aktiv -> jetzt muted
      'unmuted_now': [names...],      # vorher muted -> jetzt aktiv
      'shrunk': [ (name, before_len, after_len) ... ],   # Segmentlänge kleiner geworden
      'reduced_markers': [ (name, before_cnt, after_cnt) ... ],  # Markeranzahl reduziert
    }
    """
    bnames = set(before.keys())
    anames = set(after.keys())

    deleted = sorted(list(bnames - anames))
    new = sorted(list(anames - bnames))

    muted_now = []
    unmuted_now = []
    shrunk = []
    reduced_markers = []

    for name in sorted(bnames & anames):
        b = before[name]
        a = after[name]
        if (not b.get("is_muted", False)) and a.get("is_muted", False):
            muted_now.append(name)
        if b.get("is_muted", False) and (not a.get("is_muted", False)):
            unmuted_now.append(name)

        bl = int(b.get("segment_len", 0))
        al = int(a.get("segment_len", 0))
        if al < bl:
            shrunk.append((name, bl, al))

        bc = int(b.get("marker_count", 0))
        ac = int(a.get("marker_count", 0))
        if ac < bc:
            reduced_markers.append((name, bc, ac))

    return {
        "deleted": deleted,
        "new": new,
        "muted_now": muted_now,
        "unmuted_now": unmuted_now,
        "shrunk": shrunk,
        "reduced_markers": reduced_markers,
    }


def _count_tracks(clip: bpy.types.MovieClip) -> tuple[int, int]:
    """Zählt Tracks: (gesamt, aktiv). Aktiv = nicht is_muted."""
    tracks = clip.tracking.tracks
    total = len(tracks)
    active = 0
    for t in tracks:
        try:
            if not getattr(t, "is_muted", False):
                active += 1
        except Exception:
            # Fallback: wenn Property fehlt, zählen wir als aktiv
            active += 1
    return total, active


def _print_sample(label: str, items: list, limit: int = 12):
    if not items:
        print(f"{LOG_PREFIX} {label}: (keine)")
        return
    head = items[:limit]
    tail_n = max(0, len(items) - len(head))
    if isinstance(head[0], (tuple, list)):
        # Für Paare/Tripel
        sample = ", ".join(str(x) for x in head)
    else:
        sample = ", ".join(head)
    suffix = "" if tail_n == 0 else f" … (+{tail_n} weitere)"
    print(f"{LOG_PREFIX} {label}: {sample}{suffix}")


# ------------------------------ Operator ------------------------------

class KAISERLICHTRACKER_OT_clean_error_operator(Operator):
    """Führt bpy.ops.clip.clean_error() mit sicherem Kontext aus (Deep Logs)"""
    bl_idname = "kaiserlich_tracker.clean_error_operator"
    bl_label = "Clean Error (Context Safe, Deep Logs)"
    bl_options = {'REGISTER', 'UNDO'}

    threshold: bpy.props.FloatProperty(
        name="Threshold",
        description="Reprojection Error Grenze für Cleanup",
        default=20.0,
        min=0.0,
        soft_max=100.0
    )

    action: bpy.props.EnumProperty(
        name="Action",
        description="Bereinigungsart",
        items=[
            ('SELECT', "Select", "Markiert fehlerhafte Tracks"),
            ('DELETE_TRACK', "Delete Track", "Löscht fehlerhafte Tracks"),
            ('DELETE_SEGMENTS', "Delete Segments", "Löscht fehlerhafte Segmente"),
        ],
        default='DELETE_TRACK'
    )

    def execute(self, context: Context):
        # --- Kontext ermitteln ---
        override, clip, dbg = _find_clip_editor_override()
        print(f"{LOG_PREFIX} Kontextsuche … {dbg}")
        if not override or not clip:
            self.report({'ERROR'}, "Kein aktiver Movie Clip im Clip-Editor gefunden.")
            print(f"{LOG_PREFIX} ❌ Abbruch: kein gültiger Clip-Kontext.")
            return {'CANCELLED'}

        # --- Vorher-Snapshot & Zahlen ---
        total_before, active_before = _count_tracks(clip)
        before_snap = _snapshot_tracks(clip)
        settings = clip.tracking.settings
        print(f"{LOG_PREFIX} Vorher: tracks_total={total_before}, tracks_active={active_before}, "
              f"clean_action='{settings.clean_action}', clean_error={settings.clean_error:.4f}")
        # kurze Stichprobe zu langen / stummen / leeren Tracks
        long_tracks = [n for n, v in before_snap.items() if v["segment_len"] >= 25]
        muted_tracks = [n for n, v in before_snap.items() if v["is_muted"]]
        empty_tracks = [n for n, v in before_snap.items() if v["marker_count"] == 0]
        _print_sample("Vorher: lange Tracks (seg_len>=25)", long_tracks)
        _print_sample("Vorher: stumme Tracks", muted_tracks)
        _print_sample("Vorher: leere Tracks (0 Marker)", empty_tracks)

        # --- Parameter setzen und loggen ---
        settings.clean_action = self.action
        settings.clean_error = float(self.threshold)
        print(f"{LOG_PREFIX} Setze Parameter: action='{self.action}', threshold={self.threshold:.4f}")

        # --- Operator aufrufen ---
        try:
            print(f"{LOG_PREFIX} Aufruf: bpy.ops.clip.clean_error(override, 'EXEC_DEFAULT')")
            bpy.ops.clip.clean_error(override, 'EXEC_DEFAULT')
        except TypeError as te:
            print(f"{LOG_PREFIX} ⚠️ TypeError: {te} → Fallback ohne zweiten Parameter")
            bpy.ops.clip.clean_error(override)
        except Exception as e:
            self.report({'ERROR'}, f"Clean Error fehlgeschlagen: {e}")
            print(f"{LOG_PREFIX} ❌ Exception beim Clean: {e!r}")
            return {'CANCELLED'}

        # --- Nachher-Snapshot & Zahlen ---
        after_snap = _snapshot_tracks(clip)
        total_after, active_after = _count_tracks(clip)
        delta_total = total_after - total_before
        delta_active = active_after - active_before
        print(f"{LOG_PREFIX} Nachher: tracks_total={total_after} ({delta_total:+d}), "
              f"tracks_active={active_after} ({delta_active:+d})")

        # --- Diff auswerten ---
        diff = _diff_snapshots(before_snap, after_snap)
        _print_sample("Gelöscht (nicht mehr vorhanden)", diff["deleted"])
        _print_sample("Neu hinzugekommen", diff["new"])
        _print_sample("Jetzt stumm (muted)", diff["muted_now"])
        _print_sample("Jetzt aktiv (entmutet)", diff["unmuted_now"])
        _print_sample("Segment kürzer (name, before_len, after_len)", diff["shrunk"])
        _print_sample("Marker reduziert (name, before_cnt, after_cnt)", diff["reduced_markers"])

        # --- Abschlussmeldung ---
        msg = f"Clean Error erfolgreich (action={self.action}, threshold={self.threshold:.2f})"
        self.report({'INFO'}, msg)
        print(f"{LOG_PREFIX} ✅ {msg}")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_clean_error_operator)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_clean_error_operator)

if __name__ == "__main__":
    register()
