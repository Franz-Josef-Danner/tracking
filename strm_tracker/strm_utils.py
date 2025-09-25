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
