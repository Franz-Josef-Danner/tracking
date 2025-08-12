# main.py — "Main bis Übergabe an detect_once" (alle Pre-Detect-Schritte + Bounds-Formel, kein Modal)

import bpy
from bpy.types import Operator

# Helper, die VOR detect benötigt werden:
from ..Helper.find_low_marker_frame import find_low_marker_frame
from ..Helper.jump_to_frame import jump_to_frame


def _clip_override(context):
    """Sicheren CLIP_EDITOR-Override (area/region/space_data) liefern."""
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
    """Aktiven MovieClip ermitteln, Fallback auf erstes MovieClip."""
    space = getattr(context, "space_data", None)
    if space and getattr(space, "clip", None):
        return space.clip
    return bpy.data.movieclips[0] if bpy.data.movieclips else None


class CLIP_OT_main(Operator):
    """Führt alle Pre-Detect-Schritte aus und übergibt dann direkt an detect_once.
    Kein Modal, keine Rückkehr, keine Solve-/Cleanup-Logik."""
    bl_idname = "clip.main"
    bl_label = "Main (Pre-Detect → DetectOnce, ohne Rückkehr)"
    bl_options = {'REGISTER', 'UNDO'}

    use_override: bpy.props.BoolProperty(
        name="CLIP-Override",
        description="Im Kontext des CLIP_EDITOR ausführen (empfohlen)",
        default=True
    )

    # Optionaler externer Einfluss auf Marker-Bounds
    marker_adapt: bpy.props.IntProperty(
        name="Marker Adapt",
        description="Optionaler Ableitungswert für Marker-Bounds (nur Pre-Phase)",
        default=0, min=0
    )

    def _reset_scene_flags(self, scene):
        """Initiale Scene-Keys wie im bisherigen Pre-Flow zurücksetzen."""
        scene["solve_status"] = ""
        scene["solve_error"] = -1.0
        scene["solve_watch_fallback"] = False
        scene["pipeline_status"] = ""
        scene["marker_min"] = 0
        scene["marker_max"] = 0
        scene["goto_frame"] = -1

        # Error-Limit Snapshot wie gehabt
        try:
            scene["error_limit_run"] = float(getattr(scene, "error_track"))
        except Exception:
            scene["error_limit_run"] = float(scene.get("error_track", 0.0))

        # Optional vorhandene Repeat-Collection leeren (keine Modal-Zyklen mehr)
        if hasattr(scene, "repeat_frame"):
            try:
                scene.repeat_frame.clear()
            except Exception:
                pass

    def _precheck_and_jump(self, context, clip):
        """Vorprüfung: Low-Marker-Frame suchen und ggf. Playhead setzen."""
        scene = context.scene
        marker_basis = scene.get("marker_basis", 25)

        pre_frame = find_low_marker_frame(clip, marker_basis=marker_basis)
        if pre_frame is None:
            print("✅ Vorprüfung: Keine Low-Marker-Frames. (Fortsetzung trotzdem bis detect)")
            return

        # Low-Marker gefunden → Playhead setzen (wie bisher)
        scene["goto_frame"] = int(pre_frame)
        jump_to_frame(context)
        print(f"🎯 Vorprüfung: Low-Marker-Frame {pre_frame} – starte Setup ab diesem Frame.")

    def execute(self, context):
        # --- Sanity ---
        clip = _get_clip(context)
        if clip is None or not getattr(clip, "tracking", None):
            self.report({'ERROR'}, "Kein gültiger MovieClip oder keine Tracking-Daten.")
            return {'CANCELLED'}

        scene = context.scene
        self._reset_scene_flags(scene)

        # --- Optionaler CLIP_EDITOR-Override ---
        override = _clip_override(context) if self.use_override else None
        cx = context if not override else context.temp_override(**override)

        try:
            mgr = cx if override else None
            if mgr:
                mgr.__enter__()

            # --- Pre-Detect: Vorprüfung und Playhead-Positionierung ---
            self._precheck_and_jump(context, clip)

            # --- Pre-Detect: Tracker-/Marker-Setup ---
            print("🚀 Vorbereitung: tracker_settings …")
            bpy.ops.clip.tracker_settings('EXEC_DEFAULT')

            print("🧰 Vorbereitung: marker_helper_main …")
            bpy.ops.clip.marker_helper_main('EXEC_DEFAULT')

            # --- Bounds-Formel VOR Übergabe an detect_once ---
            marker_basis = int(scene.get("marker_basis", 25))
            marker_adapt_val = int(getattr(self, "marker_adapt", 0))
            basis_for_bounds = int(marker_adapt_val * 1.1) if marker_adapt_val > 0 else int(marker_basis)
            scene["marker_min"] = int(basis_for_bounds * 0.9)
            scene["marker_max"] = int(basis_for_bounds * 1.1)
            print(f"📏 Marker-Bounds gesetzt: min={scene['marker_min']} max={scene['marker_max']} (Basis {basis_for_bounds})")

            # --- Threshold bestimmen (Fallback auf Tracker-Default) ---
            settings = clip.tracking.settings
            detection_threshold = float(scene.get("last_detection_threshold", getattr(settings, "default_correlation_min", 0.75)))

            # --- (Optional) Pipeline-Prep, wie gehabt ---
            print("🎬 Starte Tracking-Pipeline …")
            bpy.ops.clip.tracking_pipeline('INVOKE_DEFAULT')

            # --- HARTE SCHNITTSTELLE: Direkt an detect_once übergeben ---
            print("📡 Übergabe an detect_once …")
            bpy.ops.clip.detect_once('INVOKE_DEFAULT',
                detection_threshold=detection_threshold,
                marker_adapt=int(basis_for_bounds),
                min_marker=int(scene["marker_min"]),
                max_marker=int(scene["marker_max"]),
                frame=int(scene.frame_current),
                margin_base=-1,          # auto aus Bildbreite
                min_distance_base=-1,    # auto aus Bildbreite
                close_dist_rel=0.01,
            )

            print("✅ Main beendet nach Übergabe an detect_once (ohne Rückkehr).")
            return {'FINISHED'}

        except Exception as ex:
            self.report({'ERROR'}, f"Main-Abbruch: {ex}")
            return {'CANCELLED'}

        finally:
            if override and 'mgr' in locals() and mgr:
                try:
                    mgr.__exit__(None, None, None)
                except Exception:
                    pass


# Lokale Registrierung (falls nicht zentral in __init__ gehandhabt)
def register():
    try:
        bpy.utils.register_class(CLIP_OT_main)
    except ValueError:
        pass  # bereits registriert


def unregister():
    try:
        bpy.utils.unregister_class(CLIP_OT_main)
    except ValueError:
        pass
