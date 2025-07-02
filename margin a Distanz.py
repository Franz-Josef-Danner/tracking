import bpy

# Hole den aktiven Clip aus dem Movie Clip Editor
area = next((a for a in bpy.context.screen.areas if a.type == 'CLIP_EDITOR'), None)
if area:
    space = next((s for s in area.spaces if s.type == 'CLIP_EDITOR'), None)
    if space and space.clip:
        clip = space.clip
        width = clip.size[0]

        # Berechnungen
        margin = width / 200
        distance = width / 20

        # Speichern als Custom Properties am Clip
        clip["MARGIN"] = margin
        clip["DISTANCE"] = distance

        print(f"Breite: {width}")
        print(f"MARGIN (Breite / 200): {margin}")
        print(f"DISTANCE (Breite / 20): {distance}")
    else:
        print("Kein Clip im Movie Clip Editor geladen.")
else:
    print("Movie Clip Editor nicht aktiv.")
