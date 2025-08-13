import bpy
from bpy.types import Operator

def _clip_override(context):
    """Sicherer CLIP_EDITOR-Override."""
    win = context.window
    if not win:
        return None
    scr = getattr(win, "screen", None)
    if not scr:
        return None
    for area in scr.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return {'area': area, 'region': region, 'space_data': area.spaces.active}
    return None


def _get_clip(context):
    space = getattr(context, "space_data", None)
    if space and getattr(space, "clip", None):
        return space.clip
    return bpy.data.movieclips[0] if bpy.data.movieclips else None


class CLIP_OT_main(Operator):
    """Pre-Detect-Funnel: Vorprüfung, Tracker-Setup, Bounds, detect_once. Kein Pipeline/Solve."""
    bl_idname = "clip.main"
    bl_label = "Main (Pre → DetectOnce)"
    bl_options = {'REGISTER', 'UNDO'}

    use_override: bpy.props.BoolProperty(
        name="CLIP-Override",
        description="Im Kontext des CLIP_EDITOR ausführen (empfohlen)",
        default=True
    )

    marker_adapt: bpy.props.IntProperty(
        name="Marker Adapt",
        description="Übergebener Ableitungswert zur Bounds-Berechnung",
        default=0, min=0
    )

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        clip = _get_clip(context)
        if clip is None or not getattr(clip, "tracking", None):
            self.report({'ERROR'}, "Kein gültiger MovieClip oder keine Tracking-Daten.")
            return {'CANCELLED'}

        scene = context.scene
        self._reset_scene_flags(scene)

        override = _clip_override(context) if self.use_override else None
        mgr = None

        try:
            if override:
                mgr = context.temp_override(**override)
                mgr.__enter__()

            print(f"📏 Marker-Bounds gesetzt: min={scene['marker_min']} max={scene['marker_max']} "
                  f"(Basis {basis_for_bounds}, Quelle: {src}, adapt_in={marker_adapt_in})")


            # --- Threshold bestimmen (Fallback: Tracker-Default) ---
            settings = clip.tracking.settings
            detection_threshold = float(
                scene.get("last_detection_threshold",
                          getattr(settings, "default_correlation_min", 0.75))
            )

            # --- Einmaliger Detect (stateless, non-modal) ---
            print("📡 Übergabe an detect_once …")
            bpy.ops.clip.detect_once('EXEC_DEFAULT',
                                     detection_threshold=detection_threshold,
                                     marker_adapt=int(basis_for_bounds),
                                     min_marker=int(scene["marker_min"]),
                                     max_marker=int(scene["marker_max"]),
                                     frame=int(scene.frame_current),
                                     margin_base=-1,
                                     min_distance_base=-1,
                                     close_dist_rel=0.01)

            print("✅ Main beendet nach detect_once (ohne Pipeline/Solve).")
            return {'FINISHED'}

        except Exception as ex:
            self.report({'ERROR'}, f"Main-Abbruch: {ex}")
            return {'CANCELLED'}

        finally:
            if mgr is not None:
                try:
                    mgr.__exit__(None, None, None)
                except Exception:
                    pass


def register():
    try:
        bpy.utils.register_class(CLIP_OT_main)
    except ValueError:
        pass

def unregister():
    try:
        bpy.utils.unregister_class(CLIP_OT_main)
    except ValueError:
        pass
