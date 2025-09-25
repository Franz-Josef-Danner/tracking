import bpy
import gpu
from gpu_extras.batch import batch_for_shader


def get_overlay_state(scene: bpy.types.Scene):
    """Get or initialize overlay state on the scene as an IDProperty dict."""
    ov = scene.get("strm_overlay")
    if not isinstance(ov, dict):
        ov = {"enabled": False, "tiles": []}
        scene["strm_overlay"] = ov
    else:
        # ensure expected keys exist
        ov.setdefault("enabled", False)
        ov.setdefault("tiles", [])
    return ov


def draw_tile_overlay_callback(self, context):
    space = context.space_data
    if not isinstance(space, bpy.types.SpaceClipEditor):
        return

    clip = context.edit_movieclip
    if not clip:
        return

    overlay = get_overlay_state(context.scene)
    if not overlay.get("enabled"):
        return

    tiles = overlay.get("tiles") or []
    if not tiles:
        return

    score_type = overlay.get("score_type", "motion")

    rv2d = context.region.view2d

    def normalize_score(v, vmin, vmax):
        denom = max(1e-8, (vmax - vmin))
        return max(0.0, min(1.0, (v - vmin) / denom))

    def colormap(score):
        # Rot -> Gelb -> Grün, Alpha ~ 0.4
        if score < 0.5:
            return (1.0, score * 2.0, 0.0, 0.4)
        else:
            return (2.0 * (1.0 - score), 1.0, 0.0, 0.4)

    # Score-Range bestimmen
    scores = [float(t.get(score_type, 0.0)) for t in tiles]
    vmin = min(scores) if scores else 0.0
    vmax = max(scores) if scores else 1.0

    tri_shader = gpu.shader.from_builtin('2D_UNIFORM_COLOR')
    line_shader = gpu.shader.from_builtin('2D_UNIFORM_COLOR')

    gpu.state.blend_set('ALPHA')
    gpu.state.line_width_set(1.0)

    for t in tiles:
        x0, y0, x1, y1 = t.get('coords', (0.0, 0.0, 0.0, 0.0))
        # Koordinaten aus View (Bildpixel) in Region-Pixel
        rx0, ry0 = rv2d.view_to_region(x0, y0, clip=False)
        rx1, ry1 = rv2d.view_to_region(x1, y1, clip=False)
        if None in (rx0, ry0, rx1, ry1):
            continue

        s = normalize_score(float(t.get(score_type, 0.0)), vmin, vmax)
        color = colormap(s)

        rect_coords = [(rx0, ry0), (rx1, ry0), (rx1, ry1), (rx0, ry1)]
        indices = ((0, 1, 2), (2, 3, 0))

        # Füllung
        tri_shader.bind()
        tri_shader.uniform_float("color", color)
        tri_batch = batch_for_shader(tri_shader, 'TRIS', {"pos": rect_coords}, indices=indices)
        tri_batch.draw(tri_shader)

        # Rahmen
        line_coords = [
            (rx0, ry0), (rx1, ry0),
            (rx1, ry0), (rx1, ry1),
            (rx1, ry1), (rx0, ry1),
            (rx0, ry1), (rx0, ry0),
        ]
        line_shader.bind()
        line_shader.uniform_float("color", (0.0, 0.0, 0.0, 0.35))
        line_batch = batch_for_shader(line_shader, 'LINES', {"pos": line_coords})
        line_batch.draw(line_shader)

    gpu.state.blend_set('NONE')

    # ROIs (blau) umranden
    rois = overlay.get("rois", [])
    if rois:
        shader = gpu.shader.from_builtin('2D_UNIFORM_COLOR')
        shader.bind()
        shader.uniform_float("color", (0.2, 0.6, 1.0, 0.85))

        line_coords = []
        for roi in rois:
            x0, y0, x1, y1 = roi.get('coords', (0.0, 0.0, 0.0, 0.0))
            rx0, ry0 = rv2d.view_to_region(x0, y0, clip=False)
            rx1, ry1 = rv2d.view_to_region(x1, y1, clip=False)
            if None in (rx0, ry0, rx1, ry1):
                continue
            line_coords.extend([
                (rx0, ry0), (rx1, ry0),
                (rx1, ry0), (rx1, ry1),
                (rx1, ry1), (rx0, ry1),
                (rx0, ry1), (rx0, ry0),
            ])

        if line_coords:
            gpu.state.blend_set('ALPHA')
            gpu.state.line_width_set(1.5)
            batch = batch_for_shader(shader, 'LINES', {"pos": line_coords})
            batch.draw(shader)
            gpu.state.blend_set('NONE')

    # Markerpunkte (rot) zeichnen
    markers = overlay.get("markers", [])
    if markers:
        pts = []
        for x, y in markers:
            rx, ry = rv2d.view_to_region(x, y, clip=False)
            if None not in (rx, ry):
                pts.append((rx, ry))
        if pts:
            shader = gpu.shader.from_builtin('2D_UNIFORM_COLOR')
            shader.bind()
            shader.uniform_float("color", (1.0, 0.2, 0.2, 1.0))
            batch = batch_for_shader(shader, 'POINTS', {"pos": pts})
            gpu.state.point_size_set(4.0)
            batch.draw(shader)

    # Trajektorien (türkis) zeichnen
    tracks = overlay.get("tracks", [])
    kpis = overlay.get("kpis", [])
    if tracks:
        gpu.state.line_width_set(1.5)
        for i, traj in enumerate(tracks):
            coords = []
            for p in traj:
                if p is None:
                    if len(coords) >= 2:
                        color = (0.5, 0.5, 0.5, 0.5)
                        if i < len(kpis):
                            corr = float(kpis[i].get("corr_median", 0.0))
                            corr = max(-1.0, min(1.0, corr))
                            # Mappe [-1,1] auf [0,1]
                            s = 0.5 * (corr + 1.0)
                            color = (1.0 - s, s, 0.0, 0.6)
                        shader = gpu.shader.from_builtin('2D_UNIFORM_COLOR')
                        shader.bind()
                        shader.uniform_float("color", color)
                        batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": coords})
                        batch.draw(shader)
                    coords = []
                    continue
                x, y = p
                rx, ry = rv2d.view_to_region(x, y, clip=False)
                if None not in (rx, ry):
                    coords.append((rx, ry))
            if len(coords) >= 2:
                color = (0.5, 0.5, 0.5, 0.5)
                if i < len(kpis):
                    corr = float(kpis[i].get("corr_median", 0.0))
                    corr = max(-1.0, min(1.0, corr))
                    s = 0.5 * (corr + 1.0)
                    color = (1.0 - s, s, 0.0, 0.6)
                shader = gpu.shader.from_builtin('2D_UNIFORM_COLOR')
                shader.bind()
                shader.uniform_float("color", color)
                batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": coords})
                batch.draw(shader)
