# STRM/ROI-Analyse & Priorisierung

from __future__ import annotations
from typing import Any, Dict, Tuple, List
import math
import numpy as np

BBox = Tuple[int, int, int, int]


def _clip_size(clip: Any) -> Tuple[int, int]:
    try:
        w, h = getattr(clip, "size", (0, 0))
        return int(w or 0), int(h or 0)
    except Exception:
        return 0, 0


def analyze_rois(clip: Any, grid: tuple[int, int] = (4, 6)) -> dict:
    """Return {roi_id: {bbox, texture, motion, divergence, empty_tiles, tiles}}.

    STRM: Zerlegt das Bild in Tiles und berechnet pro Tile einfache Texture-/Motion-Scores.
    Coverage-Löcher = Tiles mit Score < 0.3 (Platzhalter-Logik).
    """
    w, h = _clip_size(clip)
    nx, ny = grid
    tile_w = max(1, w // nx)
    tile_h = max(1, h // ny)
    tiles = np.zeros((ny, nx), dtype=[('texture', 'f4'), ('motion', 'f4')])
    # Platzhalter: fülle Tiles mit Pseudo-Scores (später: echte Bilddaten)
    for iy in range(ny):
        for ix in range(nx):
            # Simuliere Textur und Bewegung (z.B. als Funktion der Tile-Position)
            t = 0.4 + 0.2 * ((ix + iy) % 2)  # Schachbrettmuster
            m = 0.5 + 0.1 * ((ix - iy) % 2)
            tiles[iy, ix]["texture"] = t
            tiles[iy, ix]["motion"] = m
    # Coverage-Löcher: Tiles mit texture < 0.3
    empty_tiles = [(ix, iy) for iy in range(ny) for ix in range(nx) if tiles[iy, ix]["texture"] < 0.3]
    roi: Dict[str, Any] = {
        "bbox": (0, 0, int(w), int(h)),
        "texture": float(np.mean(tiles['texture'])),
        "motion": float(np.mean(tiles['motion'])),
        "divergence": 0.0,
        "empty_tiles": empty_tiles,
        "tiles": tiles,
        "grid": (nx, ny),
    }
    return {0: roi}


def cluster_tracks(roi_id, window: int = 30) -> list:
    """Return clusters: [{id, inliers: [track_ids], feats: {...}}].

    Platzhalter: gibt leere Liste zurück. Später per DBSCAN/HDBSCAN ergänzen.
    """
    try:
        # Best-effort: versuche Blender-API zu verwenden. Falls nicht verfügbar,
        # liefere leere Liste (außerhalb von Blender oft gewünscht).
        import bpy  # type: ignore
    except Exception:
        return []

    try:
        clip = getattr(bpy.context, "edit_movieclip", None) or getattr(getattr(bpy.context, "space_data", None), "clip", None)
    except Exception:
        clip = None
    if clip is None:
        return []

    tracks = getattr(getattr(clip, "tracking", None), "tracks", None)
    if not tracks:
        return []

    # Gather per-track last-known position and simple motion features
    width, height = _clip_size(clip)
    track_infos = []
    for idx, t in enumerate(tracks):
        try:
            # Heuristiken: track gehört zur roi, wenn custom prop `roi_id` stimmt,
            # oder Name enthält die ID, oder Track ist selektiert.
            belongs = False
            try:
                v = getattr(t, "roi_id", None)
                if v is not None and str(int(v)) == str(roi_id):
                    belongs = True
            except Exception:
                pass
            try:
                name = getattr(t, "name", "") or ""
                if f"{roi_id}" in name or name.endswith(f"_{roi_id}") or name.startswith(f"roi_{roi_id}"):
                    belongs = True
            except Exception:
                pass
            try:
                if bool(getattr(t, "select", False)):
                    belongs = True
            except Exception:
                pass

            # If none matched, skip this track (we avoid clustering unrelated tracks)
            if not belongs:
                continue

            # Extract markers (best-effort)
            markers = []
            try:
                markers = list(getattr(t, "markers") or [])
            except Exception:
                try:
                    markers = list(getattr(t, "tracked_points") or [])
                except Exception:
                    markers = []

            if not markers:
                continue

            # choose most recent marker(s)
            markers_sorted = sorted(markers, key=lambda m: int(getattr(m, "frame", -999999)))
            cur = markers_sorted[-1]
            prev = markers_sorted[-2] if len(markers_sorted) >= 2 else None

            def _co(m):
                try:
                    c = getattr(m, "co", None) or getattr(m, "pos", None) or None
                    if c is None:
                        return None
                    # c usually normalized (0..1) -> convert to pixels if clip size known
                    x = float(c[0]) * (width or 1)
                    y = float(c[1]) * (height or 1)
                    return (x, y)
                except Exception:
                    return None

            p1 = _co(cur)
            p0 = _co(prev) if prev is not None else None
            if p1 is None:
                continue

            # residual / error estimate
            try:
                residual = float(getattr(t, "error", getattr(t, "average_error", 0.0) or 0.0) or 0.0)
            except Exception:
                try:
                    residual = float(getattr(cur, "error", 0.0) or 0.0)
                except Exception:
                    residual = 0.0

            # estimate motion features
            dx = dy = 0.0
            rot = 0.0
            scale = 1.0
            try:
                if p0 is not None:
                    dx = p1[0] - p0[0]
                    dy = p1[1] - p0[1]
                # scale / rot from pattern_corners if available
                pc_cur = getattr(cur, "pattern_corners", None)
                pc_prev = getattr(prev, "pattern_corners", None) if prev is not None else None
                def _area(corners):
                    try:
                        pts = list(corners)
                        if len(pts) >= 4:
                            a = 0.0
                            for i in range(4):
                                x1, y1 = float(pts[i][0]), float(pts[i][1])
                                x2, y2 = float(pts[(i + 1) % 4][0]), float(pts[(i + 1) % 4][1])
                                a += x1 * y2 - x2 * y1
                            return abs(a) / 2.0
                    except Exception:
                        return 0.0
                    return 0.0
                def _angle(corners):
                    try:
                        pts = list(corners)
                        cx = sum(p[0] for p in pts) / len(pts)
                        cy = sum(p[1] for p in pts) / len(pts)
                        dx0 = pts[0][0] - cx
                        dy0 = pts[0][1] - cy
                        return math.atan2(dy0, dx0)
                    except Exception:
                        return 0.0

                if pc_prev is not None and pc_cur is not None:
                    a0 = _area(pc_prev) or 1.0
                    a1 = _area(pc_cur) or 1.0
                    scale = (a1 / a0) if a0 else 1.0
                    rot = float(_angle(pc_cur) - _angle(pc_prev))
            except Exception:
                pass

            track_infos.append({
                "track_id": getattr(t, "name", str(idx)),
                "pos": p1,
                "dx": dx,
                "dy": dy,
                "scale": float(scale),
                "rot": float(rot),
                "residual": float(residual),
            })
        except Exception:
            # Skip problematic tracks
            continue

    if not track_infos:
        return []

    # Clustering: try HDBSCAN -> sklearn.DBSCAN -> fallback single-link connectivity
    pts = np.array([t["pos"] for t in track_infos], dtype=float)
    n = len(pts)
    # eps: a fraction of the smallest image side, clipped to sensible px
    eps = max(8.0, min(width or 0, height or 0) * 0.03)

    labels = None
    # Try HDBSCAN if available (better for variable density)
    try:
        import hdbscan  # type: ignore
        labels = hdbscan.HDBSCAN(min_cluster_size=max(2, int(n * 0.05))).fit_predict(pts)
    except Exception:
        labels = None

    # Try sklearn DBSCAN as next option
    if labels is None:
        try:
            from sklearn.cluster import DBSCAN  # type: ignore
            labels = DBSCAN(eps=eps, min_samples=1).fit_predict(pts)
        except Exception:
            labels = None

    out_clusters = []

    if labels is None:
        # Fallback: single-link connectivity (original approach)
        adj = [[] for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                d = float(np.hypot(pts[i, 0] - pts[j, 0], pts[i, 1] - pts[j, 1]))
                if d <= eps:
                    adj[i].append(j)
                    adj[j].append(i)

        # connected components
        visited = [False] * n
        clusters = []
        for i in range(n):
            if visited[i]:
                continue
            stack = [i]
            comp = []
            visited[i] = True
            while stack:
                u = stack.pop()
                comp.append(u)
                for v in adj[u]:
                    if not visited[v]:
                        visited[v] = True
                        stack.append(v)
            clusters.append(comp)

        for cid, comp in enumerate(clusters):
            members = [track_infos[k] for k in comp]
            inlier_ids = [m.get("track_id") for m in members]
            inliers_count = len(members)
            rms_vals = [m.get("residual", 0.0) for m in members]
            rot_vals = [m.get("rot", 0.0) for m in members]
            scale_vals = [m.get("scale", 1.0) for m in members]
            jump_mags = [math.hypot(float(m.get("dx", 0.0)), float(m.get("dy", 0.0))) for m in members]

            stats = {
                # convert rotation spread to degrees for heuristics in motion_model
                "sigma_rot": float(np.std(rot_vals) * (180.0 / math.pi)) if rot_vals else 0.0,
                "sigma_scale": float(np.std([s - 1.0 for s in scale_vals])) if scale_vals else 0.0,
                "phi_shear": 0.0,
                "parallax": float(np.std(jump_mags)) if jump_mags else 0.0,
                "inliers": float(inliers_count),
                "rms": float(np.mean(rms_vals)) if rms_vals else 1.0,
                "outliers": 0.0,
            }

            out_clusters.append({"id": cid, "inliers": inlier_ids, "stats": stats})
    else:
        # Build clusters from labels
        labels = np.array(labels, dtype=int)
        unique = sorted(set(int(x) for x in labels if x >= 0))
        label_to_idx = {lab: i for i, lab in enumerate(unique)}
        groups = {lab: [] for lab in unique}
        noise = [i for i, lab in enumerate(labels) if lab == -1]
        for i, lab in enumerate(labels):
            if lab >= 0:
                groups[int(lab)].append(i)
            else:
                # treat noise as singleton clusters
                groups.setdefault(f"noise_{i}", []).append(i)

        cid = 0
        for lab, comp in groups.items():
            members = [track_infos[k] for k in comp]
            inlier_ids = [m.get("track_id") for m in members]
            inliers_count = len(members)
            rms_vals = [m.get("residual", 0.0) for m in members]
            rot_vals = [m.get("rot", 0.0) for m in members]
            scale_vals = [m.get("scale", 1.0) for m in members]
            jump_mags = [math.hypot(float(m.get("dx", 0.0)), float(m.get("dy", 0.0))) for m in members]

            stats = {
                "sigma_rot": float(np.std(rot_vals) * (180.0 / math.pi)) if rot_vals else 0.0,
                "sigma_scale": float(np.std([s - 1.0 for s in scale_vals])) if scale_vals else 0.0,
                "phi_shear": 0.0,
                "parallax": float(np.std(jump_mags)) if jump_mags else 0.0,
                "inliers": float(inliers_count),
                "rms": float(np.mean(rms_vals)) if rms_vals else 1.0,
                "outliers": 0.0,
            }

            out_clusters.append({"id": cid, "inliers": inlier_ids, "stats": stats})
            cid += 1

    return out_clusters


def prioritize_rois(rois: dict) -> list:
    """Return ROI-Ids in sinnvoller Abarbeitungsreihenfolge.

    Heuristik: sortiere nach (motion + texture) absteigend, dann Flächengröße.
    """
    if not rois:
        return []

    def key(item):
        roi_id, info = item
        tex = float(info.get("texture", 0.0) or 0.0)
        mot = float(info.get("motion", 0.0) or 0.0)
        bbox: BBox = info.get("bbox", (0, 0, 0, 0))
        area = max(1, int(bbox[2]) * int(bbox[3])) if isinstance(bbox, (tuple, list)) and len(bbox) >= 4 else 1
        return (mot + tex, area)

    sorted_items: List[Tuple[int, Dict]] = sorted(rois.items(), key=key, reverse=True)
    return [roi_id for roi_id, _ in sorted_items]