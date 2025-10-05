import bpy

def run(context, values: dict):
    """Erzeugt einen einfachen Snapshot-Kontext (Platzhalter)."""
    clip = bpy.context.edit_movieclip
    if not clip:
        print('snapshot: kein Clip')
        return
    frame = context.scene.frame_current
    print(f'snapshot: Frame {frame} für Clip {clip.name}')