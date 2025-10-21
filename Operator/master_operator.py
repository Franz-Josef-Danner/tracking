import bpy
from typing import Any, Optional, Tuple

# Import der Helper-Funktion
from ..Helper.low_marker_frame import find_first_weak_frame


def _find_clip_editor_area_for_clip(clip: Optional[bpy.types.MovieClip]):
    """Sucht eine CLIP_EDITOR-Area (mit passendem Space/Region) für Context Override."""
    wm = bpy.context.window_manager
    for window in wm.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type != "CLIP_EDITOR":
                continue
            region_window = next((r for r in area.regions if r.type == "WINDOW"), None)
            if not region_window:
                continue
            for space in area.spaces:
                if space.type != "CLIP_EDITOR":
                    continue
                # Preferiere Space mit gleicher Clip-Referenz oder leerem Slot
                if getattr(space, "clip", None) == clip or space.clip is None:
                    return window, area, region_window, space
    return None, None, None, None


def _coerce_frame(result: Any) -> Optional[int]:
    """
    Toleranter Unpacker:
    - int -> Frame
    - (frame,) -> Frame
    - (frame, count[, target]) -> Frame
    - None -> None
    """
    if result is None:
        return None
    if isinstance(result, int):
        return result
    if isinstance(result, (tuple, list)) and result:
        first = result[0]
        return int(first) if isinstance(first, (int, float)) else None
    return None


class KAISERLICHTRACKER_OT_master_operator(bpy.types.Operator):
    """Springt zum ersten Frame mit zu wenigen Markern (unterhalb Scene.kaiserlich_markers_per_frame)."""
    bl_idname = "kaiserlich_tracker.master_operator"
    bl_label = "KAISERLICHTRACKER — master operator"
    bl_options = {"REGISTER", "UNDO"}

    set_playhead: bpy.props.BoolProperty(
        name="Playhead setzen",
        description="Playhead im Clip Editor auf den gefundenen Frame setzen",
        default=True,
    )

    store_scene_key: bpy.props.StringProperty(
        name="Scene Key",
        description="Szenen-Property zum Ablegen des gefundenen Frames",
        default="kaiserlich_low_marker_frame",
    )

    def execute(self, context: bpy.types.Context):
        # 1) Weak-Frame bestimmen (robust bzgl. Return-Signatur)
        try:
            res = find_first_weak_frame(context)
        except Exception as e:
            self.report({"ERROR"}, f"find_first_weak_frame() Fehler: {e}")
            return {"CANCELLED"}

        frame = _coerce_frame(res)
        if frame is None:
            self.report({"INFO"}, "Kein Low-Marker-Frame gefunden.")
            return {"CANCELLED"}

        # 2) Wert in Szene persistieren (für nachgelagerte Pipelines/Operatoren)
        try:
            context.scene[self.store_scene_key] = int(frame)
        except Exception:
            # Fallback, falls Custom-Props gesperrt: ignorieren
            pass

        # 3) Optional: Playhead setzen (Scene + Clip Editor)
        if self.set_playhead:
            # Szene-Frame setzen (globaler Timecursor)
            context.scene.frame_current = int(frame)

            # Clip-Editor fokussieren (wenn vorhanden)
            clip = getattr(getattr(context, "space_data", None), "clip", None)
            window, area, region, space = _find_clip_editor_area_for_clip(clip)

            if window and area and region and space:
                override = {
                    "window": window,
                    "screen": window.screen,
                    "area": area,
                    "region": region,
                    "space_data": space,
                    "scene": context.scene,
                }
                # Versuche den Clip-Editor explizit zu aktualisieren
                try:
                    # change_frame existiert im Clip-Editor-Kontext
                    bpy.ops.clip.change_frame(override, frame=int(frame))
                except Exception:
                    # Minimal: Redraw triggern
                    try:
                        region.tag_redraw()
                    except Exception:
                        pass

        # 4) Operational Logging
        self.report({"INFO"}, f"Low-Marker-Frame: {frame}")
        print(f"[Kaiserlich Tracker] JumpToLowMarkerFrame -> frame={frame}")

        return {"FINISHED"}


# --- Registrierung ----------------------------------------------------------

classes = (
    KAISERLICHTRACKER_OT_jump_to_low_marker_frame,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
