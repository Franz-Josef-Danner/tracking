import numpy as np


def extract_grayscale_frames(clip, start=0, count=10):
    """Extrahiere Grayscale-Frames aus einem MovieClip"""
    size = clip.size
    frames = []

    # Sicherheit: clamp count
    count = max(1, int(count))

    for i in range(count):
        frame = start + i
        # Blender API: set current frame and get image data
        try:
            img = clip.frame_to_image(frame)
        except Exception:
            img = None
        if img is None:
            continue

        # img.pixels ist flach (rgba), Größe: width*height*4
        pixels = np.array(img.pixels[:], dtype=np.float32)
        pixels = pixels.reshape((size[1], size[0], 4))
        # Luminanz-Umrechnung
        gray = 0.2126 * pixels[..., 0] + 0.7152 * pixels[..., 1] + 0.0722 * pixels[..., 2]
        frames.append(gray.astype(np.float32))

    return frames if frames else None


def analyze_strm(frames, tile_rows=4, tile_cols=6):
    """Berechne Texture-, Motion- und Divergenz-Score pro Tile"""
    if not frames:
        return []

    # Normierung: sicherstellen gleiche Größe/Typ
    base = np.asarray(frames[0], dtype=np.float32)
    h, w = base.shape

    tile_rows = max(1, int(tile_rows))
    tile_cols = max(1, int(tile_cols))

    tile_h, tile_w = h // tile_rows, w // tile_cols
    tile_h = max(1, tile_h)
    tile_w = max(1, tile_w)

    # Stapel als (T, H, W)
    stack = [np.asarray(f, dtype=np.float32) for f in frames]
    results = []

    for ty in range(tile_rows):
        for tx in range(tile_cols):
            y0 = ty * tile_h
            y1 = h if ty == tile_rows - 1 else (ty + 1) * tile_h
            x0 = tx * tile_w
            x1 = w if tx == tile_cols - 1 else (tx + 1) * tile_w
            tile_stack = np.stack([f[y0:y1, x0:x1] for f in stack], axis=0)

            # Texture Score: Standardabweichung über alle Pixel im ersten Frame
            texture = float(np.std(tile_stack[0]))

            # Motion Score: mittlerer Frame-Differenzbetrag
            if tile_stack.shape[0] > 1:
                diff = np.abs(np.diff(tile_stack, axis=0))
                motion = float(np.mean(diff))
                div = float(np.var(diff))
                # Flicker: Std der mittleren Helligkeit pro Frame (temporale Helligkeitsschwankung)
                per_frame_mean = tile_stack.reshape(tile_stack.shape[0], -1).mean(axis=1)
                flicker = float(np.std(per_frame_mean))
            else:
                motion = 0.0
                div = 0.0
                flicker = 0.0

            # Koordinaten für Overlay (Blender-View: Ursprung unten links)
            y0_bl = float(h - y1)
            y1_bl = float(h - y0)

            results.append({
                'texture': texture,
                'motion': motion,
                'div': div,
                'flicker': flicker,
                'tile': (ty, tx),
                'coords': (float(x0), y0_bl, float(x1), y1_bl),
            })

    return results


def compute_tile_coords(clip, tile_rows=4, tile_cols=6):
    """Berechne (x0, y0, x1, y1) pro Tile in Clip-Pixelkoordinaten.
    Deckt den gesamten Bereich ab (letzte Zeile/Spalte bis zum Rand)."""
    width, height = clip.size
    tile_rows = max(1, int(tile_rows))
    tile_cols = max(1, int(tile_cols))

    tile_w = max(1, width // tile_cols)
    tile_h = max(1, height // tile_rows)
    tiles = []

    for ty in range(tile_rows):
        for tx in range(tile_cols):
            x0 = tx * tile_w
            y0 = ty * tile_h
            x1 = width if tx == tile_cols - 1 else (tx + 1) * tile_w
            y1 = height if ty == tile_rows - 1 else (ty + 1) * tile_h
            tiles.append((float(x0), float(y0), float(x1), float(y1)))

    return tiles


def select_top_tiles_as_rois(tiles, score_type="motion", top_n=6, min_distance_px=0):
    """Wählt Top-N Tiles basierend auf Score (motion/texture/div/flicker), optional mit Mindestabstand.
    Erwartet Tiles mit Schlüsseln: 'coords' und Score-Felder.
    Gibt ROIs als Dicts mit 'coords', 'center', 'score' zurück."""
    if not tiles:
        return []

    # Sortiere absteigend nach gewünschtem Score
    sorted_tiles = sorted(tiles, key=lambda t: float(t.get(score_type, 0.0)), reverse=True)

    selected_rois = []
    for tile in sorted_tiles:
        if 'coords' not in tile:
            continue
        x0, y0, x1, y1 = tile['coords']
        cx = 0.5 * (x0 + x1)
        cy = 0.5 * (y0 + y1)

        if min_distance_px > 0:
            too_close = False
            for roi in selected_rois:
                rcx, rcy = roi['center']
                dx = cx - rcx
                dy = cy - rcy
                if (dx * dx + dy * dy) ** 0.5 < float(min_distance_px):
                    too_close = True
                    break
            if too_close:
                continue

        selected_rois.append({
            'coords': (float(x0), float(y0), float(x1), float(y1)),
            'center': (float(cx), float(cy)),
            'score': float(tile.get(score_type, 0.0)),
        })

        if len(selected_rois) >= int(top_n):
            break

    return selected_rois


def extract_single_grayscale_frame(clip, frame_number):
    """Extrahiere ein einzelnes Frame als 2D-Grayscale-Array in uint8 [0,255]."""
    size = clip.size
    try:
        img = clip.frame_to_image(int(frame_number))
    except Exception:
        img = None
    if img is None:
        return None
    pixels = np.array(img.pixels[:], dtype=np.float32)
    pixels = pixels.reshape((size[1], size[0], 4))  # H, W, RGBA
    gray = 0.2126 * pixels[..., 0] + 0.7152 * pixels[..., 1] + 0.0722 * pixels[..., 2]
    gray = np.clip(gray * 255.0, 0.0, 255.0).astype(np.uint8)
    return gray


def detect_features_in_roi(gray_frame, roi, max_features=100, quality=0.01, min_distance=5):
    """Finde Features innerhalb eines Rechtecks.
    Erwartet roi['coords'] im Overlay-Koordinatensystem (unten-links Ursprung).
    Konvertiert intern in Bild-Indexkoordinaten (oben-links Ursprung) für OpenCV.
    Gibt Punkte in Overlay-Koordinaten (unten-links Ursprung) zurück.
    """
    # Lazy import, um Add-on-Registrierung ohne cv2 zu ermöglichen
    try:
        import cv2  # type: ignore
    except Exception as e:
        raise RuntimeError("OpenCV (cv2) ist nicht installiert: " + str(e))

    h, w = gray_frame.shape[:2]
    x0_bl, y0_bl, x1_bl, y1_bl = roi.get('coords', (0.0, 0.0, 0.0, 0.0))

    # In TL-Koordinaten für Array-Slicing umrechnen
    x0_tl = int(np.clip(x0_bl, 0, w - 1))
    x1_tl = int(np.clip(x1_bl, 1, w))
    y0_tl = int(np.clip(h - y1_bl, 0, h - 1))
    y1_tl = int(np.clip(h - y0_bl, 1, h))

    if x1_tl <= x0_tl or y1_tl <= y0_tl:
        return []

    roi_img = gray_frame[y0_tl:y1_tl, x0_tl:x1_tl]
    roi_img = np.ascontiguousarray(roi_img, dtype=np.uint8)

    keypoints = cv2.goodFeaturesToTrack(
        roi_img,
        maxCorners=int(max_features),
        qualityLevel=float(quality),
        minDistance=float(min_distance),
        useHarrisDetector=False
    )

    results = []
    if keypoints is not None:
        for pt in keypoints:
            x, y = pt[0]
            gx_tl = float(x0_tl) + float(x)
            gy_tl = float(y0_tl) + float(y)
            # zurück in BL-View-Koordinaten
            gy_bl = float(h) - gy_tl
            results.append((float(gx_tl), float(gy_bl)))

    return results


def extract_grayscale_frames_range(clip, start_frame, count):
    """Extrahiere eine Folge von Grayscale-Frames als uint8 [0,255]."""
    size = clip.size
    frames = []
    for i in range(int(count)):
        f = int(start_frame) + i
        try:
            img = clip.frame_to_image(f)
        except Exception:
            img = None
        if img is None:
            continue
        pixels = np.array(img.pixels[:], dtype=np.float32).reshape((size[1], size[0], 4))
        gray = 0.2126 * pixels[..., 0] + 0.7152 * pixels[..., 1] + 0.0722 * pixels[..., 2]
        frames.append(np.clip(gray * 255.0, 0, 255).astype(np.uint8))
    return frames


def track_markers_lk(gray_frames, initial_points, lk_params=None):
    """Tracke Marker über eine Sequenz von Frames mit Lucas-Kanade Optical Flow.
    initial_points erwartet in Overlay-Koordinaten (unten-links Ursprung),
    Rückgabe: Liste von Trajektorien in Overlay-Koordinaten (BL), None für Ausfall.
    """
    if lk_params is None:
        lk_params = dict(
            winSize=(15, 15),
            maxLevel=2,
            criteria=(1 | 2, 10, 0.03),  # cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT
        )

    # Lazy import
    try:
        import cv2  # type: ignore
    except Exception as e:
        raise RuntimeError("OpenCV (cv2) ist nicht installiert: " + str(e))

    num_frames = len(gray_frames)
    if num_frames < 2 or not initial_points:
        return []

    h, w = gray_frames[0].shape[:2]

    # BL -> TL für LK
    pts_tl = []
    for (x_bl, y_bl) in initial_points:
        x_tl = float(x_bl)
        y_tl = float(h) - float(y_bl)
        pts_tl.append((x_tl, y_tl))

    p0 = np.array(pts_tl, dtype=np.float32).reshape(-1, 1, 2)
    tracks = [[(float(x), float(y))] for (x, y) in initial_points]

    prev_img = gray_frames[0]
    for i in range(1, num_frames):
        next_img = gray_frames[i]

        p1, st, err = cv2.calcOpticalFlowPyrLK(prev_img, next_img, p0, None, **lk_params)
        if p1 is None or st is None:
            # mark all as failed from now on
            for t in tracks:
                t.append(None)
            break

        # Update Tracks
        for idx in range(p1.shape[0]):
            succ = bool(st[idx][0])
            if succ:
                x_tl, y_tl = float(p1[idx][0][0]), float(p1[idx][0][1])
                x_bl, y_bl = x_tl, float(h) - y_tl
                tracks[idx].append((x_bl, y_bl))
            else:
                tracks[idx].append(None)

        p0 = p1
        prev_img = next_img

    return tracks


def extract_patch(img, x_bl, y_bl, size=11):
    """Extrahiere einen quadratischen Patch um (x,y) aus img.
    Erwartet Koordinaten im Overlay-System (BL-Ursprung); konvertiert nach TL für Array-Zugriff.
    Patch wird an Bildgrenzen geclamp't.
    """
    h, w = img.shape[:2]
    x = int(round(float(x_bl)))
    y_tl = int(round(float(h) - float(y_bl)))
    half = int(size) // 2
    x0 = max(x - half, 0)
    y0 = max(y_tl - half, 0)
    x1 = min(x + half + 1, w)
    y1 = min(y_tl + half + 1, h)
    return img[y0:y1, x0:x1]


def compute_track_kpis(track, gray_frames, patch_size=11):
    """Berechne KPIs pro Track: survival, corr_median, residual_rms.
    - track: Liste von Punkten (x,y) in BL-Koordinaten oder None pro Frame.
    - gray_frames: Liste HxW uint8-Frames (TL-Indexierung)
    """
    total = len(track)
    valid_points = [(i, pt) for i, pt in enumerate(track) if pt is not None]
    num_valid = len(valid_points)

    if num_valid < 2:
        return None

    survival = num_valid / max(1, total)

    # Korrelationen gegen Referenz (erstes gültiges)
    ref_idx, ref_pt = valid_points[0]
    ref_img = gray_frames[min(ref_idx, len(gray_frames) - 1)]
    ref_patch = extract_patch(ref_img, ref_pt[0], ref_pt[1], size=int(patch_size))
    corrs = []
    if ref_patch.size > 0:
        ref_flat = ref_patch.astype(np.float32).flatten()
        ref_std = np.std(ref_flat)
        for i, pt in valid_points[1:]:
            patch = extract_patch(gray_frames[min(i, len(gray_frames) - 1)], pt[0], pt[1], size=int(patch_size))
            if patch.shape != ref_patch.shape or patch.size == 0:
                continue
            tgt_flat = patch.astype(np.float32).flatten()
            # numerisch stabil: wenn std ~ 0, Korrelation 0
            tgt_std = np.std(tgt_flat)
            if ref_std < 1e-6 or tgt_std < 1e-6:
                corr = 0.0
            else:
                corr = float(np.corrcoef(ref_flat, tgt_flat)[0, 1])
            # clamp auf [-1,1]
            if not np.isfinite(corr):
                corr = 0.0
            corr = max(-1.0, min(1.0, corr))
            corrs.append(corr)
    corr_median = float(np.median(corrs)) if corrs else 0.0

    # RMS der Residuen (Glattheit der Bewegung)
    deltas = []
    for i in range(1, total):
        p0, p1 = track[i - 1], track[i]
        if p0 is not None and p1 is not None:
            deltas.append((float(p1[0] - p0[0]), float(p1[1] - p0[1])))
    if len(deltas) < 2:
        residual_rms = 0.0
    else:
        d = np.asarray(deltas, dtype=np.float32)
        mean_d = d.mean(axis=0)
        residuals = d - mean_d
        residual_rms = float(np.sqrt(np.mean(np.square(residuals))))

    return {
        "survival": float(survival),
        "corr_median": float(corr_median),
        "residual_rms": float(residual_rms),
    }


def filter_tracks_and_kpis(
    tracks,
    kpis,
    min_survival: float = 0.6,
    min_corr: float = 0.6,
    max_rms: float = 2.0,
    min_length: int = 4,
):
    """Filtere schlechte Tracks basierend auf KPIs und Mindestlänge.
    Gibt (filtered_tracks, filtered_kpis) zurück in gleicher Reihenfolge wie Eingabe.
    """
    if not tracks or not kpis:
        return [], []

    filtered_tracks = []
    filtered_kpis = []
    for track, kpi in zip(tracks, kpis):
        valid_len = sum(1 for p in track if p is not None)
        survival = float(kpi.get("survival", 0.0))
        corr = float(kpi.get("corr_median", 0.0))
        rms = float(kpi.get("residual_rms", 9_999.0))

        if (
            valid_len >= int(min_length)
            and survival >= float(min_survival)
            and corr >= float(min_corr)
            and rms <= float(max_rms)
        ):
            filtered_tracks.append(track)
            filtered_kpis.append(kpi)

    return filtered_tracks, filtered_kpis


# ---------- Korrespondenzen aus Tracks ----------
def correspondences_from_tracks(tracks, f0, f1):
    """Sammelt (x0,y0)->(x1,y1) aus allen Tracks für zwei Frames f0,f1.
    Punkte werden als float32-Arrays (N,2) zurückgegeben."""
    A = []
    B = []
    idx_map = []  # (track_idx, f0, f1)
    for ti, tr in enumerate(tracks):
        if f0 < len(tr) and f1 < len(tr):
            p0 = tr[f0]
            p1 = tr[f1]
            if p0 is not None and p1 is not None:
                A.append(p0)
                B.append(p1)
                idx_map.append((ti, f0, f1))
    if not A:
        return None, None, []
    return np.asarray(A, dtype=np.float32), np.asarray(B, dtype=np.float32), idx_map


# ---------- Helfer: Transformation anwenden ----------
def apply_affine_2x3(M, pts):
    """M: (2,3), pts: (N,2) -> (N,2)"""
    pts = np.asarray(pts, dtype=np.float32)
    N = pts.shape[0]
    hom = np.concatenate([pts, np.ones((N, 1), dtype=np.float32)], axis=1)  # (N,3)
    out = (M @ hom.T).T  # (N,2)
    return out.astype(np.float32)


def apply_homography(H, pts):
    """H: (3,3), pts: (N,2) -> (N,2)"""
    pts = np.asarray(pts, dtype=np.float32)
    N = pts.shape[0]
    hom = np.concatenate([pts, np.ones((N, 1), dtype=np.float32)], axis=1)  # (N,3)
    proj = (H @ hom.T).T  # (N,3)
    w = np.clip(proj[:, 2:3], 1e-8, None)
    out = proj[:, :2] / w
    return out.astype(np.float32)


def rms_residual(pred, tgt, mask=None):
    pred = np.asarray(pred, dtype=np.float32)
    tgt = np.asarray(tgt, dtype=np.float32)
    if mask is not None:
        mask = np.asarray(mask, dtype=bool)
        pred = pred[mask]
        tgt = tgt[mask]
    if pred.shape[0] == 0:
        return float("inf")
    res = pred - tgt
    return float(np.sqrt(np.mean(np.sum(res * res, axis=1))))


# ---------- Translation Fit ----------
def fit_translation(A, B):
    """Einfacher Mittelwert-Versatz (kein RANSAC)."""
    A = np.asarray(A, dtype=np.float32)
    B = np.asarray(B, dtype=np.float32)
    if A.shape[0] == 0:
        return None
    d = np.mean(B - A, axis=0)

    def apply(pts):
        return pts + d

    pred = apply(A)
    rms = rms_residual(pred, B)
    inliers = np.ones((A.shape[0],), dtype=bool)  # alle
    # Als 3x3 Mat für Einheitlichkeit zurückgeben
    M = np.array([[1, 0, d[0]],
                  [0, 1, d[1]],
                  [0, 0, 1]], dtype=np.float32)
    return {"type": "translation", "M": M, "inliers": inliers, "rms": rms}


# ---------- Similarity (LocRotScale) via RANSAC ----------
def fit_similarity(A, B, ransacReprojThreshold=3.0, confidence=0.99, maxIters=2000):
    try:
        import cv2  # type: ignore
    except Exception:
        return None
    M, inliers = cv2.estimateAffinePartial2D(
        A, B, method=cv2.RANSAC,
        ransacReprojThreshold=ransacReprojThreshold,
        confidence=confidence, maxIters=maxIters, refineIters=10
    )
    if M is None or inliers is None:
        return None
    inliers = inliers.ravel().astype(bool)
    pred = apply_affine_2x3(M, A)
    rms = rms_residual(pred, B, mask=inliers)
    # in 3x3 betten
    M33 = np.array([[M[0, 0], M[0, 1], M[0, 2]],
                    [M[1, 0], M[1, 1], M[1, 2]],
                    [0, 0, 1]], dtype=np.float32)
    return {"type": "similarity", "M": M33, "inliers": inliers, "rms": rms}


# ---------- Affine via RANSAC ----------
def fit_affine(A, B, ransacReprojThreshold=3.0, confidence=0.99, maxIters=2000):
    try:
        import cv2  # type: ignore
    except Exception:
        return None
    M, inliers = cv2.estimateAffine2D(
        A, B, method=cv2.RANSAC,
        ransacReprojThreshold=ransacReprojThreshold,
        confidence=confidence, maxIters=maxIters, refineIters=10
    )
    if M is None or inliers is None:
        return None
    inliers = inliers.ravel().astype(bool)
    pred = apply_affine_2x3(M, A)
    rms = rms_residual(pred, B, mask=inliers)
    M33 = np.array([[M[0, 0], M[0, 1], M[0, 2]],
                    [M[1, 0], M[1, 1], M[1, 2]],
                    [0, 0, 1]], dtype=np.float32)
    return {"type": "affine", "M": M33, "inliers": inliers, "rms": rms}


# ---------- Perspective (Homographie) via RANSAC ----------
def fit_perspective(A, B, ransacReprojThreshold=3.0, confidence=0.995, maxIters=5000):
    try:
        import cv2  # type: ignore
    except Exception:
        return None
    if A.shape[0] < 4:
        return None
    H, inliers = cv2.findHomography(A, B, method=cv2.RANSAC,
                                    ransacReprojThreshold=ransacReprojThreshold,
                                    maxIters=maxIters, confidence=confidence)
    if H is None or inliers is None:
        return None
    inliers = inliers.ravel().astype(bool)
    pred = apply_homography(H, A)
    rms = rms_residual(pred, B, mask=inliers)
    return {"type": "perspective", "M": H.astype(np.float32), "inliers": inliers, "rms": rms}


# ---------- Score & Auswahl ----------
def model_complexity_kappa(model_type):
    # gemäß Spez: κ={1,2,3,4,6}; wir mappen:
    # translation=1, similarity=3, affine=4, perspective=6
    return {"translation": 1, "similarity": 3, "affine": 4, "perspective": 6}.get(model_type, 4)


def choose_best_model(fits, lam=0.12, min_inliers=8):
    best = None
    for f in fits:
        if f is None:
            continue
        nin = int(np.sum(f["inliers"])) if f.get("inliers") is not None else 0
        if nin < int(min_inliers):
            continue
        kappa = model_complexity_kappa(f["type"])
        S = float(f["rms"]) + float(lam) * float(kappa)
        f["score_S"] = float(S)
        f["inliers_count"] = nin
        f["inliers_ratio"] = float(nin) / float(max(1, f.get("total", nin)))
        if best is None or S < best["score_S"]:
            best = f
    return best


def fit_motion_models_all(A, B, lam=0.12, ransac_thresh=3.0, min_inliers=8):
    total = int(A.shape[0])
    fits = []

    # Translation (kein RANSAC)
    tr = fit_translation(A, B)
    if tr is not None:
        tr["total"] = total
    fits.append(tr)

    # Similarity
    sim = fit_similarity(A, B, ransacReprojThreshold=ransac_thresh)
    if sim:
        sim["total"] = total
    fits.append(sim)

    # Affine
    aff = fit_affine(A, B, ransacReprojThreshold=ransac_thresh)
    if aff:
        aff["total"] = total
    fits.append(aff)

    # Perspective (etwas großzügigerer Threshold)
    hom = fit_perspective(A, B, ransacReprojThreshold=float(ransac_thresh) * 1.25)
    if hom:
        hom["total"] = total
    fits.append(hom)

    best = choose_best_model(fits, lam=lam, min_inliers=min_inliers)
    return best, fits


# =====================
# Promotion-Engine (Levels)
# =====================

# ---------- Level-Definition ----------
MODEL_LEVELS = ["loc", "locrot", "lrs", "affine", "perspective"]


def level_index(level):
    return MODEL_LEVELS.index(level)


def kappa_for_level(level):
    # κ={1,2,3,4,6}
    return {"loc": 1, "locrot": 2, "lrs": 3, "affine": 4, "perspective": 6}[level]


# ---------- Matrix-Decomposition/Build ----------
def decompose_affine_2x3(M2x3):
    """
    Zerlege 2x3-Affine in Rotation (deg), Scale (sx, sy), Shear (phi_shear).
    """
    import numpy as _np

    A = M2x3[:, :2].astype(_np.float64)  # 2x2
    # Polar Decomp approximiert via SVD: A = U * diag(S) * V^T; R = U*V^T
    U, S, Vt = _np.linalg.svd(A)
    R = U @ Vt
    if _np.linalg.det(R) < 0:
        Vt[1, :] *= -1
        R = U @ Vt
        S = _np.array([S[0], -S[1]])
    rot_rad = _np.arctan2(R[1, 0], R[0, 0])
    rot_deg = _np.degrees(rot_rad)

    # Symmetrischer Anteil (Skalierung+Shear)
    Sym = Vt.T @ _np.diag(S) @ Vt
    sx = Sym[0, 0] ** 0.5 if Sym[0, 0] > 0 else 1.0
    sy = Sym[1, 1] ** 0.5 if Sym[1, 1] > 0 else 1.0
    # Shear-Proxy: Off-Diagonal relativ zur Scale
    shear = Sym[0, 1] / max(1e-6, (sx * sy))

    return float(rot_deg), float(sx), float(sy), float(shear)


def force_locrot_from_similarity(M2x3):
    """
    Nimmt eine Similarity-Schätzung (Rot+Scale) und erzeugt Rot-only (Scale=1) mit gleicher Translation.
    """
    import numpy as _np

    rot_deg, sx, sy, shear = decompose_affine_2x3(M2x3)
    theta = _np.radians(rot_deg)
    R = _np.array([[_np.cos(theta), -_np.sin(theta)],
                   [_np.sin(theta),  _np.cos(theta)]], dtype=_np.float32)
    t = M2x3[:, 2:3].astype(_np.float32)
    M_locrot = _np.concatenate([R, t], axis=1)  # 2x3
    return M_locrot


# ---------- Fit pro Level (nutzt vorhandene Fits als Basis) ----------
def fit_loc(A, B):
    import numpy as _np

    A = _np.asarray(A, dtype=_np.float32)
    B = _np.asarray(B, dtype=_np.float32)
    if A.shape[0] == 0:
        return None
    d = _np.mean(B - A, axis=0)
    pred = A + d
    rms = float(_np.sqrt(_np.mean(_np.sum((pred - B) ** 2, axis=1))))
    inliers = _np.ones((A.shape[0],), dtype=bool)
    M33 = _np.array([[1, 0, d[0]], [0, 1, d[1]], [0, 0, 1]], dtype=_np.float32)
    return {"level": "loc", "M": M33, "inliers": inliers, "rms": rms}


def fit_locrot(A, B, thresh=3.0):
    # erst Similarity schätzen, dann Scale→1 zwingen und neu bewerten
    try:
        import cv2  # type: ignore
    except Exception:
        return None
    import numpy as _np

    M, inl = cv2.estimateAffinePartial2D(_np.asarray(A, _np.float32), _np.asarray(B, _np.float32),
                                         method=cv2.RANSAC,
                                         ransacReprojThreshold=float(thresh),
                                         confidence=0.99, maxIters=2000, refineIters=10)
    if M is None:
        return None
    M_lr = force_locrot_from_similarity(M)
    homA = _np.concatenate([_np.asarray(A, _np.float32), _np.ones((_np.asarray(A).shape[0], 1), _np.float32)], axis=1)
    pred = (M_lr @ homA.T).T
    inliers = _np.linalg.norm(pred - _np.asarray(B, _np.float32), axis=1) < (float(thresh) * 1.25)
    rms = float(_np.sqrt(_np.mean(_np.sum((pred[inliers] - _np.asarray(B, _np.float32)[inliers]) ** 2, axis=1)))) if _np.any(inliers) else _np.inf
    M33 = _np.array([[M_lr[0, 0], M_lr[0, 1], M_lr[0, 2]],
                     [M_lr[1, 0], M_lr[1, 1], M_lr[1, 2]],
                     [0, 0, 1]], dtype=_np.float32)
    return {"level": "locrot", "M": M33, "inliers": inliers, "rms": rms}


def fit_lrs(A, B, thresh=3.0):
    try:
        import cv2  # type: ignore
    except Exception:
        return None
    import numpy as _np

    M, inl = cv2.estimateAffinePartial2D(_np.asarray(A, _np.float32), _np.asarray(B, _np.float32),
                                         method=cv2.RANSAC,
                                         ransacReprojThreshold=float(thresh),
                                         confidence=0.99, maxIters=2000, refineIters=10)
    if M is None or inl is None:
        return None
    inliers = inl.ravel().astype(bool)
    homA = _np.concatenate([_np.asarray(A, _np.float32), _np.ones((_np.asarray(A).shape[0], 1), _np.float32)], axis=1)
    pred = (M @ homA.T).T
    rms = float(_np.sqrt(_np.mean(_np.sum((pred[inliers] - _np.asarray(B, _np.float32)[inliers]) ** 2, axis=1)))) if _np.any(inliers) else _np.inf
    M33 = _np.array([[M[0, 0], M[0, 1], M[0, 2]],
                     [M[1, 0], M[1, 1], M[1, 2]],
                     [0, 0, 1]], dtype=_np.float32)
    return {"level": "lrs", "M": M33, "inliers": inliers, "rms": rms}


def fit_affine_level(A, B, thresh=3.0):
    try:
        import cv2  # type: ignore
    except Exception:
        return None
    import numpy as _np

    M, inl = cv2.estimateAffine2D(_np.asarray(A, _np.float32), _np.asarray(B, _np.float32),
                                  method=cv2.RANSAC,
                                  ransacReprojThreshold=float(thresh),
                                  confidence=0.99, maxIters=2000, refineIters=10)
    if M is None or inl is None:
        return None
    inliers = inl.ravel().astype(bool)
    homA = _np.concatenate([_np.asarray(A, _np.float32), _np.ones((_np.asarray(A).shape[0], 1), _np.float32)], axis=1)
    pred = (M @ homA.T).T
    rms = float(_np.sqrt(_np.mean(_np.sum((pred[inliers] - _np.asarray(B, _np.float32)[inliers]) ** 2, axis=1)))) if _np.any(inliers) else _np.inf
    M33 = _np.array([[M[0, 0], M[0, 1], M[0, 2]],
                     [M[1, 0], M[1, 1], M[1, 2]],
                     [0, 0, 1]], dtype=_np.float32)
    return {"level": "affine", "M": M33, "inliers": inliers, "rms": rms}


def fit_perspective_level(A, B, thresh=3.5):
    try:
        import cv2  # type: ignore
    except Exception:
        return None
    import numpy as _np

    A = _np.asarray(A, _np.float32)
    B = _np.asarray(B, _np.float32)
    if A.shape[0] < 4:
        return None
    H, inl = cv2.findHomography(A, B, method=cv2.RANSAC,
                                ransacReprojThreshold=float(thresh),
                                maxIters=5000, confidence=0.995)
    if H is None or inl is None:
        return None
    inliers = inl.ravel().astype(bool)
    homA = _np.concatenate([A, _np.ones((A.shape[0], 1), _np.float32)], axis=1)
    proj = (H @ homA.T).T
    proj = proj[:, :2] / _np.clip(proj[:, 2:3], 1e-8, None)
    rms = float(_np.sqrt(_np.mean(_np.sum((proj[inliers] - B[inliers]) ** 2, axis=1)))) if _np.any(inliers) else _np.inf
    return {"level": "perspective", "M": H.astype(_np.float32), "inliers": inliers, "rms": rms}


# ---------- S-Score ----------
def s_score(rms, level, lam=0.12):
    return float(rms + float(lam) * kappa_for_level(level))


# ---------- Indikatoren (Rot/Scale/Shear/Parallax) ----------
def indicators_for_fit(fit, A, B, img_wh=None):
    import numpy as _np

    lvl = fit["level"]
    M = fit["M"]
    nin = int(_np.sum(fit["inliers"]))
    tot = A.shape[0]
    outlier_drop_ratio = 1.0 - (nin / max(1, tot))

    rot_deg = 0.0
    scale = 1.0
    shear_phi = 0.0
    if lvl in ("locrot", "lrs", "affine"):
        M2 = M[:2, :]
        rdeg, sx, sy, shear = decompose_affine_2x3(M2)
        rot_deg = abs(rdeg)
        scale = 0.5 * (sx + sy)
        shear_phi = abs(shear)

    # Parallax-Proxy: Korrelation Residuallänge mit Radius zum Bildzentrum
    parallax = 0.0
    try:
        if img_wh is not None:
            w, h = img_wh
            cx, cy = w * 0.5, h * 0.5
            A_np = _np.asarray(A, _np.float32)
            B_np = _np.asarray(B, _np.float32)
            if lvl in ("loc", "locrot", "lrs", "affine"):
                pred = (M[:2, :] @ _np.concatenate([A_np, _np.ones((A_np.shape[0], 1), _np.float32)], axis=1).T).T
            else:
                homA = _np.concatenate([A_np, _np.ones((A_np.shape[0], 1), _np.float32)], axis=1)
                proj = (M @ homA.T).T
                pred = proj[:, :2] / _np.clip(proj[:, 2:3], 1e-8, None)
            res = _np.linalg.norm(pred - B_np, axis=1)
            rad = _np.sqrt((A_np[:, 0] - cx) ** 2 + (A_np[:, 1] - cy) ** 2)
            if _np.std(res) > 1e-6 and _np.std(rad) > 1e-6:
                parallax = float(_np.corrcoef(res, rad)[0, 1])
    except Exception:
        parallax = 0.0

    return {
        "nin": nin, "tot": tot,
        "outlier_drop": outlier_drop_ratio,
        "rot_deg": float(rot_deg),
        "scale": float(scale),
        "shear_phi": float(shear_phi),
        "parallax": float(parallax),
    }


# ---------- Promotion Engine ----------
def get_model_state(scene, window_len=30):
    st = scene.get("strm_model_state")
    if not st:
        st = {
            "current_level": "loc",
            "history": [],  # list of dicts with: level,S,rms,nin,tot,rot,scale,shear,parallax
            "promote_counter": 0,
            "rollback_counter": 0,
            "cooldown": 0,
        }
        scene["strm_model_state"] = st
    return st


def append_history(state, entry, maxlen=40):
    hist = state.get("history", [])
    hist.append(entry)
    if len(hist) > maxlen:
        del hist[0]
    state["history"] = hist


def rolling_sigma(vals, k=3):
    vals = [v for v in vals if v is not None]
    if len(vals) < k:
        return None
    import numpy as _np
    arr = _np.array(vals[-k:], dtype=_np.float32)
    return float(_np.std(arr))


def promotion_step(A, B, img_wh, scene, lam=0.12, ransac_thresh=3.0):
    """
    Führt einen Promotionsschritt durch:
    - fitte alle Levels (sofern möglich)
    - evaluiere ΔS und Indikatoren
    - update current_level mit Hysterese/Rollback/Cooldown
    """
    import numpy as _np

    st = get_model_state(scene)
    cur = st["current_level"]

    # Fit-Kandidaten
    candidates = []
    loc = fit_loc(A, B);                   candidates.append(loc)
    locrot = fit_locrot(A, B, ransac_thresh);  candidates.append(locrot)
    lrs = fit_lrs(A, B, ransac_thresh);        candidates.append(lrs)
    aff = fit_affine_level(A, B, ransac_thresh); candidates.append(aff)
    hom = fit_perspective_level(A, B, ransac_thresh * 1.25); candidates.append(hom)

    fits = {f["level"]: f for f in candidates if f is not None and _np.sum(f["inliers"]) >= 8}
    if not fits:
        return {}, st
    if cur not in fits:
        # Fallback: setze auf einfachstes verfügbares
        cur = sorted(fits.keys(), key=lambda L: level_index(L))[0]
        st["current_level"] = cur

    # Scores + Indikatoren
    stats = {}
    for lvl, f in fits.items():
        S = s_score(f["rms"], lvl, lam=lam)
        ind = indicators_for_fit(f, A, B, img_wh)
        stats[lvl] = {"fit": f, "S": S, **ind}

    # Aktuelle Kennzahlen
    curS = stats[cur]["S"]
    append_history(st, {"level": cur, "S": curS, "rms": stats[cur]["fit"]["rms"],
                        "nin": stats[cur]["nin"], "tot": stats[cur]["tot"],
                        "rot": stats[cur].get("rot_deg"), "scale": stats[cur].get("scale"),
                        "shear": stats[cur].get("shear_phi"), "parallax": stats[cur].get("parallax")})

    # Cooldown?
    if st.get("cooldown", 0) > 0:
        st["cooldown"] = max(0, st["cooldown"] - 1)
        return stats, st  # keine Promotion während Cooldown

    # Helper: ΔS zum nächsten Level
    def try_promote(target, dS_thresh, extra_ok):
        if target in stats:
            dS = curS - stats[target]["S"]
            return (dS >= dS_thresh) or extra_ok
        return False

    next_level = None

    # ——— Promotion-Regeln ———
    if cur == "loc":
        # ΔS≥0.3 oder σ_rot≥0.5° (3 Fenster)
        sigma_rot = rolling_sigma([h.get("rot") for h in st["history"]], k=3)
        cond_extra = (sigma_rot is not None and sigma_rot >= 0.5)
        if try_promote("locrot", 0.30, cond_extra):
            next_level = "locrot"
    elif cur == "locrot":
        # ΔS≥0.25 oder σ_scale≥1.5 % (3 Fenster)
        sigma_scale = rolling_sigma([h.get("scale") for h in st["history"]], k=3)
        cond_extra = (sigma_scale is not None and (sigma_scale * 100.0) >= 1.5)
        if try_promote("lrs", 0.25, cond_extra):
            next_level = "lrs"
    elif cur == "lrs":
        # ΔS≥0.20 oder ϕ_shear≥0.15 UND Outlier↓≥10 %
        if "affine" in stats:
            dS = curS - stats["affine"]["S"]
            out_drop = stats["affine"]["outlier_drop"] - stats["lrs"]["outlier_drop"]
            shear_ok = stats["affine"]["shear_phi"] >= 0.15
            if (dS >= 0.20) or (shear_ok and out_drop >= 0.10):
                next_level = "affine"
    elif cur == "affine":
        # ΔS≥0.20 UND Parallaxe hoch UND Outlier↓≥5 %
        if "perspective" in stats:
            dS = curS - stats["perspective"]["S"]
            out_drop = stats["perspective"]["outlier_drop"] - stats["affine"]["outlier_drop"]
            parallax_ok = stats["perspective"].get("parallax", 0.0) >= 0.3
            if (dS >= 0.20) and parallax_ok and (out_drop >= 0.05):
                next_level = "perspective"

    if next_level:
        st["promote_counter"] = st.get("promote_counter", 0) + 1
        # Hysterese: 3 Fenster positiv für Stufen <affine>, 2 Fenster für affine→persp
        need = 3 if next_level in ("locrot", "lrs", "affine") else 2
        if st["promote_counter"] >= need:
            st["current_level"] = next_level
            st["promote_counter"] = 0
            st["rollback_counter"] = 0
            st["cooldown"] = 15  # min. Cooldown (Frames)
    else:
        # kein Upgrade → Counter zurücksetzen
        st["promote_counter"] = 0

    # ——— Rollback: wenn kein Benefit (2 Fenster) ———
    # prüfe, ob ein einfacheres Level aktuell klar besseren S liefert
    simpler_levels = [L for L in MODEL_LEVELS if level_index(L) < level_index(st["current_level"]) and L in stats]
    if simpler_levels:
        best_simple = min(simpler_levels, key=lambda L: stats[L]["S"])
        dS_back = stats[best_simple]["S"] - stats[st["current_level"]]["S"]
        # Wenn S_current nicht besser als einfacher Level (dS_back >= 0) über 2 Fenster -> rollback
        if dS_back >= -1e-6:
            st["rollback_counter"] = st.get("rollback_counter", 0) + 1
            if st["rollback_counter"] >= 2:
                st["current_level"] = best_simple
                st["rollback_counter"] = 0
                st["promote_counter"] = 0
                st["cooldown"] = 10
        else:
            st["rollback_counter"] = 0

    return stats, st
