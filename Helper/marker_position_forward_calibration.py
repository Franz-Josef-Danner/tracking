# Helper/marker_position_forward_calibration.py
# ---------------------------------------------------------------------
# Stabilisierung/Korrektur von Markerpositionen im aktuellen Frame
# anhand stabiler Referenzen aus bis zu 4 Rückblick-Frames.
#
# Log-Ausgaben:
#   [INIT]     – erkannte Referenzquelle
#   [MODE]     – gewählte Frame-Kombination (4/3/2)
#   [FORMULA]  – Geschätzte Velocity & Gewicht
#   [RESULT]   – alte → neue Position
#   [WARN]     – fehlende Voraussetzungen / zu wenig Marker
# ---------------------------------------------------------------------

from typing import List, Tuple, Optional
import math
import bpy


# ============================================================
# Core marker utilities (Proxy an bestehende Helper)
# ============================================================

def get_active_markers(frame: int) -> List[bpy.types.MovieTrackingTrack]:
    """Dummy-Wrapper, erwartet externen Helper im realen Add-on."""
    ctx = bpy.context
    clip = getattr(ctx.space_data, "clip", None)
    if not clip:
        return []
    out = []
    for t in clip.tracking.tracks:
        if t.select and t.markers.find_frame(frame):
            out.append(t)
    return out


def get_marker_position(track, frame: int) -> Tuple[float, float]:
    mk = track.markers.find_frame(frame)
    if mk:
        return float(mk.co[0]), float(mk.co[1])
    return 0.0, 0.0


def set_marker_position(track, frame: int, x: float, y: float):
    mk = track.markers.find_frame(frame)
    if mk:
        mk.co[0], mk.co[1] = float(x), float(y)


# ============================================================
# Hauptlogik
# ============================================================

def correct_marker_positions(scene,
                             good_trackss,
                             selected_markers,
                             frame_a,
                             frame_b,
                             frame_c=None,
                             frame_d=None):
    """
    Stabilisiert Markerpositionen im Frame_a anhand stabiler Marker
    aus bis zu 4 Rückblickframes.
    """

    # ----------------------------------------------------------
    # Referenzquellenwahl (Mutual Exclusivity)
    # ----------------------------------------------------------
    if "good_tracks" in scene and "best_tracks" in scene:
        print("[MarkerCorrection][WARN] Beide Referenz-Strings vorhanden – Abbruch.")
        return

    if "good_tracks" in scene:
        good_trackss = scene["good_tracks"]
        print("[MarkerCorrection][INIT] Verwende Referenz: good_tracks")
    elif "best_tracks" in scene:
        good_trackss = scene["best_tracks"]
        print("[MarkerCorrection][INIT] Verwende Referenz: best_tracks")
    else:
        print("[MarkerCorrection][WARN] Kein Referenz-String gefunden – Abbruch.")
        return

    # ----------------------------------------------------------
    # Mindestabdeckung prüfen
    # ----------------------------------------------------------
    min_required = getattr(scene, "kaiserlich_markers_per_frame", 20) / 2

    fa = get_active_markers(frame_a)
    fb = get_active_markers(frame_b)
    fc = get_active_markers(frame_c) if frame_c else []
    fd = get_active_markers(frame_d) if frame_d else []

    fa_good = [m for m in fa if m in good_trackss]
    fb_good = [m for m in fb if m in good_trackss]
    fc_good = [m for m in fc if m in good_trackss]
    fd_good = [m for m in fd if m in good_trackss]

    la, lb, lc, ld = len(fa_good), len(fb_good), len(fc_good), len(fd_good)

    # ----------------------------------------------------------
    # Moduswahl nach Datenlage
    # ----------------------------------------------------------
    if ld >= min_required:
        source = fd_good; mode = 4
    elif lc >= min_required:
        source = fc_good; mode = 3
    elif lb >= min_required:
        source = fb_good; mode = 2
    elif la >= min_required:
        print("[MarkerCorrection][INFO] Nur aktueller Frame – keine Korrektur nötig.")
        return
    else:
        print("[MarkerCorrection][WARN] Zu wenige stabile Marker – Abbruch.")
        return

    print(f"[MarkerCorrection][MODE] {mode}-Frame-Basis gewählt "
          f"(fd={ld} fc={lc} fb={lb} fa={la}, min={min_required:.0f})")

    # ----------------------------------------------------------
    # Hilfsfunktionen
    # ----------------------------------------------------------
    def robust_weighted_mean(pairs: List[Tuple[float, float]]) -> float:
        """Trimmed weighted mean (10 %) mit Fallback."""
        n = len(pairs)
        if n == 0:
            return 0.0
        if n < 5:
            s = sum(w for _, w in pairs)
            return sum(v * w for v, w in pairs) / s if s else 0.0
        pairs = sorted(pairs, key=lambda x: x[0])
        cut = max(1, int(0.1 * n))
        core = pairs[cut:-cut] if n > 2 * cut else pairs
        s = sum(w for _, w in core)
        return sum(v * w for v, w in core) / s if s else 0.0

    def radial_weight(ax, ay, bx, by):
        d = math.hypot(ax - bx, ay - by)
        return 1.0 / (1e-6 + d)

    # ----------------------------------------------------------
    # Positionskorrektur
    # ----------------------------------------------------------
    for sm in selected_markers:
        fa_sm_x, fa_sm_y = get_marker_position(sm, frame_a)
        fb_sm_x, fb_sm_y = get_marker_position(sm, frame_b)

        wvx, wvy = [], []

        for gm in source:
            fa_gx, fa_gy = get_marker_position(gm, frame_a)
            fb_gx, fb_gy = get_marker_position(gm, frame_b)
            if mode >= 3:
                fc_gx, fc_gy = get_marker_position(gm, frame_c)
            if mode == 4:
                fd_gx, fd_gy = get_marker_position(gm, frame_d)

            # Geschwindigkeitsabschätzung
            if mode == 4:
                v1x, v1y = fb_gx - fc_gx, fb_gy - fc_gy
                v2x, v2y = fa_gx - fb_gx, fa_gy - fb_gy
                vx, vy = 0.5 * (v1x + v2x), 0.5 * (v1y + v2y)
            elif mode == 3:
                vx = 0.5 * ((fb_gx - fc_gx) + (fa_gx - fb_gx))
                vy = 0.5 * ((fb_gy - fc_gy) + (fa_gy - fb_gy))
            elif mode == 2:
                vx, vy = fa_gx - fb_gx, fa_gy - fb_gy
            else:
                vx = vy = 0.0

            w = radial_weight(fa_sm_x, fa_sm_y, fa_gx, fa_gy)
            wvx.append((vx, w))
            wvy.append((vy, w))
            print(f"[MarkerCorrection][FORMULA] gm={gm.name}  "
                  f"v=({vx:+.5f},{vy:+.5f})  w={w:.4f}")

        if not wvx or not wvy:
            print(f"[MarkerCorrection][WARN] {sm.name}: keine gültigen Referenzen.")
            continue

        avg_vx, avg_vy = robust_weighted_mean(wvx), robust_weighted_mean(wvy)

        # Vorhersage & Kalibrierung
        new_x, new_y = fb_sm_x + avg_vx, fb_sm_y + avg_vy
        calib_x, calib_y = 0.5 * (fa_sm_x + new_x), 0.5 * (fa_sm_y + new_y)

        # Dämpfung (±5 %)
        final_x = max(new_x * 0.95, min(new_x * 1.05, calib_x))
        final_y = max(new_y * 0.95, min(new_y * 1.05, calib_y))

        set_marker_position(sm, frame_a, final_x, final_y)
        print(f"[MarkerCorrection][RESULT] {sm.name}: "
              f"({fa_sm_x:.5f},{fa_sm_y:.5f}) → ({final_x:.5f},{final_y:.5f})")

    print(f"[MarkerCorrection][SUMMARY] Marker-Korrektur abgeschlossen "
          f"(Mode={mode}, Frames={frame_a},{frame_b},{frame_c},{frame_d}).")
