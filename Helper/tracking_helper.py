def _force_clip_view_refresh(context: bpy.types.Context) -> None:
    """Viewer-Refresh im Clip-Editor erzwingen (mit Context-Override)."""
    handles = None
    try:
        handles = _clip_editor_handles(context)
    except Exception:
        handles = None

    # 1) Regionen redrawen
    try:
        wm = context.window_manager
    except Exception:
        wm = bpy.context.window_manager

    try:
        for win in wm.windows:
            scr = win.screen
            if not scr: 
                continue
            for area in scr.areas:
                if area.type != 'CLIP_EDITOR':
                    continue
                try:
                    area.tag_redraw()
                    for reg in area.regions:
                        if reg.type in {'WINDOW', 'UI'}:
                            reg.tag_redraw()
                except Exception:
                    pass
                # 2) Context-Override + ViewLayer-Update (wie im Modal-Kontext)
                try:
                    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                    space  = area.spaces.active if hasattr(area, 'spaces') else None
                    if region and space:
                        with bpy.context.temp_override(window=win, area=area, region=region, space_data=space):
                            try:
                                bpy.context.view_layer.update()
                            except Exception:
                                pass
                except Exception:
                    pass
        # 3) Fallback: globaler Redraw
        try:
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        except Exception:
            pass
    except Exception:
        pass
