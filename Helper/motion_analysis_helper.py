import math
from mathutils import Matrix


# ==========================================================
# Rohdaten sammeln: Position + Matrix pro Frame
# ==========================================================
def collect_marker_motion_data(track, current_frame, max_history=5):
    """
    Liefert: [(frame, (x, y), matrix), ...]
    Achtung: nutzt die letzten max_history Frames rückwärts.
    """
    print(f"[MotionAnalysis][Collect] Track='{track.name}', current_frame={current_frame}, max_history={max_history}")
    positions = []

    for i in range(max_history):
        f = current_frame - i
        mk = track.markers.find_frame(f)
        if not mk or mk.mute:
            # bewusst leise – sonst zu viel Spam bei langen Runs
            continue

        mat = getattr(mk, "matrix", None)
        if mat is None:
            print(f"[MotionAnalysis][Collect] WARN: Frame={f} hat keine Matrix.")
            continue

        positions.append((f, (mk.co[0], mk.co[1]), mat.copy()))

    positions.sort(key=lambda x: x[0])

    frames = [f for f, _, _ in positions]
    print(f"[MotionAnalysis][Collect] Gefundene Frames: {frames} (count={len(positions)})")

    return positions


# ==========================================================
# Komponenten extrahieren: Translation / Rotation / Scale / Shear
# ==========================================================
def extract_motion_components(pos_list):
    if len(pos_list) < 2:
        print("[MotionAnalysis][Extract] Zu wenig Daten (<2), keine Komponenten.")
        return []

    comps = []

    print(f"[MotionAnalysis][Extract] Paare={len(pos_list) - 1}")
    for i in range(len(pos_list)-1):
        f1, (x1, y1), M1 = pos_list[i]
        f2, (x2, y2), M2 = pos_list[i+1]

        # --- Translation ---
        d_trans = math.hypot(x2 - x1, y2 - y1)

        # --- Rotation ---
        rot1 = math.atan2(M1[1][0], M1[0][0])
        rot2 = math.atan2(M2[1][0], M2[0][0])
        d_rot = abs(rot2 - rot1)

        # --- Scale ---
        def scale_from_matrix(M):
            sx = math.sqrt(M[0][0]**2 + M[0][1]**2)
            sy = math.sqrt(M[1][0]**2 + M[1][1]**2)
            return sx, sy

        s1x, s1y = scale_from_matrix(M1)
        s2x, s2y = scale_from_matrix(M2)
        d_scale = math.hypot(s2x - s1x, s2y - s1y)

        # --- Shear (Perspective) ---
        shear1 = abs(M1[0][1] - M1[1][0])
        shear2 = abs(M2[0][1] - M2[1][0])
        d_shear = abs(shear2 - shear1)

        comps.append((d_trans, d_rot, d_scale, d_shear))

        print(
            f"[MotionAnalysis][Extract] Frame {f1}->{f2}: "
            f"dT={d_trans:.6f}, dR={d_rot:.6f}, dS={d_scale:.6f}, dH={d_shear:.6f}"
        )

    return comps


# ==========================================================
# Modellwahl – Verhältnisbasiert (datengetrieben, ohne Schwellen)
# ==========================================================
def classify_motion_model(components):
    if not components:
        print("[MotionAnalysis][Classify] Keine Komponenten -> 'Loc'")
        return "Loc"

    t = sum(c[0] for c in components)
    r = sum(c[1] for c in components)
    s = sum(c[2] for c in components)
    h = sum(c[3] for c in components)

    print(
        "[MotionAnalysis][Classify] Summen: "
        f"T={t:.6f}, R={r:.6f}, S={s:.6f}, H={h:.6f}"
    )

    # Perspective dominiert → klarster Fall
    if h > (r + s) * 1.5:
        print("[MotionAnalysis][Classify] Entscheidung: Perspective")
        return "Perspective"

    # Rotation dominiert
    if r > s * 1.5 and r > t * 1.2:
        print("[MotionAnalysis][Classify] Entscheidung: LocRot")
        return "LocRot"

    # Scale dominiert
    if s > r * 1.5 and s > t * 1.2:
        print("[MotionAnalysis][Classify] Entscheidung: LocScale")
        return "LocScale"

    # Rotation + Scale vergleichbar
    if r > 0.0005 and s > 0.0005:
        print("[MotionAnalysis][Classify] Entscheidung: LocRotScale")
        return "LocRotScale"

    print("[MotionAnalysis][Classify] Entscheidung: Loc")
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
    components = extract_motion_components(pos_data)
    model = classify_motion_model(components)

    print(
        f"[MotionAnalysis][Detect] RESULT Track='{track.name}', "
        f"Model={model}, Components={len(components)}"
    )

    return model
