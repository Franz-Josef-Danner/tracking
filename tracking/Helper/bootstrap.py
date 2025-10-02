import bpy

def bootstrap(context, ef: int):
    scene = context.scene
    clip = context.space_data.clip if context.space_data else None
    if clip is None:
        raise RuntimeError("Kein Clip im Clip Editor aktiv.")
    size = clip.size
    hz = size[0]
    vc = size[1]
    ma = hz * 0.025
    md = int(hz * 0.025)
    pz = int(hz * 0.01) or 1
    sz = pz * 2
    tr = 1.0

    za = (ef * 4) / 14
    og = za * 1.1
    ug = za * 0.9

    print(f"bootstrap: hz={hz} vc={vc} ma={ma:.2f} md={md} pz={pz} sz={sz} tr={tr} za={za:.2f} (ug={ug:.2f}, og={og:.2f})")

    return dict(hz=hz, vc=vc, ma=int(ma), md=md, pz=pz, sz=sz, tr=tr, ef=ef, za=za, og=og, ug=ug)
