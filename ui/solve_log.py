import math, time, bpy
from .utils import tag_clip_redraw


# --- bestehende Logik unverändert lassen (Einträge hinzufügen/trimmen) ---
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

    # ---- Entprellung/Dedupe -----------------------------------------------
    # 1) Pro Attempt nur einen Eintrag (falls Property existiert)
    try:
        attempt = int(getattr(scn, "kaiserlich_solve_attempts", -1))
    except Exception:
        attempt = -1
    last_attempt = scn.get("_kaiserlich_last_attempt_logged", None) if scn else None
    # 2) Zeitfenster-Entprellung (Back-to-back Doppelcalls)
    now = time.time()
    last_ts = scn.get("_kaiserlich_last_log_ts", 0.0) if scn else 0.0
    last_v = scn.get("_kaiserlich_last_log_v", None) if scn else None
    if attempt == last_attempt and now - last_ts < 0.2 and v == last_v:
        return

    if scn is None:
        return
    coll = getattr(scn, "kaiserlich_solve_err_log", None)
    if coll is None:
        return

    item = coll.add()
    item.attempt = attempt
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

    # Metadaten für Dedupe aktualisieren
    try:
        scn["_kaiserlich_last_attempt_logged"] = attempt
        scn["_kaiserlich_last_log_ts"] = now
        scn["_kaiserlich_last_log_v"] = v
    except Exception:
        pass
