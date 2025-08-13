# refine_high_error.py
import bpy
from bpy.types import Operator
from bpy.props import BoolProperty, IntProperty, FloatProperty

__all__ = ("CLIP_OT_refine_on_high_error", "run_refine_on_high_error")


# --- Context Utilities --------------------------------------------------------

def _find_clip_window(context):
    win = context.window
    if not win or not getattr(win, "screen", None):
        return None, None, None
    for area in win.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return area, region, area.spaces.active
    return None, None, None


def _get_active_clip(context):
    space = getattr(context, "space_data", None)
    if space and getattr(space, "clip", None):
        return space.clip
    return bpy.data.movieclips[0] if bpy.data.movieclips else None


def _prev_next_keyframes(track, frame):
    prev_k, next_k = None, None
    for m in track.markers:
        if not m.is_keyed:
            continue
        if m.frame < frame and (prev_k is None or m.frame > prev_k):
            prev_k = m.frame
        if m.frame > frame and (next_k is None or m.frame < next_k):
            next_k = m.frame
    return prev_k, next_k


# --- Error-Serie --------------------------------------------------------------

def _build_error_series(recon):
    """frame -> average_error (float) aus Reconstruction Cameras."""
    series = {}
    for cam in recon.cameras:
        series[int(cam.frame)] = float(cam.average_error)
    # sortiert zurückgeben
    return dict(sorted(series.items()))


# --- Neue Selektion: Top-N nach Szene/marker_basis ----------------------------

def _select_top_n_frames_by_scene_basis(context, recon):
    """
    N = (scene.frame_end - scene.frame_start + 1) // scene['marker_basis']
    mind. 1. Wählt die N höchsten Error-Frames (innerhalb des Szenenbereichs).
    """
    scene = context.scene
    frame_start = int(scene.frame_start)
    frame_end = int(scene.frame_end)
    total_frames = max(0, frame_end - frame_start + 1)

    marker_basis = int(scene.get("marker_basis", 25))
    if marker_basis <= 0:
        marker_basis = 25

    # Ganzzahlige Division; mindestens 1
    n = max(1, total_frames // marker_basis)

    series = _build_error_series(recon)

    # Auf Szenenbereich filtern
    series = {f: e for f, e in series.items() if frame_start <= f <= frame_end}

    if not series:
        return []

    # Top-N Frames nach Error (desc), stabil nach Frame (asc) für Reproduzierbarkeit
    sorted_by_error = sorted(series.items(), key=lambda kv: (-kv[1], kv[0]))
    selected = [f for f, _ in sorted_by_error[:n]]

    print(f"[Select] Szene-Frames: {total_frames}, marker_basis: {marker_basis} → N={n}")
    print(f"[Select] Top-{n} Frames (höchste Errors): {selected}")
    return sorted(selected)


# --- Core Routine -------------------------------------------------------------

def run_refine_on_high_error(
    context,
    limit_frames: int = 0,
    resolve_after: bool = False,
    # --- Backward-Compat (ignoriert, aber akzeptiert) ---
    error_threshold: float | None = None,
    **_compat_ignored,
) -> int:
    """
    Refine an genau N Frames mit den höchsten Solve-Frame-Errors.
    N = (Szenen-Frameanzahl) // scene['marker_basis'], N >= 1.

    Hinweis: 'error_threshold' und weitere Alt-Argumente werden im Top-N-Modus ignoriert
    (Kompatibilität für ältere Aufrufer/Operatoren).
    """
    if error_threshold is not None:
        print("[Refine][Compat] 'error_threshold' übergeben, wird im Top-N-Modus ignoriert.")
    if _compat_ignored:
        print(f"[Refine][Compat] Ignoriere zusätzliche Alt-Argumente: {list(_compat_ignored.keys())}")

    clip = _get_active_clip(context)
    if not clip:
        raise RuntimeError("Kein MovieClip geladen.")

    obj = clip.tracking.objects.active
    recon = obj.reconstruction
    if not recon.is_valid:
        raise RuntimeError("Keine gültige Rekonstruktion gefunden (Solve fehlt oder wurde gelöscht).")

    # --- Frame-Selektion (neu) ---
    bad_frames = _select_top_n_frames_by_scene_basis(context, recon)

    # Optional zusätzlich begrenzen
    if limit_frames > 0 and bad_frames:
        bad_frames = bad_frames[:int(limit_frames)]

    if not bad_frames:
        print("[INFO] Keine Frames für Refine gefunden.")
        return 0

    area, region, space_ce = _find_clip_window(context)
    if not area:
        raise RuntimeError("Kein CLIP_EDITOR-Fenster gefunden (Kontext erforderlich).")

    scene = context.scene
    original_frame = scene.frame_current
    processed = 0

    for f in bad_frames:
        print(f"\n[FRAME] Starte Refine für Frame {f}")
        scene.frame_set(f)

        tracks_forward, tracks_backward = [], []
        for tr in clip.tracking.tracks:
            if getattr(tr, "hide", False) or getattr(tr, "lock", False):
                continue
            prev_k, next_k = _prev_next_keyframes(tr, f)
            mk = tr.markers.find_frame(f, exact=True)
            if mk and getattr(mk, "mute", False):
                continue
            if prev_k is not None:
                tracks_forward.append(tr)
            if next_k is not None:
                tracks_backward.append(tr)

        print(f"  → Vorwärts-Refine Tracks: {len(tracks_forward)} | Rückwärts-Refine Tracks: {len(tracks_backward)}")

        if tracks_forward:
            with context.temp_override(area=area, region=region, space_data=space_ce):
                for tr in clip.tracking.tracks:
                    tr.select = False
                for tr in tracks_forward:
                    tr.select = True
                bpy.ops.clip.refine_markers(backwards=False)

        if tracks_backward:
            with context.temp_override(area=area, region=region, space_data=space_ce):
                for tr in clip.tracking.tracks:
                    tr.select = False
                for tr in tracks_backward:
                    tr.select = True
                bpy.ops.clip.refine_markers(backwards=True)

        processed += 1
        print(f"  [DONE] Frame {f} abgeschlossen.")

    if resolve_after:
        print("[ACTION] Starte erneutes Kamera-Solve…")
        with context.temp_override(area=area, region=region, space_data=space_ce):
            bpy.ops.clip.solve_camera()
        print("[DONE] Kamera-Solve abgeschlossen.")

    scene.frame_set(original_frame)
    print(f"\n[SUMMARY] Insgesamt bearbeitet: {processed} Frame(s)")
    return processed


# --- Operator-Wrapper ---------------------------------------------------------

class CLIP_OT_refine_on_high_error(Operator):
    """Refine an den N Frames mit höchsten Solve-Frame-Errors (N = Szene/marker_basis)."""
    bl_idname = "clip.refine_on_high_error"
    bl_label = "Refine: Top-N Solve-Error Frames"
    bl_options = {"REGISTER", "UNDO"}

    # Deprecated, rein für Abwärtskompatibilität (wird ignoriert)
    error_threshold: FloatProperty(
        name="(Deprecated) Frame Error ≥",
        description="Wird im Top-N-Modus ignoriert; nur für alte Aufrufe vorhanden.",
        default=2.0, min=0.0
    )

    limit_frames: IntProperty(
        name="Max Frames",
        description="Zusätzliche Obergrenze (0 = keine Begrenzung)",
        default=0, min=0
    )
    resolve_after: BoolProperty(
        name="Nach Refine erneut lösen",
        default=False
    )

    def execute(self, context):
        try:
            n = run_refine_on_high_error(
                context,
                limit_frames=self.limit_frames,
                resolve_after=self.resolve_after,
                # Kompatibilität: wird intern ignoriert
                error_threshold=self.error_threshold
            )
        except RuntimeError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

        if n == 0:
            self.report({'INFO'}, "Keine Frames ausgewählt.")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Refine abgeschlossen an {n} Frame(s).")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(CLIP_OT_refine_on_high_error)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_refine_on_high_error)
