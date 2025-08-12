import bpy
import statistics, math

for cell, items in buckets.items():
    if not items:
        continue

    # Bewegungsbeträge
    v_mags = [math.hypot(vx, vy) for _, _, vx, vy in items]
    median_mag = statistics.median(v_mags)
    abs_dev = [abs(v - median_mag) for v in v_mags]
    mad = statistics.median(abs_dev) or 1e-6  # Division durch Null vermeiden

    # Schwelle setzen (z. B. 3 * MAD)
    thr = median_mag + 3.0 * mad

    for (tr, f, vx, vy), mag in zip(items, v_mags):
        if mag > thr:
            for ff in (f - 1, f, f + 1):
                if tr.markers.find_frame(ff):
                    tr.markers.delete_frame(ff)
                    deleted += 1

def multiscale_temporal_grid_clean(context, area, region, space, tracks, frame_range,
                                   width, height, grid=(6, 6),
                                   start_delta=None, min_delta=3,
                                   outlier_q=0.9, hysteresis_hits=2, min_cell_items=4):
    scene = context.scene
    clip = getattr(space, "clip", None)
    if not clip or not tracks:
        return 0

    # Fallback, falls Operator keinen Wert setzt
    if start_delta is None:
        frames_track = getattr(scene, "frames_track", None)
        range_len = int(frame_range[1] - frame_range[0] + 1)
        if frames_track:
            start_delta = max(min_delta * 2, frames_track // 2)
        else:
            start_delta = max(min_delta * 2, range_len // 6)
        start_delta = min(start_delta, max(min_delta * 4, range_len // 2))

    # Δ-Pyramide (ASCII)
    D0 = int(max((start_delta), min_delta * 2))
    if D0 > max(24, min_delta * 4):
        D0 = max(24, min_delta * 4)

    deltas = []
    D = D0
    while D >= int(min_delta):
        deltas.append(D)
        D //= 2

    frame_start, frame_end = int(frame_range[0]), int(frame_range[1])

    # ---------- Helpers ----------
    # Cache für Marker-Positionen in Pixeln
    pos_cache = {}
    def pos(t, f):
        k = (t.name, f)
        if k in pos_cache:
            return pos_cache[k]
        m = t.markers.find_frame(f)
        if m:
            xy = (m.co[0] * width, m.co[1] * height)
            pos_cache[k] = xy
            return xy
        return None

    gx, gy = grid
    cell_w, cell_h = width / gx, height / gy
    def cell_idx(xy):
        x, y = xy
        cx = min(gx - 1, max(0, int(x // cell_w)))
        cy = min(gy - 1, max(0, int(y // cell_h)))
        return (cx, cy)

    # ---------- Phase A/B: Coarse→Fine Drift-Erkennung ----------
    # Hysterese über Skalen: (track_name, frame) -> Trefferanzahl
    hits = {}

    # Nur Tracks berücksichtigen, die genug Marker über Fenster haben
    valid_tracks = [t for t in tracks if len(t.markers) >= (2 * min_delta + 1)]

    for Δ in deltas:
        for f in range(frame_start + Δ, frame_end - Δ):
            # Buckets je Zelle
            buckets = {}
            for t in valid_tracks:
                p1 = pos(t, f - Δ); p0 = pos(t, f); p2 = pos(t, f + Δ)
                if not (p1 and p0 and p2):
                    continue
                c = cell_idx(p0)
                buckets.setdefault(c, []).append((t, p1, p2, f))

            # Zellweise Median-Flow und Residuen
            for c, items in buckets.items():
                if len(items) < min_cell_items:
                    continue

                flows = [(p2[0] - p1[0], p2[1] - p1[1]) for _, p1, p2, _ in items]
                mx = sorted([fx for fx, _ in flows])[len(flows) // 2]
                my = sorted([fy for _, fy in flows])[len(flows) // 2]

                residuals = []
                for t, p1, p2, fcur in items:
                    dx = (p2[0] - p1[0]) - mx
                    dy = (p2[1] - p1[1]) - my
                    r = (dx * dx + dy * dy) ** 0.5
                    residuals.append((t, fcur, r))

                # robuste Schwelle via Perzentil
                rs = sorted(r for _, _, r in residuals)
                idx = int(max(0, min(len(rs) - 1, len(rs) * float(outlier_q))))
                thr = rs[idx]

                for t, fcur, r in residuals:
                    if r >= thr:
                        key = (t.name, fcur)
                        hits[key] = hits.get(key, 0) + 1

    # Coarse/Fine-Kandidaten → zu löschende Frames (um f herum ±1)
    coarse_delete = {}
    for (tname, f), n in hits.items():
        if n >= int(hysteresis_hits):
            coarse_delete.setdefault(tname, set()).update({f - 1, f, f + 1})

    deleted_coarse = 0
    if coarse_delete:
        # Rebind aktuelle RNA-Objekte per Name, dann im gültigen Kontext löschen
        tracks_by_name = {t.name: t for t in tracks}
        with context.temp_override(area=area, region=region, space_data=space):
            for tname, frames in coarse_delete.items():
                t = tracks_by_name.get(tname)
                if not t:
                    continue
                for f in sorted(frames):
                    if t.markers.find_frame(f):
                        t.markers.delete_frame(f)
                        deleted_coarse += 1
            try:
                region.tag_redraw()
            except Exception:
                pass

    # ---------- Phase C: Micro-Pass (3-Frame-Ausreißer) ----------
    def _micro_outlier_pass():
        import math, statistics
        deleted = 0
        with context.temp_override(area=area, region=region, space_data=space):
            cell_w, cell_h = width / gx, height / gy
    
            for fi in range(frame_start + 1, frame_end - 1):
                buckets = {}
                for tr in tracks:
                    m1 = tr.markers.find_frame(fi - 1)
                    m2 = tr.markers.find_frame(fi)
                    m3 = tr.markers.find_frame(fi + 1)
                    if not (m1 and m2 and m3):
                        continue
    
                    x = m2.co[0] * width
                    y = m2.co[1] * height
                    cx = min(gx - 1, max(0, int(x // cell_w)))
                    cy = min(gy - 1, max(0, int(y // cell_h)))
    
                    vx = (m2.co[0] - m1.co[0]) + (m3.co[0] - m2.co[0])
                    vy = (m2.co[1] - m1.co[1]) + (m3.co[1] - m2.co[1])
    
                    buckets.setdefault((cx, cy), []).append((tr, fi, vx, vy))
    
                for _, items in buckets.items():
                    # Zellen mit zu wenig Stichproben überspringen
                    if len(items) < max(3, min_cell_items):
                        continue
    
                    # Bewegungsbeträge (euklidisch)
                    v_mags = [math.hypot(vx, vy) for _, _, vx, vy in items]
                    med = statistics.median(v_mags)
                    mad = statistics.median([abs(v - med) for v in v_mags]) or 1e-6
                    thr = med + 3.0 * mad  # robustere Schwelle
    
                    for (tr, f, vx, vy), mag in zip(items, v_mags):
                        if mag > thr:
                            for ff in (f - 1, f, f + 1):
                                if tr.markers.find_frame(ff):
                                    tr.markers.delete_frame(ff)
                                    deleted += 1
            try:
                region.tag_redraw()
            except Exception:
                pass
        return deleted


    deleted_micro = _micro_outlier_pass()
    return int(deleted_coarse) + int(deleted_micro)
