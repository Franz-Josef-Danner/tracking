import bpy

def jump_to_frame(context):
    scene = context.scene
    target_frame = scene.get("goto_frame")

    if target_frame is None:
        return False

    scene.frame_current = int(target_frame)
    return True
