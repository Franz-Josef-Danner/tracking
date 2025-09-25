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

    region = context.region
    rv2d = context.region.view2d

    # Prepare shader
    shader = gpu.shader.from_builtin('2D_UNIFORM_COLOR')
    shader.bind()
    shader.uniform_float("color", (1.0, 1.0, 0.0, 0.9))  # yellow

    # Build line segments for all tile rectangles
    coords = []
    for x0, y0, x1, y1 in tiles:
        # Convert from image/view space (pixels) to region pixels
        rx0, ry0 = rv2d.view_to_region(x0, y0, clip=False)
        rx1, ry1 = rv2d.view_to_region(x1, y1, clip=False)
        if rx0 is None or ry0 is None or rx1 is None or ry1 is None:
            continue
        coords.extend([
            (rx0, ry0), (rx1, ry0),
            (rx1, ry0), (rx1, ry1),
            (rx1, ry1), (rx0, ry1),
            (rx0, ry1), (rx0, ry0),
        ])

    if not coords:
        return

    batch = batch_for_shader(shader, 'LINES', {"pos": coords})
    gpu.state.blend_set('ALPHA')
    gpu.state.line_width_set(1.0)
    batch.draw(shader)
    gpu.state.blend_set('NONE')
