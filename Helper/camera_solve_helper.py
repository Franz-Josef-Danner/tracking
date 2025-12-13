# Helper/camera_solve_helper.py
import bpy

ERROR_THRESHOLD = 10.0


def run_camera_solve(context):
    clip = getattr(context.space_data, "clip", None)
    if not clip:
        return {"CANCELLED"}

    tracking = clip.tracking
    settings = tracking.settings
    recon = tracking.reconstruction

    # --- Average Error prüfen ---
    avg_error = None
    if recon and recon.is_valid:
        avg_error = recon.average_error

    # --- Entscheidungslogik ---
    if avg_error is not None and avg_error < ERROR_THRESHOLD:
        settings.refine_focal_length = True
    else:
        settings.refine_focal_length = False

    # --- Solve auslösen ---
    bpy.ops.clip.solve_camera('INVOKE_DEFAULT')

    return {"FINISHED"}