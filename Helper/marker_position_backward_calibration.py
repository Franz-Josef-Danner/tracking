# ------------------------------------------------------------
# Kaiserlich Tracker – Backward Calibration (symmetrisch zu Forward)
# ------------------------------------------------------------
# Diese Version ist vollständig gespiegelt:
# gleiche Parameter, gleiche Logik, nur inverse Zeitrichtung.
# ------------------------------------------------------------

from typing import Optional, List, Any
import ast
import bpy


# -------------------------------------------------------------------
# Erwartete extern bereitgestellte Low-Level-Funktionen
# -------------------------------------------------------------------
# get_active_markers(frame) -> List[str]
# get_marker_position(track_or_name, frame) -> (x, y)
# set_marker_position(track_or_name, frame, x, y)


# -------------------------------------------------------------------
# Hilfsfunktionen: Scene-String lesen
# -------------------------------------------------------------------
def _read_scene_list(scene: bpy.types.Scene, key: str) -> Optional[List[str]]:
    raw = scene.get(key)
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            parsed = ast.literal_eval(raw)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                return list(parsed.values())
            return [s.strip() for s in raw.split(",") if s.strip()]
        except Exception:
            return [s.strip() for s in raw.split(",") if s.strip()]
    if isinstance(raw, list):
        return raw
    return None


# -------------------------------------------------------------------
# Backward Calibration – sauber gespiegelt zur Forward-Version
# -------------------------------------------------------------------
def correct_marker_positions_backward(
    scene: bpy.types.Scene,
    ref_tracks: List[str],
    calibrate_tracks: List[str],
    frame_now: int,
    frame_next: Optional[int],
    frame_next2: Optional[int] = None,
    frame_next3: Optional[int] = None
):
    """
    Symmetrische Backward-Kalibrierung:
    f_now  = aktueller Frame
    f_next = Frame in Tracking-Richtung (rückwärts: +1)
    """

    # Referenzliste sauber ziehen
    ref_scene = None

    # identische Regeln wie Forward
    if "best_tracks" in scene:
        ref_scene = _read_scene_list(scene, "best_tracks")
    elif "good_tracks" in scene:
        ref_scene = _read_scene_list(scene, "good_tracks")

    if not ref_scene:
        return

    # final verwendete Referenzliste
    ref_tracks = list(set(ref_tracks) & set(ref_scene))

    if not ref_tracks:
        return

    # Mindestabdeckung (identisch zu Forward)
    min_required = getattr(scene, "kaiserlich_markers_per_frame", 20) / 2

    # aktive Marker je Frame
    f0 = get_active_markers(frame_now)
    f1 = get_active_markers(frame_next) if frame_next else []
    f2 = get_active_markers(frame_next2) if frame_next2 else []
    f3 = get_active_markers(frame_next3) if frame_next3 else []

    f0_good = [m for m in f0 if m in ref_tracks]
    f1_good = [m for m in f1 if m in ref_tracks]
    f2_good = [m for m in f2 if m in ref_tracks]
    f3_good = [m for m in f3 if m in ref_tracks]

    # Auswahl exakt wie Forward (4 → 3 → 2)
    if len(f3_good) >= min_required:
        source = f3_good
        mode = 4
    elif len(f2_good) >= min_required:
        source = f2_good
        mode = 3
    elif len(f1_good) >= min_required:
        source = f1_good
        mode = 2
    else:
        return

    # Clip-Aspect
    try:
        clip = bpy.context.edit_movieclip or bpy.context.space_data.clip
        w = clip.size[0]
        h = clip.size[1]
        aspect_ratio = w / h if h != 0 else 1.0
    except Exception:
        aspect_ratio = 1.0

    # Marker-Korrektur
    for tr in calibrate_tracks:

        x_now, y_now = get_marker_position(tr, frame_now)
        x_next, y_next = get_marker_position(tr, frame_next)

        vlist_x = []
        vlist_y = []

        for gm in source:
            g0x, g0y = get_marker_position(gm, frame_now)
            g1x, g1y = get_marker_position(gm, frame_next)

            # optionale Frames
            if mode >= 3:
                g2x, g2y = get_marker_position(gm, frame_next2)
            if mode == 4:
                g3x, g3y = get_marker_position(gm, frame_next3)

            # ---- Velocity-Spiegelung ----
            if mode == 4:
                vx = 0.5 * ((g2x - g3x) + (g1x - g2x))
                vy = 0.5 * ((g2y - g3y) + (g1y - g2y))
            elif mode == 3:
                vx = 0.5 * ((g1x - g2x) + (g0x - g1x))
                vy = 0.5 * ((g1y - g2y) + (g0y - g1y))
            elif mode == 2:
                vx = (g1x - g0x)
                vy = (g1y - g0y)
            else:
                vx = vy = 0.0

            dx = (x_now - g0x)
            dy = (y_now - g0y)
            dist = (dx*dx + dy*dy) ** 0.5
            w = 1.0 / (1e-6 + dist)

            vlist_x.append((vx, w))
            vlist_y.append((vy, w))

        if not vlist_x:
            continue

        # identische Robust-Funktion wie Forward
        def robust_weighted_mean(vw):
            if len(vw) < 5:
                sw = sum(w for v, w in vw)
                return sum(v*w for v, w in vw) / sw if sw else 0.0
            vs = sorted(vw, key=lambda x: x[0])
            n = len(vs)
            cut = max(1, int(0.1*n))
            trimmed = vs[cut:-cut] if n > 2*cut else vs
            sw = sum(w for v, w in trimmed)
            return sum(v*w for v, w in trimmed) / sw if sw else 0.0

        avg_vx = robust_weighted_mean(vlist_x)
        avg_vy = robust_weighted_mean(vlist_y)

        # ---- Position rückwärts prognostizieren ----
        pred_x = x_next - avg_vx
        pred_y = y_next - avg_vy

        diff_x = abs(x_now - pred_x)
        diff_y = abs(y_now - pred_y) * aspect_ratio

        wx = max(0.0, min(1.0, 1.0 - (diff_x ** (diff_x * 20))))
        wy = max(0.0, min(1.0, 1.0 - (diff_y ** (diff_y * 20))))

        # identische Blend-Funktion wie Forward
        def blend(est, meas, w):
            a = w
            b = 1.0 - w
            return (est*a + meas*b) / (a+b if (a+b) != 0 else 1.0)

        final_x = blend(pred_x, x_now, wx)
        final_y = blend(pred_y, y_now, wy)

        set_marker_position(tr, frame_now, final_x, final_y)
