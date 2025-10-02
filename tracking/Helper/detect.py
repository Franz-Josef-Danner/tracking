import bpy

def detect_features(margin: int, threshold: float, min_distance: int):
    # Direktes Mapping auf Blender Operator
    try:
        bpy.ops.clip.detect_features(placement='FRAME', margin=margin, threshold=threshold, min_distance=min_distance)
    except Exception as e:
        print(f"Detect Features Fehler: {e}")
