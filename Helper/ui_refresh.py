# Helper/ui_refresh.py
import bpy
from typing import Iterable, Tuple

# Wir refreshen ausschließlich CLIP_EDITOR-Areas.
# Das deckt Viewer, Graph, Dopesheet und Timeline *innerhalb* des Movie-Clip-Editors ab.
_CLIP_EDITOR = ("CLIP_EDITOR",)
# Diese Region-Typen genügen, um alle Subbereiche im CLIP-Editor sicher zu repainten.
_REGIONS: Tuple[str, ...] = ("WINDOW", "UI", "HEADER")

def refresh_clip_editor(context: bpy.types.Context = None) -> None:
    """
    Forciert einen Redraw *nur* im Movie-Clip-Editor (inkl. Viewer, Graph, Dopesheet, Timeline).
    Einsatz: zwischen Operator-Schritten aufrufen.
    """
    ctx = context or bpy.context
    wm = ctx.window_manager

    for window in wm.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type not in _CLIP_EDITOR:
                continue

            # 1) Area selbst anstoßen (zieht i.d.R. alle Sub-Regions mit)
            try:
                area.tag_redraw()
            except Exception:
                pass

            # 2) Sicherheitsnetz: zentrale Regions explizit redrawen
            for region in area.regions:
                if region.type in _REGIONS:
                    try:
                        region.tag_redraw()
                    except Exception:
                        pass


def hard_refresh_clip_editor() -> None:
    """
    Fallback mit globalem Draw-Swap, falls tag_redraw() in seltenen Fällen nicht greift
    (z.B. bei langen Operator-Queues oder Timer-lastigen Pipelines).
    Nutzt weiterhin nur bestehende Fenster, erzeugt aber einen sofortigen Frame-Swap.
    """
    try:
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
    except Exception:
        pass
