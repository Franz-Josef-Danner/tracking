# Helper/main_to_adapt.py
import bpy

__all__ = ("main_to_adapt", "clip_override")

def clip_override(context):
    """Sicheren CLIP_EDITOR-Override bereitstellen (oder None)."""
    win = context.window
    if not win or not win.screen:
        return None
    for area in win.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return {
                        'area': area,
                        'region': region,
                        'space_data': area.spaces.active
                    }
    return None


def main_to_adapt(
    context: bpy.types.Context,
    *,
    factor: int = 4,
    use_override: bool = True,
    call_next: bool = True,
    invoke_next: bool = True,
):
    """
    Setzt scene['marker_adapt'] aus scene['marker_basis'] * factor * 0.9.
    Optional: triggert im Anschluss 'bpy.ops.clip.tracker_settings'.

    Returns:
        (ok: bool, marker_adapt: int, op_result: str|None)
    """
    scene = context.scene

    marker_basis = int(scene.get("marker_basis", 25))
    marker_adapt = int(marker_basis * factor * 0.9)

    # Persistieren für Downstream-Consumer
    scene["marker_adapt"] = marker_adapt
    print(f"[MainToAdapt] marker_adapt gesetzt: {marker_adapt} (basis={marker_basis}, factor={factor})")

    op_result = None
    if call_next:
        try:
            override = clip_override(context) if use_override else None
            op_call_mode = 'INVOKE_DEFAULT' if invoke_next else 'EXEC_DEFAULT'

            if override:
                with context.temp_override(**override):
                    op_result = bpy.ops.clip.tracker_settings(op_call_mode)
            else:
                op_result = bpy.ops.clip.tracker_settings(op_call_mode)

            print(f"[MainToAdapt] Übergabe an tracker_settings → {op_result}")
        except Exception as e:
            print(f"[MainToAdapt][ERROR] tracker_settings konnte nicht gestartet werden: {e}")
            return False, marker_adapt, None

    return True, marker_adapt, op_result
