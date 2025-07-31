import bpy


def invoke_clip_operator_safely(operator_name: str, **kwargs):
    """Call ``bpy.ops.clip.<operator_name>('INVOKE_DEFAULT', ...)`` in a valid
    ``CLIP_EDITOR`` context.
    """
    wm = bpy.context.window_manager

    for window in wm.windows:
        for area in window.screen.areas:
            if area.type == "CLIP_EDITOR":
                for region in area.regions:
                    if region.type == "WINDOW":
                        with bpy.context.temp_override(
                            window=window,
                            area=area,
                            region=region,
                        ):
                            return getattr(bpy.ops.clip, operator_name)(
                                "INVOKE_DEFAULT", **kwargs
                            )

    print(
        f"[WARNUNG] Kein g\u00fcltiger CLIP_EDITOR-Kontext gefunden f\u00fcr {operator_name}"
    )
    return {"CANCELLED"}
