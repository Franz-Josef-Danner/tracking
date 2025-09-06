import bpy

def tag_clip_redraw() -> None:
    try:
        wm = bpy.context.window_manager
        if not wm:
            return
        for win in wm.windows:
            scr = getattr(win, "screen", None)
            if not scr:
                continue
            for area in scr.areas:
                if area.type != "CLIP_EDITOR":
                    continue
                for region in area.regions:
                    if region.type in {"WINDOW", "UI"}:
                        region.tag_redraw()
    except Exception:
        pass