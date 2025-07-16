from types import SimpleNamespace

from modules.util.context_helpers import get_clip_editor_override


def test_get_clip_editor_override():
    area = SimpleNamespace(
        type="CLIP_EDITOR",
        regions=[SimpleNamespace(type="WINDOW")],
        spaces=SimpleNamespace(active=SimpleNamespace(type="CLIP_EDITOR")),
    )
    ctx = SimpleNamespace(window=SimpleNamespace(screen=SimpleNamespace(areas=[area])))

    override = get_clip_editor_override(ctx)
    assert override["window"] is ctx.window
    assert override["area"] is area
    assert override["region"] is area.regions[0]
    assert override["space_data"] is area.spaces.active


def test_get_clip_editor_override_no_area():
    ctx = SimpleNamespace(window=SimpleNamespace(screen=SimpleNamespace(areas=[])))
    override = get_clip_editor_override(ctx)
    assert override == {"window": ctx.window}
