import math
import time
import bpy

from .utils import tag_clip_redraw


def kaiserlich_solve_log_add(context: bpy.types.Context, value: float | None) -> None:
    """Logge einen Solve-Versuch NUR bei gültigem numerischen Wert (kein None/NaN/Inf)."""
    scn = context.scene if hasattr(context, "scene") else None
    dbg = bool(getattr(scn, "kaiserlich_debug_graph", False)) if scn else False
    if dbg:
        pass  # removed print
    # Nur numerische Endwerte zulassen
    if value is None:
        if dbg:
            pass  # removed print
        return
    try:
        v = float(value)
    except Exception:
        if dbg:
            pass  # removed print
        return
    if (v != v) or math.isinf(v):  # NaN oder ±Inf
        if dbg:
            reason = "NaN" if (v != v) else "Inf"
            pass  # removed print
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
    # Neuester Eintrag ganz nach oben (Index 0)
    try:
        coll = scn.kaiserlich_solve_err_log
        coll.move(len(coll) - 1, 0)
        scn.kaiserlich_solve_err_idx = 0
    except Exception:
        pass
    # Ältere Werte abschneiden, nur die letzten 10 behalten
    coll = scn.kaiserlich_solve_err_log
    if dbg:
        pass  # removed print
    while len(coll) > 10:
        coll.remove(len(coll) - 1)
    if dbg:
        seq_dbg = [(it.attempt, it.value) for it in coll]
        pass  # removed print
    # UI-Refresh (CLIP-Editor + Sidebar)
    tag_clip_redraw()

