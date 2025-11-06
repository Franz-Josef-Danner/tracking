# Operator/Master/master_clean_error_operator.py
import bpy
from bpy.types import Operator, Context

LOG_PREFIX = "[CleanError]"

def _find_clip_editor_override() -> tuple[dict | None, bpy.types.MovieClip | None, str]:
    """Sucht einen gültigen CLIP_EDITOR und baut ein Override.
    Gibt (override, clip, debug_str) zurück.
    """
    wm = bpy.context.window_manager
    for window in wm.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type != 'CLIP_EDITOR':
                continue
            space = area.spaces.active
            if not (space and space.clip):
                continue
            # WINDOW-Region erzwingen (nicht UI/TOOLS)
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

def _count_tracks(clip: bpy.types.MovieClip) -> tuple[int, int]:
    """Zählt Tracks: (gesamt, aktiv)."""
    tracks = clip.tracking.tracks
    total = len(tracks)
    active = sum(1 for t in tracks if not t.mute)
    return total, active

class KAISERLICHTRACKER_OT_clean_error_operator(Operator):
    """Führt bpy.ops.clip.clean_error() mit sicherem Kontext aus (mit Logs)"""
    bl_idname = "kaiserlich_tracker.clean_error_operator"
    bl_label = "Clean Error (Context Safe, Logged)"
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

        # --- Vorher-Zustand loggen ---
        total_before, active_before = _count_tracks(clip)
        settings = clip.tracking.settings
        print(f"{LOG_PREFIX} Vorher: tracks_total={total_before}, tracks_active={active_before}, "
              f"clean_action='{settings.clean_action}', clean_error={settings.clean_error:.4f}")

        # --- Parameter setzen und loggen ---
        settings.clean_action = self.action
        settings.clean_error = float(self.threshold)
        print(f"{LOG_PREFIX} Setze Parameter: action='{self.action}', threshold={self.threshold:.4f}")

        # --- Operator aufrufen (mit robustem Fallback bei Signatur-Divergenzen) ---
        try:
            # Primär: expliziter Execution Context
            print(f"{LOG_PREFIX} Aufruf: bpy.ops.clip.clean_error(override, 'EXEC_DEFAULT')")
            bpy.ops.clip.clean_error(override, 'EXEC_DEFAULT')
        except TypeError as te:
            # Blender 4.4 kann je nach Build „1-2 args execution context is supported“ werfen
            print(f"{LOG_PREFIX} ⚠️ TypeError: {te} → Fallback ohne zweiten Parameter")
            bpy.ops.clip.clean_error(override)
        except Exception as e:
            self.report({'ERROR'}, f"Clean Error fehlgeschlagen: {e}")
            print(f"{LOG_PREFIX} ❌ Exception beim Clean: {e!r}")
            return {'CANCELLED'}

        # --- Nachher-Zustand loggen ---
        total_after, active_after = _count_tracks(clip)
        delta_total = total_after - total_before
        delta_active = active_after - active_before
        print(f"{LOG_PREFIX} Nachher: tracks_total={total_after} ({delta_total:+d}), "
              f"tracks_active={active_after} ({delta_active:+d})")

        # Zusatz: kurze Auflistung betroffener Tracks, wenn DELETE_* gewählt
        if self.action in {'DELETE_TRACK', 'DELETE_SEGMENTS'}:
            # Heuristik: liste alle stummen (mute) oder kürzlich veränderten Tracks knapp auf
            # (Vollständige Diff-Verfolgung wäre aufwändiger; wir loggen hier einen Überblick)
            changed_names = [t.name for t in clip.tracking.tracks if t.mute]
            sample = ", ".join(changed_names[:10])
            more = "" if len(changed_names) <= 10 else f" … (+{len(changed_names)-10} weitere)"
            print(f"{LOG_PREFIX} Betroffene (mute) Tracks (sample): {sample}{more}")

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
