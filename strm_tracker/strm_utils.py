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
