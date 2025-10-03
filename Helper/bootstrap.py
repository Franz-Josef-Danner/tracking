import bpy

def run(context, ef: int):
    scene = context.scene
    seq = scene.sequence_editor
    # Placeholder: Bestimme Auflösung aus Render-Settings (oder Sequencer Strip)
    hz = scene.render.resolution_x
    vc = scene.render.resolution_y

    ma = hz * 0.025
    md = hz * 0.025
    print(f"min_distance (md) = {md}")

    # pattern size (pz)
    pz = hz * 0.01
    print(f"pattern size (pz) = {pz}")

    sz = pz * 2

    tr = 1
    print(f"threshold (tr) = {tr}")

    # Eingabefeld Wert ef -> Berechnungen
    za = (ef * 4) / 14
    og = za * 1.1
    ug = za * 0.9

    print(f"ef={ef} za={za} og={og} ug={ug} hz={hz} vc={vc} ma={ma} md={md} pz={pz} sz={sz} tr={tr}")
    # Rückgabe der relevanten Parameter für weitere Schritte
    return {
        "ef": ef,
        "hz": hz,
        "vc": vc,
        "ma": int(ma),  # detect_features erwartet ints für margin / min_distance
        "md": int(md),
        "tr": float(tr),
        "pz": pz,
        "sz": sz,
        "za": za,
        "og": og,
        "ug": ug,
    }
