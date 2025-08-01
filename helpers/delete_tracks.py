import bpy

def delete_selected_tracks():
    """Löscht selektierte Tracks via Operator – mit Kontextabsicherung."""
    for area in bpy.context.window.screen.areas:
        if area.type == 'CLIP_EDITOR':
            with bpy.context.temp_override(area=area):
                bpy.ops.clip.delete_track(confirm=False)
                return
    print("❌ Kein CLIP_EDITOR gefunden – Löschung nicht möglich.")
