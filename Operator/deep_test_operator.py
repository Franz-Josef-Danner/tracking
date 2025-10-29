# Operator/deep_test_operator.py
import bpy
import time
import math
from typing import Optional, List, Dict, Any, Tuple, Set
from collections import deque
from dataclasses import dataclass, field

# ---- Helper-Importe ---------------------------------------------------------
from ..Helper.util_clip import get_active_clip
from ..Helper.scene import get_end_frame
from ..Helper.reset_helper import reset_all_thresholds
from ..Helper.playhead_helper import reset_to_frame
from ..Helper.newmarker import classify_markers
from ..Helper.find_clip_editor_area import find_clip_editor_area
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.detect import detect_features
from ..Helper.cleaneup import cleanup_new_markers
from ..Helper.delete import delete_tracks_by_names
from ..Helper.track_length_helper import get_total_track_length
from ..Helper.selection_helper import collect_selected_track_names
from ..Helper.formula_helper import apply_formula_on_selected_tracks
from ..Helper.track_markers_helper import track_markers_with_override
from ..Helper.filter_active_tracks import filter_active_tracks_at_frame
from ..Helper.util_scene import set_scene_props
from ..Helper.init_detect_state import init_detect_state

# ---- Szenen Keys ------------------------------------------------------------
SCENE_TOTAL_TRACK_LEN_BASE  = "kaiserlich_len_baseline_00"
SCENE_TOTAL_TRACK_LEN_STEP1 = "kaiserlich_len_rot_xy_00"
SCENE_TOTAL_TRACK_LEN_STEP2 = "kaiserlich_len_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP3 = "kaiserlich_len_rot_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP4 = "kaiserlich_len_perspective_0"

# ---- DeepTest Parameter -----------------------------------------------------
REDUCTION_STEPS = [0.05, 0.5, 0.8, 0.9, 0.95, 0.98, 0.99]
MIN_THRESHOLD_VAL = 0.00001


class KAISERLICHTRACKER_OT_deep_test_operator(bpy.types.Operator):
    """Kaiserlich Tracker — Deep Test (sequentiell, wie ShortTest-Ablauf)"""
    bl_idname = "kaiserlich_tracker.deep_test_operator"
    bl_label = "Kaiserlich Tracker — Deep Threshold Test"
    bl_options = {'REGISTER', 'UNDO'}

    # ------------------------------------------------------------------------
    # Execute (einmaliger sequentieller Ablauf, nicht modal)
    # ------------------------------------------------------------------------
    def execute(self, context: bpy.types.Context):

        scene = context.scene
        clip = get_active_clip(context)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver MovieClip gefunden.")
            return {'CANCELLED'}

        # --- Initialisierung (ShortTest-Parität) ---
        reset_all_thresholds(context, active_props=[])
        print("[DeepTest] Thresholds reset (ShortTest-Parität).")

        # Dummy Detect-Run für Pufferinitialisierung
        detect_features(
            context,
            placement='FRAME',
            margin=100,
            threshold=0.0001,
            min_distance=100
        )
        delete_tracks_by_names(context, [t.name for t in clip.tracking.tracks])
        print("[DeepTest] Dummy Detect ausgeführt (ShortTest DummyPass).")

        # State vorbereiten
        start_frame = scene.frame_start
        end_frame = get_end_frame(context)
        if end_frame < start_frame:
            end_frame = start_frame
        reset_to_frame(context, start_frame)

        hz = vc = 1
        try:
            s = init_detect_state(context)
            hz, vc = s["hz"], s["vc"]
        except Exception:
            pass

        # --- Kategorie-Sequenz vorbereiten ---
        categories = ["rot_xy", "scale_min", "scale_max", "rot_scale_rot", "rot_scale_scale", "perspective"]
        results: Dict[str, int] = {}
        base_total = 0

        print(f"[DeepTest] Starte Threshold-Test für Kategorien: {categories}")

        # --------------------------------------------------------------------
        # Haupt-Testloop (1x Detect/Track/Messung pro Threshold-Stufe)
        # --------------------------------------------------------------------
        for cat in categories:
            print(f"\n[DeepTest] → Kategorie {cat}")
            base_val = 1.0
            goal_len = 0
            for i, factor in enumerate(REDUCTION_STEPS, 1):
                curr_val = max(MIN_THRESHOLD_VAL, base_val * factor)

                # --- Threshold setzen je Kategorie ---
                if cat == "rot_xy":
                    ratio_vh = (vc / hz) if hz else 1.0
                    delta = (math.log10(1 * 1_000_000) - math.log10(curr_val * 1_000_000))
                    adj = pow((delta * ratio_vh), 10) / 1_000_000
                    rot_x = curr_val
                    rot_y = rot_x + adj
                    set_scene_props(scene, kaiserlich_rot_thresh_x=rot_x, kaiserlich_rot_thresh_y=rot_y)

                elif cat == "scale_min":
                    set_scene_props(scene, kaiserlich_scale_thresh_min=curr_val, kaiserlich_scale_thresh_max=0.0)

                elif cat == "scale_max":
                    set_scene_props(scene, kaiserlich_scale_thresh_max=curr_val)

                elif cat == "rot_scale_rot":
                    set_scene_props(scene, kaiserlich_rot_scale_thresh_rot=curr_val, kaiserlich_rot_scale_thresh_scale=0.0)

                elif cat == "rot_scale_scale":
                    set_scene_props(scene, kaiserlich_rot_scale_thresh_rot=0.0, kaiserlich_rot_scale_thresh_scale=curr_val)

                elif cat == "perspective":
                    set_scene_props(scene, kaiserlich_perspective_thresh=curr_val)

                print(f"[DeepTest] Step {i}/{len(REDUCTION_STEPS)} | {cat} = {curr_val:.6f}")

                # --------------------------------------------------------------
                # Detect-Adapt (ShortTest-Logik)
                # --------------------------------------------------------------
                pre_snapshot = snapshot_active_markers(context)
                detect_features(
                    context,
                    placement='FRAME',
                    margin=100,
                    threshold=0.0001,
                    min_distance=100
                )
                post_snapshot = snapshot_active_markers(context)
                alte_marker, neue_marker = classify_markers(pre_snapshot, post_snapshot)
                cleaned_new, _ = cleanup_new_markers(context, alte_marker, neue_marker, pz=50, hz=hz, vc=vc)

                if not cleaned_new:
                    print("[DeepTest] ⚠ Keine Marker gefunden, breche diese Stufe ab.")
                    continue

                # Alle Marker selektieren
                for trk in clip.tracking.tracks:
                    trk.select = True

                # --------------------------------------------------------------
                # Tracking-Cycle (ShortTest-gleich)
                # --------------------------------------------------------------
                window, area, region, space = find_clip_editor_area(clip)
                if not window:
                    raise RuntimeError("Keine CLIP_EDITOR Area gefunden.")

                current = start_frame
                scene.frame_current = current
                space.clip_user.frame_current = current
                active_tracks = [t.name for t in clip.tracking.tracks]

                while active_tracks and current <= end_frame:
                    active_tracks, _ = filter_active_tracks_at_frame(context, active_tracks, current)
                    if not active_tracks:
                        break

                    apply_formula_on_selected_tracks(context, max_frames=5)
                    success = track_markers_with_override(window, area, region, space, backwards=False, sequence=False)
                    if not success:
                        print("[DeepTest] Tracking-Fehler, Abbruch.")
                        break

                    current += 1
                    scene.frame_current = current
                    space.clip_user.frame_current = current

                # --------------------------------------------------------------
                # Track-Länge messen (ShortTest-Parität)
                # --------------------------------------------------------------
                bpy.context.view_layer.update()
                total_len = int(get_total_track_length(context, start_frame=start_frame))
                print(f"[DeepTest] Total Track Length = {total_len}")

                if i == 1 and cat == "rot_xy":
                    base_total = total_len
                    scene[SCENE_TOTAL_TRACK_LEN_BASE] = total_len

                # Nur speichern, wenn besser als vorherige Kategorie-Ziel
                if total_len > goal_len:
                    goal_len = total_len
                    results[cat] = total_len

                # Cleanup nach Messung
                delete_tracks_by_names(context, [t.name for t in clip.tracking.tracks])
                reset_to_frame(context, start_frame)
                bpy.context.view_layer.update()

                # Stopp, wenn keine Verbesserung mehr auftritt
                if total_len <= goal_len and i > 2:
                    print("[DeepTest] Keine Verbesserung mehr → nächste Kategorie.")
                    break

                base_val = curr_val

            print(f"[DeepTest] ✅ Kategorie {cat} abgeschlossen | Beste Länge={goal_len}")

        # --------------------------------------------------------------------
        # Ergebnisse speichern (ShortTest-konform)
        # --------------------------------------------------------------------
        if results:
            if "rot_xy" in results:
                scene[SCENE_TOTAL_TRACK_LEN_STEP1] = results["rot_xy"]
            if "scale_min" in results or "scale_max" in results:
                scene[SCENE_TOTAL_TRACK_LEN_STEP2] = max(results.get("scale_min", 0), results.get("scale_max", 0))
            if "rot_scale_rot" in results or "rot_scale_scale" in results:
                scene[SCENE_TOTAL_TRACK_LEN_STEP3] = max(results.get("rot_scale_rot", 0), results.get("rot_scale_scale", 0))
            if "perspective" in results:
                scene[SCENE_TOTAL_TRACK_LEN_STEP4] = results["perspective"]

        print("\n[DeepTest] Ergebnisvergleich:")
        print(f" Base={scene.get(SCENE_TOTAL_TRACK_LEN_BASE, 0)}")
        print(f" RotXY={scene.get(SCENE_TOTAL_TRACK_LEN_STEP1, 0)}")
        print(f" Scale={scene.get(SCENE_TOTAL_TRACK_LEN_STEP2, 0)}")
        print(f" RotScale={scene.get(SCENE_TOTAL_TRACK_LEN_STEP3, 0)}")
        print(f" Perspective={scene.get(SCENE_TOTAL_TRACK_LEN_STEP4, 0)}")

        self.report({'INFO'}, "Deep Test abgeschlossen (ShortTest-Parität).")
        return {'FINISHED'}


# ------------------------------------------------------------------------
# Registration
# ------------------------------------------------------------------------
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_deep_test_operator)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_deep_test_operator)
