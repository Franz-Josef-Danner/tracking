import bpy

def run(context, ef: int):
    """Berechnet alle Parameter laut Vorgabe und gibt sie als Dict zurück.

    Reihenfolge / Formeln (Clip-Auflösung):
      hz = horizontale Auflösung
      vc = vertikale Auflösung
      ma = hz * 0.025 (margin)
      md = hz * 0.025 (min_distance)  -> print
      pz = hz * 0.01  (pattern size)  -> print
      sz = pz * 2     (search size)
      tr = 1          (threshold)     -> print
      ef = UI Wert
      za = (ef * 4) / 14
      og = za * 1.1
      ug = za * 0.9
    """
    scene = context.scene
    hz = scene.render.resolution_x
    vc = scene.render.resolution_y

    ma = hz * 0.025
    md = hz * 0.025
    print(f"md = {md}")

    pz = hz * 0.01
    print(f"pz = {pz}")

    sz = pz * 2

    tr = 1
    print(f"tr = {tr}")

    za = (ef * 4) / 14
    og = int(za * 1.1)
    ug = int(za * 0.9)

    # Tracking Settings (pattern/search size) direkt setzen, falls verfügbar
    space = getattr(context, 'space_data', None)
    clip = None
    if space and getattr(space, 'type', None) == 'CLIP_EDITOR':
        clip = getattr(space, 'clip', None)
    if clip:
        tracking = clip.tracking
        try:
            settings = tracking.settings
            if hasattr(settings, 'pattern_size'):
                settings.pattern_size = int(pz)
            if hasattr(settings, 'search_size'):
                settings.search_size = int(sz)
            print(f"Tracking settings gesetzt: pattern_size={int(pz)} search_size={int(sz)}")
        except Exception as e:
            print(f"Konnte Tracking Settings nicht setzen: {e}")

    print(f"[Kaiserlich Tracker] ef={ef} hz={hz} vc={vc} ma={ma} md={md} pz={pz} sz={sz} tr={tr} za={za} og={og} ug={ug}")

    return {
        "ef": int(ef),
        "hz": int(hz),
        "vc": int(vc),
        "ma": int(ma),  # margin
        "md": int(md),  # min_distance
        "tr": float(tr),  # threshold
        "pz": float(pz),  # pattern size (berechnet in Pixeln)
        "sz": float(sz),  # search size (berechnet in Pixeln)
        "za": float(za),
        "og": int(og),
        "ug": int(ug),
    }
