import bpy

def run(context, tr: float, md: float, ma: float):
    """Wrap für bpy.ops.clip.detect_features mit übergebenen Parametern.

    Parameter:
      tr -> threshold
      md -> min_distance
      ma -> margin
    """
    clip = bpy.context.edit_movieclip
    if not clip:
        print('detect: kein Clip')
        return
    try:
        res = bpy.ops.clip.detect_features(
            placement='FRAME',
            margin=int(ma),
            threshold=float(tr),
            min_distance=int(md)
        )
        print(f'detect: ausgeführt result={res} (margin={int(ma)} threshold={tr} min_distance={int(md)})')
    except Exception as e:
        print(f'detect: Fehler {e}')