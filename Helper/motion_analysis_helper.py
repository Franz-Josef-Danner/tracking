import math

# Optional, falls du später auf get_positions zurückgreifen willst:
from .marker_positions_helper import get_positions


# ==========================================================
# Rohdaten sammeln: Position pro Frame
# ==========================================================
def collect_marker_motion_data(track, current_frame, max_history=5):
    """
    Liefert: [(frame, x, y), ...]
    Nutzt die letzten max_history Frames rückwärts.
    """
    print(f"[MotionAnalysis][Collect] Track='{track.name}', current_frame={current_frame}, max_history={max_history}")

    # Variante A: Direkt über Marker-Liste
    positions = []
    for i in range(max_history):
        f = current_frame - i
        mk = track.markers.find_frame(f)
        if not mk or mk.mute:
            continue
        positions.append((f, mk.co[0], mk.co[1]))

    # Wenn du schon überall get_positions verwendest, könntest du statt oben auch:
    # raw = get_positions(track, current_frame, max_frames=max_history)
    # positions = [(f, x, y) for f, (x, y) in raw]

    positions.sort(key=lambda x: x[0])

    frames = [f for f, _, _ in positions]
    print(f"[MotionAnalysis][Collect] Gefundene Frames: {frames} (count={len(positions)})")

    return positions


# ==========================================================
# Komponenten extrahieren: Translation / Spannweiten / Distanz-Varianz
# ==========================================================
def extract_motion_components(pos_list):
    """
    Berechnet:
      - frame-weise Translation (d_trans)
      - X/Y-Spannweite (dx_span, dy_span)
      - Distanz-Varianz (dist_var) als grober Scale-Proxy
    """
    if len(pos_list) < 2:
        print("[MotionAnalysis][Extract] Zu wenig Daten (<2), keine Komponenten.")
        return [], 0.0, 0.0, 0.0

    comps = []
    xs = [x for _, x, _ in pos_list]
    ys = [y for _, _, y in pos_list]

    # Spannweite in X/Y über das Zeitfenster
    dx_span = max(xs) - min(xs)
    dy_span = max(ys) - min(ys)

    print(
        f"[MotionAnalysis][Extract] Framespan={pos_list[0][0]}->{pos_list[-1][0]}, "
        f"dx_span={dx_span:.6f}, dy_span={dy_span:.6f}"
    )

    # Frame-zu-Frame Translation + Distanz-Liste
    dists = []
    for i in range(len(pos_list) - 1):
        f1, x1, y1 = pos_list[i]
        f2, x2, y2 = pos_list[i + 1]

        dx = x2 - x1
        dy = y2 - y1
        d_trans = math.hypot(dx, dy)
        dists.append(d_trans)
        comps.append((f1, f2, d_trans))

        print(
            f"[MotionAnalysis][Extract] Frame {f1}->{f2}: "
            f"dx={dx:.6f}, dy={dy:.6f}, dT={d_trans:.6f}"
        )

    if dists:
        dist_min = min(dists)
        dist_max = max(dists)
        dist_var = dist_max - dist_min
    else:
        dist_var = 0.0

    print(
        f"[MotionAnalysis][Extract] Distanz-Stats: "
        f"min={dist_min:.6f if dists else 0.0}, "
        f"max={dist_max:.6f if dists else 0.0}, "
        f"var={dist_var:.6f}"
        if dists
        else "[MotionAnalysis][Extract] Distanz-Stats: keine Distanzen"
    )

    return comps, dx_span, dy_span, dist_var


# ==========================================================
# Modellwahl – Verhältnisbasiert auf Positionsdaten
# ==========================================================
def classify_motion_model(components, dx_span, dy_span, dist_var):
    """
    Komponenten:
      - components: [(f1, f2, d_trans), ...]
      - dx_span/dy_span: Gesamtbewegung in X/Y
      - dist_var: Variation der Translation (proxy für „Skalierung“)
    """
    if not components:
        print("[MotionAnalysis][Classify] Keine Komponenten -> 'Loc'")
        return "Loc"

    total_trans = sum(c[2] for c in components)

    print(
        "[MotionAnalysis][Classify] Summary: "
        f"total_trans={total_trans:.6f}, dx_span={dx_span:.6f}, "
        f"dy_span={dy_span:.6f}, dist_var={dist_var:.6f}"
    )

    # Heuristik:
    # - Wenn quasi nichts passiert → Loc
    if total_trans < 1e-5 and dx_span < 1e-5 and dy_span < 1e-5:
        print("[MotionAnalysis][Classify] Entscheidung: Loc (kaum Bewegung)")
        return "Loc"

    # „Rotationsähnlich“: viel X/Y-Bewegung, aber Distanz über Frames relativ stabil
    if dist_var < total_trans * 0.2 and (dx_span > total_trans * 0.3 or dy_span > total_trans * 0.3):
        print("[MotionAnalysis][Classify] Entscheidung: LocRot")
        return "LocRot"

    # „Scale-ähnlich“: starke Varianz in der Bewegungsdistanz
    if dist_var > total_trans * 0.4:
        print("[MotionAnalysis][Classify] Entscheidung: LocScale")
        return "LocScale"

    # Mix: Rotation + „irgendwas“ → LocRotScale
    if dist_var > total_trans * 0.2 and (dx_span > total_trans * 0.2 or dy_span > total_trans * 0.2):
        print("[MotionAnalysis][Classify] Entscheidung: LocRotScale")
        return "LocRotScale"

    # Fallback
    print("[MotionAnalysis][Classify] Entscheidung: Loc (Fallback)")
    return "Loc"


# ==========================================================
# Haupt-API: Modell bestimmen für EINEN Track
# ==========================================================
def detect_motion_model_for_track(track, current_frame, max_history=5):
    print(
        f"[MotionAnalysis][Detect] START Track='{track.name}', "
        f"current_frame={current_frame}, max_history={max_history}"
    )

    pos_data = collect_marker_motion_data(track, current_frame, max_history=max_history)
    components, dx_span, dy_span, dist_var = extract_motion_components(pos_data)
    model = classify_motion_model(components, dx_span, dy_span, dist_var)

    print(
        f"[MotionAnalysis][Detect] RESULT Track='{track.name}', "
        f"Model={model}, Segmente={len(components)}"
    )

    return model
