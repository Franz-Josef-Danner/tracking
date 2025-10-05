import bpy

def run(context, tr: float, md: float, ma: float, clip=None):
    """Wrap für bpy.ops.clip.detect_features mit übergebenen Parametern.

    Parameter:
      tr -> threshold
      md -> min_distance
      ma -> margin
    """
    if clip is None:
        clip = getattr(bpy.context, 'edit_movieclip', None)
    if not clip:
        print('detect: kein Clip (Kontext ohne edit_movieclip)')
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