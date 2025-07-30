import bpy


def invoke_clip_operator_safely(operator: str, **kwargs):
    """Call a clip operator with a valid CLIP_EDITOR context."""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        with bpy.context.temp_override(window=window, area=area, region=region):
                            return getattr(bpy.ops.clip, operator)(**kwargs)
    print(f"\u274c Kein g\u00fcltiger CLIP_EDITOR-Kontext f\u00fcr {operator}")
    return {'CANCELLED'}
