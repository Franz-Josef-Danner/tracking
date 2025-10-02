import bpy


def bootstrap(context):
    """Initiale Berechnung der Parameter.

    Rückgabe: dict mit Werten (statt Set im Pseudocode).
    """
    space = context.space_data
    clip = getattr(space, 'clip', None)
    if clip is None:
        raise RuntimeError('Kein MovieClip aktiv')

    width, height = clip.size

    ma = width * 0.025   # Margin
    md = width * 0.025   # Min Distance (Pixel)
    pz = width * 0.01    # Pattern Size (Basis)
    sz = pz * 2          # Search Size heuristisch
    tr = 1.0             # Threshold Start

    scene = context.scene
    ef = getattr(scene, 'kaiserlich_marker_per_frame', 25)
    za = (ef * 4) / 14
    og = za * 1.1  # Obergrenze
    ug = za * 0.9  # Untergrenze

    values = {
        'hz': width,
        'vc': height,
        'ma': ma,
        'md': md,
        'pz': pz,
        'sz': sz,
        'tr': tr,
        'za': za,
        'og': og,
        'ug': ug,
    }

    print('[Kaiserlich][bootstrap]', values)
    return values
