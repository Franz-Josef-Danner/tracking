import bpy
from bpy.types import Operator
from bpy.props import FloatProperty, BoolProperty, IntProperty

__all__ = ("CLIP_OT_refine_on_high_error", "run_refine_on_high_error")


# --- Context Utilities --------------------------------------------------------

def _find_clip_window(context):
    """Sucht ein aktives CLIP_EDITOR-Fenster. Rückgabe: (area, region, space) oder (None, None, None)."""
    for area in context.window.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return area, region, area.spaces.active
    return None, None, None


def _get_active_clip(context):
    """Aktiven MovieClip ermitteln: bevorzugt aus space_data, sonst erstes bpy.data.movieclips."""
    space = getattr(context, "space_data", None)
    if space and getattr(space, "clip", None):
        return space.clip
    return bpy.data.movieclips[0] if bpy.data.movieclips else None


def _prev_next_keyframes(track, frame):
    """Vorherigen und nächsten Keyframe (m.is_keyed) relativ zu 'frame' finden."""
    prev_k, next_k = None, None
    for m in track.markers:
        if not m.is_keyed:
            continue
        if m.frame < frame and (prev_k is None or m.frame > prev_k):
            prev_k = m.frame
        if m.frame > frame and (next_k is None or m.frame < next_k):
            next_k = m.frame
    return prev_k, next_k


# --- Core Routine (funktionsbasiert) -----------------------------------------

def run_refine_on_high_error(context, error_threshold: float = 2.0, limit_frames: int = 0, resolve_after: bool = False) -> int:
    clip = _get_active_clip(context)
    if not clip:
        raise RuntimeError("Kein MovieClip geladen.")

    obj = clip.tracking.objects.active
    recon = obj.reconstruction
    if not recon.is_valid:
        raise RuntimeError("Keine gültige Rekonstruktion gefunden (Solve fehlt oder wurde gelöscht).")

    # Spike-Frames ermitteln
    bad_frames = [cam.frame for cam in recon.cameras if float(cam.average_error) >= float(error_threshold)]
    bad_frames = sorted(set(bad_frames))
    if limit_frames > 0:
        bad_frames = bad_frames[:int(limit_frames)]

    print(f"[INFO] Gefundene Problem-Frames (≥ {error_threshold:.3f}px): {bad_frames}")

    if not bad_frames:
        print("[INFO] Keine Frames mit zu hohem Error gefunden.")
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
            print(f"  [ACTION] Vorwärts-Refine ({len(tracks_forward)} Tracks)")
            with context.temp_override(area=area, region=region, space_data=space_ce):
                for tr in clip.tracking.tracks:
                    tr.select = False
                for tr in tracks_forward:
                    tr.select = True
                bpy.ops.clip.refine_markers(backwards=False)

        if tracks_backward:
            print(f"  [ACTION] Rückwärts-Refine ({len(tracks_backward)} Tracks)")
            with context.temp_override(area=area, region=region, space_data=space_ce):
                for tr in clip.tracking.tracks:
                    tr.select = False
                for tr in tracks_backward:
                    tr.select = True
                bpy.ops.clip.refine_markers(backwards=True)

        processed += 1
        print(f"  [DONE] Frame {f} abgeschlossen.")

    if resolve_after:
        print("[ACTION] Starte erneutes Kamera-Solve...")
        with context.temp_override(area=area, region=region, space_data=space_ce):
            bpy.ops.clip.solve_camera()
        print("[DONE] Kamera-Solve abgeschlossen.")

    scene.frame_set(original_frame)
    print(f"\n[SUMMARY] Insgesamt bearbeitet: {processed} Frame(s)")
    return processed



# --- Operator-Wrapper (optional) ---------------------------------------------

class CLIP_OT_refine_on_high_error(Operator):
    """Refine Markers an Frames mit hohem Solve-Frame-Error (beidseitig), optional mit Re-Solve."""
    bl_idname = "clip.refine_on_high_error"
    bl_label = "Refine on High Solve Error"
    bl_options = {"REGISTER", "UNDO"}

    error_threshold: FloatProperty(
        name="Frame Error ≥ (px)",
        description="Kamera-Frame-Durchschnittsfehler, ab dem Refine ausgelöst wird",
        default=2.0, min=0.0
    )
    limit_frames: IntProperty(
        name="Max Frames",
        description="Obergrenze der zu verarbeitenden Frames (0 = alle)",
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
                error_threshold=self.error_threshold,
                limit_frames=self.limit_frames,
                resolve_after=self.resolve_after
            )
        except RuntimeError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

        if n == 0:
            self.report({'INFO'}, f"Keine Frames ≥ {self.error_threshold:.3f} px.")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Refine abgeschlossen an {n} Frame(s) (≥ {self.error_threshold:.3f}px).")
        return {'FINISHED'}


# --- Register Helpers ---------------------------------------------------------

def register():
    bpy.utils.register_class(CLIP_OT_refine_on_high_error)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_refine_on_high_error)
