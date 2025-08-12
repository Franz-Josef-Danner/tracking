# Helper/multiscale_temporal_grid_clean.py

import bpy

def multiscale_temporal_grid_clean(context, area, region, space, tracks, frame_range,
                                   width, height, grid=(6, 6),
                                   start_delta=None, min_delta=3,
                                   outlier_q=0.9, hysteresis_hits=2, min_cell_items=4):
    """
    Erweiterung für den Grid-Error-Clean:
    Erkennt glatte Drift über große Zeitfenster via Zell-Median-Flow
    und löscht gezielt Markerframes (konservativ).
    """
    scene = context.scene
    clip = space.clip
    if not clip or not tracks:
        return 0

    # Δ-Pyramide erstellen
    ft = int(scene.get("frames_track", 12))
    Δ = int(max((start_delta or ft // 2), 6))
    deltas = []
    while Δ >= min_delta:
        deltas.append(Δ)
        Δ //= 2

    frame_start, frame_end = map(int, frame_range)

    # Positionen cachen
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

    # Grid-Berechnung
    gx, gy = grid
    cell_w, cell_h = width / gx, height / gy
    def cell_idx(xy):
        x, y = xy
        return (min(gx - 1, max(0, int(x // cell_w))),
                min(gy - 1, max(0, int(y // cell_h))))

    hits = {}  # (track, frame) -> Trefferanzahl

    for Δ in deltas:
        for f in range(frame_start + Δ, frame_end - Δ):
            buckets = {}
            for t in tracks:
                p1 = pos(t, f - Δ); p0 = pos(t, f); p2 = pos(t, f + Δ)
                if not (p1 and p0 and p2):
                    continue
                c = cell_idx(p0)
                buckets.setdefault(c, []).append((t, p1, p2, f))

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

                rs = sorted(r for _, _, r in residuals)
                thr = rs[int(max(0, min(len(rs) - 1, len(rs) * outlier_q)))]

                for t, fcur, r in residuals:
                    if r >= thr:
                        key = (t.name, fcur)
                        hits[key] = hits.get(key, 0) + 1

    # Marker löschen
    to_delete = {}
    for (tname, f), n in hits.items():
        if n >= hysteresis_hits:
            to_delete.setdefault(tname, set()).update({f - 1, f, f + 1})

    deleted = 0
    if to_delete:
        tracks_by_name = {t.name: t for t in tracks}
        with context.temp_override(area=area, region=region, space_data=space):
            for tname, frames in to_delete.items():
                t = tracks_by_name.get(tname)
                if not t:
                    continue
                for f in sorted(frames):
                    if t.markers.find_frame(f):
                        t.markers.delete_frame(f)
                        deleted += 1
            region.tag_redraw()
    return deleted
