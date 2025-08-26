import bpy

__all__ = ("run_marker_adapt_boost",)

def run_marker_adapt_boost(context: bpy.types.Context):

    scene = context.scene

    base = scene.get("marker_adapt", None)
    if base is None:
        base = scene.get("marker_basis", 25)

    try:
        base_val = float(base)
    except Exception:
        base_val = 25.0

    new_val = round(base_val * 1.1)
    scene["marker_adapt"] = int(new_val)

    msg = f"marker_adapt: {int(base_val)} → {int(new_val)}"
    print(f"[MarkerAdapt] {msg}")

    # Identisches Abschlussverhalten wie ein Operator
    return {'FINISHED'}
