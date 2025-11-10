# ---------------------------------------------------------------------
# Marker-Korrektur über bis zu 4 Frames mit dynamischem Rückfall-System
# inkl. robuster Mittelung und radialem Gewicht
# Automatische Auswahl zwischen 'good_marker' und 'best_marker'
# ---------------------------------------------------------------------

def correct_marker_positions(scene, good_markers, selected_markers, frame_a, frame_b, frame_c=None, frame_d=None):
    """
    Korrigiert instabile Markerpositionen anhand stabiler Marker
    über bis zu 4 vorherige Frames. Adaptive Gewichtung und Fallback-System.
    Jetzt mit robuster Mittelung (Trimmen extremer Werte) und radialer Gewichtung.
    Erkennt automatisch, ob 'good_marker' oder 'best_marker' in der Szene existiert.
    """

    # ----------------------------------------------------------
    # Auswahl des existierenden Marker-Strings
    # ----------------------------------------------------------
    if "good_marker" in scene and "best_marker" in scene:
        print("[Marker Correction] Fehler: Sowohl 'good_marker' als auch 'best_marker' existieren – Konflikt.")
        return

    elif "good_marker" in scene:
        good_markers = scene["good_marker"]
        print("[Marker Correction] Verwende Marker-Set: 'good_marker'")

    elif "best_marker" in scene:
        good_markers = scene["best_marker"]
        print("[Marker Correction] Verwende Marker-Set: 'best_marker'")

    else:
        print("[Marker Correction] Kein gültiger Marker-String ('good_marker' oder 'best_marker') vorhanden – Abbruch.")
        return

    # ----------------------------------------------------------
    # Mindestanzahl stabiler Marker
    # ----------------------------------------------------------
    min_required = getattr(scene, "kaiserlich_markers_per_frame", 20) / 2

    # Aktive Marker pro Frame
    fa_marker = get_active_markers(frame_a)
    fb_marker = get_active_markers(frame_b)
    fc_marker = get_active_markers(frame_c) if frame_c else []
    fd_marker = get_active_markers(frame_d) if frame_d else []

    # Matching der gültigen Marker (Schnittmengenbildung)
    fa_good = [m for m in fa_marker if m in good_markers]
    fb_good = [m for m in fb_marker if m in good_markers]
    fc_good = [m for m in fc_marker if m in good_markers]
    fd_good = [m for m in fd_marker if m in good_markers]

    fa_gm_count = len(fa_good)
    fb_gm_count = len(fb_good)
    fc_gm_count = len(fc_good)
    fd_gm_count = len(fd_good)

    # ----------------------------------------------------------
    # FALL 1 – 4-Frame-Basis (höchste Genauigkeit)
    # ----------------------------------------------------------
    if fd_gm_count >= min_required:
        source = fd_good
        base_frames = (fa_good, fb_good, fc_good, fd_good)
        mode = 4

    # ----------------------------------------------------------
    # FALL 2 – 3-Frame-Basis
    # ----------------------------------------------------------
    elif fc_gm_count >= min_required:
        source = fc_good
        base_frames = (fa_good, fb_good, fc_good)
        mode = 3

    # ----------------------------------------------------------
    # FALL 3 – 2-Frame-Basis
    # ----------------------------------------------------------
    elif fb_gm_count >= min_required:
        source = fb_good
        base_frames = (fa_good, fb_good)
        mode = 2

    # ----------------------------------------------------------
    # FALL 4 – Kein Vektor möglich
    # ----------------------------------------------------------
    elif fa_gm_count >= min_required:
        print("[Marker Correction] Nur aktueller Frame – keine Korrektur notwendig.")
        return

    else:
        print("[Marker Correction] Zu wenige gültige Marker – Prozess abgebrochen.")
        return

    # ----------------------------------------------------------
    # Positionskorrektur der selektierten Marker
    # ----------------------------------------------------------
    for sm in selected_markers:
        # Startwerte
        fa_sm_x, fa_sm_y = get_marker_position(sm, frame_a)
        fb_sm_x, fb_sm_y = get_marker_position(sm, frame_b)

        weighted_velocities_x = []
        weighted_velocities_y = []

        # Vergleich mit allen good markers
        for gm in source:
            fa_gm_x, fa_gm_y = get_marker_position(gm, frame_a)
            fb_gm_x, fb_gm_y = get_marker_position(gm, frame_b)

            # --- Bewegungsvektoren für good marker ---
            if mode >= 3:
                fc_gm_x, fc_gm_y = get_marker_position(gm, frame_c)
            if mode == 4:
                fd_gm_x, fd_gm_y = get_marker_position(gm, frame_d)

            # Velocity aus Differenzen
            if mode == 4:
                v1x = fb_gm_x - fc_gm_x
                v2x = fa_gm_x - fb_gm_x
                v1y = fb_gm_y - fc_gm_y
                v2y = fa_gm_y - fb_gm_y
                v_gm_x = 0.5 * (v1x + v2x)
                v_gm_y = 0.5 * (v1y + v2y)
            elif mode == 3:
                v_gm_x = 0.5 * ((fb_gm_x - fc_gm_x) + (fa_gm_x - fb_gm_x))
                v_gm_y = 0.5 * ((fb_gm_y - fc_gm_y) + (fa_gm_y - fb_gm_y))
            elif mode == 2:
                v_gm_x = fa_gm_x - fb_gm_x
                v_gm_y = fa_gm_y - fb_gm_y
            else:
                v_gm_x = v_gm_y = 0.0

            # --- Gemeinsames (radiales) Gewicht ---
            dx = fa_sm_x - fa_gm_x
            dy = fa_sm_y - fa_gm_y
            dist = (dx * dx + dy * dy) ** 0.5
            w = 1.0 / (1e-6 + dist)

            weighted_velocities_x.append((v_gm_x, w))
            weighted_velocities_y.append((v_gm_y, w))

        # Wenn keine gültigen Daten → skip
        if not weighted_velocities_x or not weighted_velocities_y:
            continue

        # ----------------------------------------------------------
        # Robuste Mittelung – obere und untere 10 % der Werte trimmen
        # ----------------------------------------------------------
        def robust_weighted_mean(values_with_weights):
            if len(values_with_weights) < 5:
                # Zu wenig Daten → normales gewichtetes Mittel
                total_w = sum(w for _, w in values_with_weights)
                return sum(v * w for v, w in values_with_weights) / total_w if total_w != 0 else 0.0

            # Sortiere nach Geschwindigkeit (v), ignoriere Ausreißer
            sorted_vals = sorted(values_with_weights, key=lambda x: x[0])
            n = len(sorted_vals)
            cut = max(1, int(0.1 * n))
            trimmed = sorted_vals[cut:-cut] if n > 2 * cut else sorted_vals

            total_w = sum(w for _, w in trimmed)
            return sum(v * w for v, w in trimmed) / total_w if total_w != 0 else 0.0

        avg_vx = robust_weighted_mean(weighted_velocities_x)
        avg_vy = robust_weighted_mean(weighted_velocities_y)

        # Sanfte Positionskorrektur (additiv)
        new_x = fb_sm_x + avg_vx
        new_y = fb_sm_y + avg_vy

        # Kalibrierung + Dämpfung
        calib_x = 0.5 * (fa_sm_x + new_x)
        calib_y = 0.5 * (fa_sm_y + new_y)

        final_x = max(new_x * 0.95, min(new_x * 1.05, calib_x))
        final_y = max(new_y * 0.95, min(new_y * 1.05, calib_y))

        # In Szene zurückschreiben
        set_marker_position(sm, frame_a, final_x, final_y)

    print(f"[Marker Correction] Marker-Korrektur abgeschlossen – Basis: {mode}-Frame (robust).")
