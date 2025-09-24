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


def analyze_rois(clip: Any, grid: tuple[int, int] = (4, 6), frame_img: Any = None, prev_frame_img: Any = None) -> dict:
    """Return {roi_id: {bbox, texture, motion, divergence, empty_tiles, tiles}}.

    Wenn `frame_img` (und optional `prev_frame_img`) als NumPy-Arrays übergeben werden,
    berechnen wir echte Tile-basierte Texture- und Motion-Scores. Falls OpenCV (`cv2`) vorhanden
    wird, nutzen wir dessen Laplacian für einen Texture-Score; sonst verwenden wir eine
    Gradienten-basierte Heuristik (reine NumPy-Implementierung).

    Coverage-Löcher = Tiles mit texture < 0.3 (oder low motion), Platzhalter-Thresholds.
    """
    w, h = _clip_size(clip)
    nx, ny = grid
    tile_w = max(1, w // nx)
    tile_h = max(1, h // ny)
    tiles = np.zeros((ny, nx), dtype=[('texture', 'f4'), ('motion', 'f4')])

    # If frame images provided, compute real texture & motion per tile.
    img = None
    prev = None
    try:
        import numpy as _np
        img = _np.asarray(frame_img) if frame_img is not None else None
        prev = _np.asarray(prev_frame_img) if prev_frame_img is not None else None
    except Exception:
        img = None
        prev = None

    use_cv2 = False
    try:
        import cv2  # type: ignore
        use_cv2 = True
    except Exception:
        use_cv2 = False

    if img is None:
        # Fallback to previous pseudo-scores when no image is available
        for iy in range(ny):
            for ix in range(nx):
                t = 0.4 + 0.2 * ((ix + iy) % 2)
                m = 0.5 + 0.1 * ((ix - iy) % 2)
                tiles[iy, ix]["texture"] = float(t)
                tiles[iy, ix]["motion"] = float(m)
    else:
        # Ensure grayscale float image in range 0..1
        try:
            if img.ndim == 3 and img.shape[2] >= 3:
                # convert RGB -> gray
                img_gray = img[..., :3].astype(float)
                img_gray = (0.299 * img_gray[..., 0] + 0.587 * img_gray[..., 1] + 0.114 * img_gray[..., 2])
            else:
                img_gray = img.astype(float)
            # normalize to 0..1 if values appear in 0..255
            if img_gray.max() > 1.5:
                img_gray = img_gray / 255.0
        except Exception:
            img_gray = np.zeros((h, w), dtype=float)

        prev_gray = None
        if prev is not None:
            try:
                if prev.ndim == 3 and prev.shape[2] >= 3:
                    pgray = prev[..., :3].astype(float)
                    prev_gray = (0.299 * pgray[..., 0] + 0.587 * pgray[..., 1] + 0.114 * pgray[..., 2])
                else:
                    prev_gray = prev.astype(float)
                if prev_gray.max() > 1.5:
                    prev_gray = prev_gray / 255.0
            except Exception:
                prev_gray = None

        H, W = img_gray.shape[:2]
        # Resize or crop to declared clip size if mismatch
        if (W, H) != (w or W, h or H):
            # Try to respect clip size; but don't fail on mismatch
            try:
                # simple crop/resize via slicing if larger
                img_gray = img_gray[: (h or H), : (w or W)]
                if prev_gray is not None:
                    prev_gray = prev_gray[: (h or H), : (w or W)]
                H, W = img_gray.shape[:2]
            except Exception:
                pass

        tile_w = max(1, W // nx)
        tile_h = max(1, H // ny)

        # Precompute gradient-based texture or use cv2.Laplacian
        if use_cv2:
            try:
                import cv2 as _cv
                lap = _cv.Laplacian((img_gray * 255.0).astype(_cv.CV_8U), _cv.CV_64F)
                tex_map = np.abs(lap) / 255.0
            except Exception:
                use_cv2 = False

        if not use_cv2:
            # gradient magnitude heuristic (NumPy-only)
            gy, gx = np.gradient(img_gray)
            grad_mag = np.hypot(gx, gy)
            tex_map = grad_mag

        # Motion map: abs diff if previous frame present
        if prev_gray is not None:
            mot_map = np.abs(img_gray - prev_gray)
        else:
            mot_map = np.zeros_like(img_gray)

        # Aggregate per tile and normalize to 0..1
        tvals = []
        mvals = []
        for iy in range(ny):
            for ix in range(nx):
                y0 = iy * tile_h
                x0 = ix * tile_w
                y1 = min(H, y0 + tile_h)
                x1 = min(W, x0 + tile_w)
                region_tex = tex_map[y0:y1, x0:x1]
                region_mot = mot_map[y0:y1, x0:x1]
                tval = float(np.mean(region_tex)) if region_tex.size else 0.0
                mval = float(np.mean(region_mot)) if region_mot.size else 0.0
                tvals.append(tval)
                mvals.append(mval)

        tvals = np.array(tvals, dtype=float)
        mvals = np.array(mvals, dtype=float)
        # Normalize by max or mean to get relative 0..1 scores
        tmax = float(np.max(tvals)) if tvals.size else 1.0
        mmax = float(np.max(mvals)) if mvals.size else 1.0
        tnorm = tvals / (tmax or 1.0)
        mnorm = mvals / (mmax or 1.0)

        # write back into tiles
        k = 0
        for iy in range(ny):
            for ix in range(nx):
                tiles[iy, ix]["texture"] = float(tnorm[k])
                tiles[iy, ix]["motion"] = float(mnorm[k])
                k += 1
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

    # Telemetrie: log cluster summary if telemetry is available
    try:
        from .telemetry import log_batch
        try:
            log_batch("roi.cluster", "cluster_summary", {"roi_id": int(roi_id), "clusters": len(out_clusters), "members": sum(len(c.get("inliers", [])) for c in out_clusters)})
        except Exception:
            pass
    except Exception:
        pass

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