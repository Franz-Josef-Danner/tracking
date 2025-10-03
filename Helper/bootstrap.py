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

    # Bestimme Auflösung: bevorzugt echte Clip-Auflösung, Fallback Render-Auflösung
    space = getattr(context, 'space_data', None)
    clip = None
    if space and getattr(space, 'type', None) == 'CLIP_EDITOR':
        clip = getattr(space, 'clip', None)
    if clip and getattr(clip, 'size', None):
        try:
            hz = int(clip.size[0])
            vc = int(clip.size[1])
        except Exception:
            hz = scene.render.resolution_x
            vc = scene.render.resolution_y
    else:
        hz = scene.render.resolution_x
        vc = scene.render.resolution_y

    ma = hz * 0.025
    md = hz * 0.025
    print(f"md = {md}")

    # pattern size (integer)
    pz = int(hz * 0.01)
    print(f"pz = {pz}")

    # search size (integer)
    sz = int(pz * 2)

    tr = 1
    print(f"tr = {tr}")

    za = (ef * 4) / 14
    og = int(za * 1.1)
    ug = int(za * 0.9)

    # Tracking Settings (linke Panels -> Track Panel -> Tracking Settings)
    # pattern size = pz, search size = sz
    if clip:
        tracking = clip.tracking
        try:
            settings = tracking.settings
            # Setze Defaults für neu erstellte Tracks
            if hasattr(settings, 'default_pattern_size'):
                settings.default_pattern_size = int(pz)
            if hasattr(settings, 'default_search_size'):
                settings.default_search_size = int(sz)
            # Fallback: Setze auch direkte pattern/search size falls vorhanden
            if hasattr(settings, 'pattern_size'):
                settings.pattern_size = int(pz)
            if hasattr(settings, 'search_size'):
                settings.search_size = int(sz)
            print(f"Tracking settings gesetzt: default_pattern_size={int(pz)} default_search_size={int(sz)}")
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
    "pz": int(pz),  # pattern size (Pixel, int)
    "sz": int(sz),  # search size (Pixel, int)
        "za": float(za),
        "og": int(og),
        "ug": int(ug),
    }
