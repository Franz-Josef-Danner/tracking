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
    print(f"min_distance (md) = {md}")

    pz = hz * 0.01
    print(f"pattern size (pz) = {pz}")

    sz = pz * 2

    tr = 1
    print(f"threshold (tr) = {tr}")

    za = (ef * 4) / 14
    og = za * 1.1
    ug = za * 0.9

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
        "og": float(og),
        "ug": float(ug),
    }
