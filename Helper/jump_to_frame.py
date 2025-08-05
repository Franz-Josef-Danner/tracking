import bpy

def jump_to_frame(context):
    scene = context.scene
    target_frame = scene.get("goto_frame")

    if target_frame is None:
        print("[GotoFrame] Scene variable 'goto_frame' nicht gesetzt.")
        return False

    scene.frame_current = int(target_frame)
    print(f"[GotoFrame] Playhead auf Frame {target_frame} gesetzt.")
    return True
