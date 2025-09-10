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

    # Gleicher Attempt bereits verbucht? -> verwerfen
    if attempt is not None and last_attempt is not None and attempt == last_attempt:
        return
    # Falls kein Attempt-Tracking verfügbar: innerhalb 0.5s denselben Wert (±1e-6) nicht doppelt loggen
    if attempt == -1:
        if (now - float(last_ts) < 0.5) and (last_v is not None) and (abs(float(last_v) - v) <= 1e-6):
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

    # Metadaten für Dedupe aktualisieren
    try:
        scn["_kaiserlich_last_attempt_logged"] = attempt
        scn["_kaiserlich_last_log_ts"] = now
        scn["_kaiserlich_last_log_v"] = v
    except Exception:
        pass
