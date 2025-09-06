import math, time, bpy
from .utils import tag_clip_redraw

def kaiserlich_solve_log_add(context: bpy.types.Context, value: float | None) -> None:
    """Nur gültige numerische Werte loggen; max 10 Einträge; UI refreshen."""
    scn = context.scene if hasattr(context, "scene") else None
    dbg = bool(getattr(scn, "kaiserlich_debug_graph", False)) if scn else False

    if value is None:
        return
    try:
        v = float(value)
    except Exception:
        return
    if (v != v) or math.isinf(v):  # NaN/Inf rausfiltern
        return

    scn = context.scene
    try:
        scn.kaiserlich_solve_attempts += 1
    except Exception:
        scn["kaiserlich_solve_attempts"] = int(scn.get("kaiserlich_solve_attempts", 0)) + 1

    item = scn.kaiserlich_solve_err_log.add()
    item.attempt = int(scn.kaiserlich_solve_attempts)
    item.value = v
    item.stamp = time.strftime("%H:%M:%S")

    # jüngsten nach oben, Index aktualisieren
    try:
        coll = scn.kaiserlich_solve_err_log
        coll.move(len(coll) - 1, 0)
        scn.kaiserlich_solve_err_idx = 0
    except Exception:
        pass

    # Log auf 10 beschränken
    coll = scn.kaiserlich_solve_err_log
    while len(coll) > 10:
        coll.remove(len(coll) - 1)

    tag_clip_redraw()