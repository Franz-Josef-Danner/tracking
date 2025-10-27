import bpy
from typing import Any, Optional, Set, Dict, Callable, ContextManager, List, Tuple, Deque
from contextlib import contextmanager
import math
import time

# Helper imports that were used across the original operators.  These helpers
# encapsulate low‑level logic for threshold management, track detection,
# cleanup and tracking.  By importing them here we avoid any calls into
# other Blender operators and instead drive the workflow directly.
from ..Helper.low_marker_frame import find_first_weak_frame
from ..Helper.filter_tracks import filter_problematic_tracks
from ..Helper.thresh_map import (
    should_use_cached_thresholds,
    save_after_autocalibrate,
)
from ..Helper.bootstrap import run_bootstrap

# Auto‑calibrate helpers
from ..Helper.util_thresholds import set_all_thresholds_to_one
from ..Helper.util_shorttest import short_test_pipeline, compare_len_steps_to_total
from ..Helper.util_scene import set_scene_props
from ..Helper.util_reduce import (
    reduce_rot_xy,
    reduce_scale_min_max,
    reduce_rot_scale_pair,
    reduce_perspective,
)
from ..Helper.util_format import fmt8
from ..Helper.util_deeptest import (
    SCENE_DEEPTEST_ROT_XY_BEST,
    SCENE_DEEPTEST_SCALE_BEST,
    SCENE_DEEPTEST_ROT_SCALE_BEST,
    SCENE_DEEPTEST_PERSPECTIVE_BEST,
)

# Detection helpers
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.detect import detect_features
from ..Helper.newmarker import classify_markers
from ..Helper.cleaneup import cleanup_new_markers
from ..Helper.delete import delete_tracks_by_names

# Inline tracking helpers
from ..Helper.find_clip_editor_area import find_clip_editor_area
from ..Helper.collect_selected_tracks import collect_selected_track_names
from ..Helper.filter_active_tracks import filter_active_tracks_at_frame
from ..Helper.track_markers_helper import track_markers_with_override
from ..Helper.formula_helper import apply_formula_on_selected_tracks
from ..Helper.playhead_helper import reset_to_frame
from ..Helper.scene import get_end_frame
from ..Helper.playhead_helper import get_start_frame as ph_get_start_frame
from ..Helper.track_length_helper import get_total_track_length

# Context & selection utilities from the original master operator.  These
# remain largely unchanged and are used to manage context overrides and
# selections.
def _find_clip_editor_area_for_clip(clip: Optional[bpy.types.MovieClip]):
    """Find a CLIP_EDITOR area (with matching space/region) for context override."""
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
                if getattr(space, "clip", None) == clip or space.clip is None:
                    return window, area, region_window, space
    return None, None, None, None

def _get_active_clip(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    sd = getattr(context, "space_data", None)
    return getattr(sd, "clip", None) if sd else None

def _coerce_frame(result: Any) -> Optional[int]:
    """Allows flexible return types from find_first_weak_frame."""
    if result is None:
        return None
    if isinstance(result, int):
        return int(result)
    if isinstance(result, (tuple, list)) and result:
        first = result[0]
        return int(first) if isinstance(first, (int, float)) else None
    return None

def _snapshot_selected_track_names(clip: Optional[bpy.types.MovieClip]) -> Set[str]:
    names: Set[str] = set()
    if not clip:
        return names
    tracking = clip.tracking
    for track in tracking.tracks:
        if getattr(track, "select", False):
            names.add(track.name)
    return names

def _restore_selected_tracks_by_names(clip: Optional[bpy.types.MovieClip], names: Set[str]) -> None:
    if not clip or not names:
        return
    tracking = clip.tracking
    for track in tracking.tracks:
        track.select = False
    for track in tracking.tracks:
        if track.name in names:
            track.select = True

def _set_frame_in_scene_and_clip(context: bpy.types.Context, frame: int) -> None:
    """Set the playhead globally and in the clip editor (if possible)."""
    context.scene.frame_current = int(frame)
    clip = _get_active_clip(context)
    window, area, region, space = _find_clip_editor_area_for_clip(clip)
    if window and area and region and space:
        try:
            with bpy.context.temp_override(window=window, area=area, region=region, space_data=space, scene=context.scene):
                bpy.ops.clip.change_frame(frame=int(frame))
        except Exception:
            try:
                region.tag_redraw()
            except Exception:
                pass

@contextmanager
def _clip_context(context: bpy.types.Context, clip: Optional[bpy.types.MovieClip]) -> ContextManager[None]:
    """
    Provides a safe override context for CLIP_EDITOR operators via temp_override.
    Only allowed keys; no 'screen' (internally derived from window).
    """
    window, area, region, space = _find_clip_editor_area_for_clip(clip)
    if window and area and region and space:
        with bpy.context.temp_override(window=window, area=area, region=region, space_data=space, scene=context.scene):
            yield
    else:
        yield

class KAISERLICHTRACKER_OT_master_operator(bpy.types.Operator):
    """
    Iterative low‑marker pipeline: low_marker_frame -> (auto_calibrate?) ->
    detect_adapt -> track_backwards -> track_forwards, until no low‑marker
    frame exists.  This version embeds the full logic of all called
    operators inline, removing any nested bpy.ops.kaiserlich_tracker.* calls.
    """
    bl_idname = "kaiserlich_tracker.master_operator"
    bl_label = "KAISERLICHTRACKER — Master Operator"
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

    max_iterations: bpy.props.IntProperty(
        name="Max Iterationen",
        description="Safety-Stop gegen Endlosschleifen",
        default=100,
        min=1,
        soft_min=1,
    )

    # ---------------------------------------------------------------------
    #  Inline implementations of dependent operators
    # ---------------------------------------------------------------------

    def _auto_calibrate_inline(self, context: bpy.types.Context) -> None:
        """
        Perform the auto-calibration workflow inline.  This mirrors the logic
        of KAISERLICHTRACKER_OT_auto_calibrate without invoking any other
        operators.
        """
        scene = context.scene
        report = lambda msg: self.report({'INFO'}, msg)

        # 1) Reset all thresholds to 1.0
        set_all_thresholds_to_one(context)
        report("Kaiserlich Tracker: Thresholds auf 1.0 gesetzt.")

        # 2) Run the short-test pipeline (baseline + steps) without deleting tracks
        try:
            results = short_test_pipeline(context=context, tracks_to_delete=None, report_fn=report)
            report(f"Short-Test abgeschlossen | "
                   f"Base={results['baseline']} | "
                   f"Step1={results['step1']} | "
                   f"Step2={results['step2']} | "
                   f"Step3={results['step3']} | "
                   f"Step4={results['step4']}")
        except Exception as e:
            # If short-test fails, surface an error to the user
            self.report({'ERROR'}, f"Short-Test fehlgeschlagen: {e}")
            return

        # 3) Compare the lengths of each step to the baseline
        cmp = compare_len_steps_to_total(context)
        base = int(cmp.get("baseline") or 0)
        vals = cmp.get("values", {})
        rels = cmp.get("relations", {})
        ge_list = cmp.get("better_or_equal", [])

        report(f"Vergleich: Base={base} | "
               f"Step1={vals.get('STEP1')}({rels.get('STEP1')}) "
               f"Step2={vals.get('STEP2')}({rels.get('STEP2')}) "
               f"Step3={vals.get('STEP3')}({rels.get('STEP3')}) "
               f"Step4={vals.get('STEP4')}({rels.get('STEP4')})")
        report("≥ Baseline: " + (", ".join(ge_list) if ge_list else "keine"))

        # 4) Perform long tests (deep reductions) for each step that meets or exceeds the baseline
        # Step 1 – Rotation XY
        if "STEP1" in ge_list:
            try:
                target = max(base, int(vals.get("STEP1") or 0))
                r = reduce_rot_xy(context, target_len=target, report_fn=report)
                scene[SCENE_DEEPTEST_ROT_XY_BEST] = int(target)
                best = r.get("best", {})
                val = best.get("values")
                if best.get("sf") and val and len(val) == 2:
                    set_scene_props(scene,
                        kaiserlich_rot_thresh_x=float(val[0]),
                        kaiserlich_rot_thresh_y=float(val[1]))
                    ratio = best.get("ratio")
                    report(f"[Reduce RotXY] sf={fmt8(best['sf'])} "
                           f"→ ({fmt8(val[0])}, {fmt8(val[1])}) "
                           f"{'(ratio='+fmt8(ratio)+')' if ratio else ''}")
            except Exception as e:
                self.report({'WARNING'}, f"STEP1 RotXY-Reducer: {e}")

        # Step 2 – Scale Min/Max
        if "STEP2" in ge_list:
            try:
                target = max(base, int(vals.get("STEP2") or 0))
                r = reduce_scale_min_max(context, target_len=target, report_fn=report)
                scene[SCENE_DEEPTEST_SCALE_BEST] = int(target)
                best = r.get("best", {})
                val = best.get("values")
                if best.get("sf") and val and len(val) == 2:
                    set_scene_props(scene,
                        kaiserlich_scale_thresh_min=float(val[0]),
                        kaiserlich_scale_thresh_max=float(val[1]))
                    report(f"[Reduce Scale] sf={fmt8(best['sf'])} "
                           f"→ ({fmt8(val[0])}, {fmt8(val[1])})")
            except Exception as e:
                self.report({'WARNING'}, f"STEP2 Scale-Reducer: {e}")

        # Step 3 – Rotation + Scale Pair
        if "STEP3" in ge_list:
            try:
                target = max(base, int(vals.get("STEP3") or 0))
                r = reduce_rot_scale_pair(context, target_len=target, report_fn=report)
                scene[SCENE_DEEPTEST_ROT_SCALE_BEST] = int(target)
                best = r.get("best", {})
                val = best.get("values")
                if best.get("sf") and val and len(val) == 2:
                    set_scene_props(scene,
                        kaiserlich_rot_scale_thresh_rot=float(val[0]),
                        kaiserlich_rot_scale_thresh_scale=float(val[1]))
                    report(f"[Reduce Rot+Scale] sf={fmt8(best['sf'])} "
                           f"→ ({fmt8(val[0])}, {fmt8(val[1])})")
            except Exception as e:
                self.report({'WARNING'}, f"STEP3 RotScale-Reducer: {e}")

        # Step 4 – Perspective
        if "STEP4" in ge_list:
            try:
                target = max(base, int(vals.get("STEP4") or 0))
                r = reduce_perspective(context, target_len=target, report_fn=report)
                scene[SCENE_DEEPTEST_PERSPECTIVE_BEST] = int(target)
                best = r.get("best", {})
                val = best.get("value")
                if best.get("sf") and val is not None:
                    set_scene_props(scene, kaiserlich_perspective_thresh=float(val))
                    report(f"[Reduce Perspective] sf={fmt8(best['sf'])} "
                           f"→ {fmt8(val)}")
            except Exception as e:
                self.report({'WARNING'}, f"STEP4 Perspective-Reducer: {e}")

        report("Auto-Calibrate erfolgreich abgeschlossen.")

    def _detect_adapt_inline(self, context: bpy.types.Context) -> None:
        """
        Perform the adaptive marker detection inline.  This replicates the
        logic of KAISERLICHTRACKER_OT_detect_adapt without invoking another
        operator.
        """
        scene = context.scene
        ef_target = int(scene.kaiserlich_markers_per_frame)

        # Load bootstrap parameters if available, otherwise compute fallback
        params = scene.get("bootstrap_params", None)
        if params:
            md = float(params.get('md', 100))
            ma = int(params.get('ma', 30))
            tr = float(params.get('tr', 0.5))
            pz = int(params.get('pz', 50))
            sz = int(params.get('sz', 0))
            hz = params.get('hz', 1)
            vc = params.get('vc', False)
        else:
            # Fallback bootstrap: derive parameters from the active clip
            clip = getattr(context.space_data, "clip", None)
            if clip is None:
                self.report({'ERROR'}, "Kein aktiver Clip verfügbar (Fallback fehlgeschlagen).")
                return
            # Basic information from clip
            hz = clip.size[0]
            vc = clip.size[1]
            scene_obj = getattr(context, "scene", None)
            frame_end = scene_obj.frame_end if scene_obj else None
            # Parameters from tracking settings
            tracking_settings = getattr(clip.tracking, "settings", None)
            ma = getattr(tracking_settings, "margin", 100) if tracking_settings else 100
            pz = getattr(tracking_settings, "pattern_size", 50) if tracking_settings else 50
            sz = getattr(tracking_settings, "search_size", 100) if tracking_settings else 100
            # Derived start values
            md = hz * 0.025
            tr = 0.0001
            za = ef_target * 4
            og = math.ceil(za * 1.1)
            ug = math.floor(za * 0.9)
            print(f"[Kaiserlich Tracker][DetectAdapt][Fallback] "
                  f"hz={hz}, vc={vc}, margin={ma}, md={md:.2f}, "
                  f"pattern={pz}, search={sz}, tr={tr}, og={og}, ug={ug}, frame_end={frame_end}")

        # Baseline-fix: separate the concepts of pre_snapshot and baseline track names
        pre_snapshot = snapshot_active_markers(context)
        clip = getattr(context.space_data, "clip", None)
        tracking = getattr(clip, "tracking", None) if clip else None
        baseline_start_tracknames = set()
        if tracking:
            baseline_start_tracknames = {t.name for t in tracking.tracks}
        print(f"[Kaiserlich Tracker][DetectAdapt] Ausgangsmarker: {len(pre_snapshot)} | "
              f"BaselineTracks: {len(baseline_start_tracknames)}")

        # Adaptive loop
        max_loops = 8
        loop = 0
        frame_num = scene.frame_current
        # Attempt to load previously stored min_distance for this frame, or interpolate between known frames
        if "min_distance_values" in scene:
            md_dict = scene["min_distance_values"]
            if str(frame_num) in md_dict:
                last_md = float(md_dict[str(frame_num)])
            else:
                if "known_frames" in md_dict and len(md_dict["known_frames"]) >= 2:
                    known = sorted(md_dict["known_frames"])
                    prev_frames = [f for f in known if f < frame_num]
                    next_frames = [f for f in known if f > frame_num]
                    if prev_frames and next_frames:
                        f1 = max(prev_frames)
                        f2 = min(next_frames)
                        v1 = float(md_dict[str(f1)])
                        v2 = float(md_dict[str(f2)])
                        t = (frame_num - f1) / (f2 - f1)
                        last_md = v1 + (v2 - v1) * t
                    else:
                        last_md = md
                else:
                    last_md = md
        else:
            last_md = md

        deleted_old = 0
        while loop < max_loops:
            loop += 1
            print(f"\n[Kaiserlich Tracker][DetectAdapt] --- LOOP {loop} ---")
            print(f"[Kaiserlich Tracker][DetectAdapt] Aktuelles min_distance = {last_md:.2f}")

            # Perform detect
            detect_features(
                context,
                placement='FRAME',
                margin=ma,
                threshold=tr,
                min_distance=int(max(1, round(last_md)))
            )

            # After detection Blender automatically selects all new tracks; reset selection
            clip = getattr(context.space_data, 'clip', None)
            if clip and getattr(clip, 'tracking', None):
                for trk in clip.tracking.tracks:
                    try:
                        trk.select = False
                    except Exception:
                        pass

            # Snapshot after detect and classify new vs old markers
            post_snapshot = snapshot_active_markers(context)
            alte_marker, neue_marker = classify_markers(pre_snapshot, post_snapshot)

            print(f"[Kaiserlich Tracker][DetectAdapt] Alte Marker erkannt: {len(alte_marker)}")
            print(f"[Kaiserlich Tracker][DetectAdapt] Neue Marker erkannt: {len(neue_marker)}")
            if len(neue_marker) > 0:
                print("   ➤ Beispiel neue Marker:", [m['track'] for m in neue_marker[:5]])
            if len(alte_marker) > 0:
                print("   ➤ Beispiel alte Marker:", [m['track'] for m in alte_marker[:5]])

            am = len(neue_marker)

            # Cleanup new markers and remove close duplicates
            cleaned_new, deleted_old = cleanup_new_markers(
                context,
                alte_marker,
                neue_marker,
                pz=pz,
                hz=hz,
                vc=vc
            )

            deleted_old_names = [
                m['track'] for m in alte_marker
                if m['track'] not in [n['track'] for n in post_snapshot]
            ]
            if deleted_old_names:
                print(f"[⚠️ Kaiserlich Tracker][DetectAdapt] WARNUNG: Alte Marker gelöscht: {deleted_old_names}")

            print(f"[Kaiserlich Tracker][DetectAdapt] Nach Cleanup: {len(cleaned_new)} neue Marker übrig, {deleted_old} alte gelöscht")

            remaining = len(cleaned_new)
            diff = remaining - ef_target
            tolerance = ef_target * 0.10  # 10 % tolerance
            if abs(diff) <= tolerance:
                print(f"[Kaiserlich Tracker][DetectAdapt] Ziel erreicht: "
                      f"{remaining}/{ef_target} Marker (Toleranz ±{tolerance:.1f})")
                break

            # Dynamically adjust min_distance for next iteration
            if am > 0:
                ratio = ef_target / am
                factor = max(0.5, min(2.0, ratio))
                new_md = last_md / factor
                last_md = max(1.0, new_md)
            else:
                last_md = last_md * 1.5
                print("[Kaiserlich Tracker][DetectAdapt] Keine neuen Marker, erhöhe min_distance stark")

            # Delete new markers before next iteration
            if loop < max_loops:
                delete_tracks_by_names(context, [m['track'] for m in neue_marker])
                print(f"[Kaiserlich Tracker][DetectAdapt] {len(neue_marker)} neue Marker gelöscht für nächsten Zyklus")
                # Sleep briefly to allow Blender UI to update
                time.sleep(0.1)

        # Select the final new markers (tracks not in the baseline)
        clip = getattr(context.space_data, 'clip', None)
        if clip and getattr(clip, 'tracking', None):
            tracking = clip.tracking
            new_tracks = [trk for trk in tracking.tracks if trk.name not in baseline_start_tracknames]
            try:
                for trk in tracking.tracks:
                    trk.select = False
                for new_trk in new_tracks:
                    new_trk.select = True
                print(f"[Kaiserlich Tracker][DetectAdapt] Final selektierte Marker: {len(new_tracks)}")
            except Exception:
                pass

        # Persist the frame-specific min_distance and interpolate between known frames
        frame_num = scene.frame_current
        md_value = float(last_md)
        if "min_distance_values" not in scene:
            scene["min_distance_values"] = {}
        md_dict = scene["min_distance_values"]
        known_list = list(md_dict.get("known_frames", []))
        if frame_num not in known_list:
            known_list.append(frame_num)
            known_list.sort()
        md_dict["known_frames"] = known_list
        md_dict[str(frame_num)] = md_value

        if len(known_list) > 1:
            for i in range(len(known_list) - 1):
                f_start = known_list[i]
                f_end = known_list[i + 1]
                if f_end - f_start < 2:
                    continue
                v_start = float(md_dict[str(f_start)])
                v_end = float(md_dict[str(f_end)])
                for f in range(f_start + 1, f_end):
                    t = (f - f_start) / float(f_end - f_start)
                    interp_val = v_start + (v_end - v_start) * t
                    md_dict[str(f)] = interp_val

        print(f"[Kaiserlich Tracker][DetectAdapt] Frame {frame_num}: final min_distance = {md_value:.2f}")

    def _run_backward_track_inline(self, context: bpy.types.Context) -> Dict[str, Any]:
        """
        Execute a full backward tracking cycle inline.  This mirrors the
        implementation from track_operator_backwards.run_backward_track_inline,
        iterating from the scene's end frame down to the start frame.
        """
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if not clip:
            raise RuntimeError("Kein aktiver Clip (Backwards Inline).")

        window, area, region, space = find_clip_editor_area(clip)
        if not window:
            raise RuntimeError("Keine CLIP_EDITOR Area gefunden (Backwards Inline).")

        start_frame = getattr(scene, "frame_start", 1)
        end_frame = getattr(scene, "frame_end", start_frame)
        if end_frame < start_frame:
            end_frame = start_frame

        selected = collect_selected_track_names(context)
        if not selected:
            raise RuntimeError("Keine Tracks selektiert (Backwards Inline).")

        processing_names = list(selected)
        frames_processed = 0
        print("[Kaiserlich Tracker][InlineBackwards] ▶ Starte Rückwärts-Tracking-Zyklus…")

        for current_frame in range(end_frame, start_frame - 1, -1):
            # Move playhead to current frame
            space.clip_user.frame_current = current_frame
            scene.frame_current = current_frame
            # Apply formula on selected tracks (e.g. smoothing)
            try:
                apply_formula_on_selected_tracks(context, max_frames=5)
            except Exception as e:
                print(f"[Kaiserlich Tracker][InlineBackwards] ⚠️ Formel-Fehler: {e}")
            # Perform tracking step
            success = track_markers_with_override(
                window, area, region, space,
                backwards=True, sequence=False
            )
            if not success:
                print("[Kaiserlich Tracker][InlineBackwards] ⚠️ Tracking-Fehler, Abbruch.")
                break
            frames_processed += 1
            # Filter inactive tracks at this frame
            processing_names, _ = filter_active_tracks_at_frame(context, processing_names, current_frame)
            # Termination conditions
            if current_frame <= start_frame:
                print("[Kaiserlich Tracker][InlineBackwards] ✅ Szenenstart erreicht.")
                break
            if not processing_names:
                print("[Kaiserlich Tracker][InlineBackwards] ✅ Keine aktiven Tracks mehr.")
                break

        # Reset to start frame
        try:
            reset_to_frame(context, start_frame)
        except Exception as e:
            print(f"[Kaiserlich Tracker][InlineBackwards] ⚠️ Reset-Fehler: {e}")

        print("[Kaiserlich Tracker][InlineBackwards] ✅ Zyklus abgeschlossen.")
        total_len = float(get_total_track_length(context))
        return {"total_track_length": total_len, "frames_processed": frames_processed}

    def _run_forward_track_inline(self, context: bpy.types.Context) -> Dict[str, Any]:
        """
        Execute a full forward tracking cycle inline.  This is a counterpart
        to run_backward_track_inline, iterating from the scene's start frame
        to the end frame.  It performs framewise tracking on the selected
        tracks without invoking any modal operators.
        """
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if not clip:
            raise RuntimeError("Kein aktiver Clip (Forwards Inline).")

        window, area, region, space = find_clip_editor_area(clip)
        if not window:
            raise RuntimeError("Keine CLIP_EDITOR Area gefunden (Forwards Inline).")

        start_frame = ph_get_start_frame(context)
        end_frame = get_end_frame(context)
        if end_frame < start_frame:
            end_frame = start_frame

        selected = collect_selected_track_names(context)
        if not selected:
            raise RuntimeError("Keine Tracks selektiert (Forwards Inline).")

        processing_names = list(selected)
        frames_processed = 0
        print("[Kaiserlich Tracker][InlineForwards] ▶ Starte Vorwärts-Tracking-Zyklus…")

        for current_frame in range(start_frame, end_frame + 1):
            # Move playhead to current frame
            space.clip_user.frame_current = current_frame
            scene.frame_current = current_frame

            # Apply formula on selected tracks
            try:
                apply_formula_on_selected_tracks(context, max_frames=5)
            except Exception as e:
                print(f"[Kaiserlich Tracker][InlineForwards] ⚠️ Formel-Fehler: {e}")

            # Perform tracking step
            success = track_markers_with_override(
                window, area, region, space,
                backwards=False, sequence=False
            )
            if not success:
                print("[Kaiserlich Tracker][InlineForwards] ⚠️ Tracking-Fehler, Abbruch.")
                break
            frames_processed += 1
            # Filter inactive tracks at this frame
            processing_names, _ = filter_active_tracks_at_frame(context, processing_names, current_frame)
            # Termination conditions
            if current_frame >= end_frame:
                print("[Kaiserlich Tracker][InlineForwards] ✅ Szenenende erreicht.")
                break
            if not processing_names:
                print("[Kaiserlich Tracker][InlineForwards] ✅ Keine aktiven Tracks mehr.")
                break

        # Reset to the start frame
        try:
            reset_to_frame(context, start_frame)
        except Exception as e:
            print(f"[Kaiserlich Tracker][InlineForwards] ⚠️ Reset-Fehler: {e}")

        print("[Kaiserlich Tracker][InlineForwards] ✅ Zyklus abgeschlossen.")
        total_len = float(get_total_track_length(context))
        return {"total_track_length": total_len, "frames_processed": frames_processed}

    # ---------------------------------------------------------------------
    #  Execute method: orchestrates the full pipeline
    # ---------------------------------------------------------------------
    def execute(self, context: bpy.types.Context):
        scene = context.scene
        clip = _get_active_clip(context)

        # Save current selection
        saved_selection = _snapshot_selected_track_names(clip)
        iterations = 0

        # 1) One-time bootstrap (only if not already available)
        try:
            ef_target = int(scene.kaiserlich_markers_per_frame)
            if "bootstrap_params" not in scene:
                print(f"[Kaiserlich Tracker][Master] Bootstrap init (Ziel={ef_target}) …")
                params = run_bootstrap(context, ef_target)
                if not params:
                    self.report({'ERROR'}, "Bootstrap fehlgeschlagen.")
                    return {'CANCELLED'}
                scene["bootstrap_params"] = params
                print("[Kaiserlich Tracker][Master] Bootstrap abgeschlossen.")
            else:
                print("[Kaiserlich Tracker][Master] Bootstrap übersprungen (bereits vorhanden).")
        except Exception as e:
            self.report({'ERROR'}, f"Bootstrap-Fehler: {e}")
            return {'CANCELLED'}

        # 2) Main iteration loop
        while iterations < self.max_iterations:
            iterations += 1
            # 2.1 Determine the first weak frame (low-marker frame)
            try:
                res = find_first_weak_frame(context)
            except Exception as e:
                self.report({"ERROR"}, f"find_first_weak_frame() Fehler: {e}")
                break
            frame = _coerce_frame(res)
            if frame is None:
                break

            # Persist the frame to the scene key
            try:
                scene[self.store_scene_key] = int(frame)
            except Exception:
                pass

            # Optionally set the playhead to the weak frame
            if self.set_playhead:
                _set_frame_in_scene_and_clip(context, frame)

            # 2.2 Run auto-calibrate only if cached thresholds are not already present
            skip_auto = False
            try:
                skip_auto = should_use_cached_thresholds(context, frame)
            except Exception:
                skip_auto = False
            if not skip_auto:
                # Inline auto-calibrate (no operator invocation)
                self._auto_calibrate_inline(context)
                # Save thresholds for this frame (and optionally neighbor frames)
                try:
                    save_after_autocalibrate(context, frame, bake_neighbors=True)
                except Exception:
                    pass

            # 2.3 Detect adapt inline (no operator invocation)
            try:
                self._detect_adapt_inline(context)
            except Exception as e:
                self.report({'WARNING'}, f"DetectAdapt Fehler: {e}")

            # 2.4 Run backward tracking inline
            try:
                self._run_backward_track_inline(context)
            except Exception as e:
                self.report({'WARNING'}, f"BackwardTracking Fehler: {e}")

            # 2.5 Run forward tracking inline
            try:
                self._run_forward_track_inline(context)
            except Exception as e:
                self.report({'WARNING'}, f"ForwardTracking Fehler: {e}")

            # 2.6 Restore the original selection
            _restore_selected_tracks_by_names(clip, saved_selection)

            # 2.7 Filter problematic tracks after each iteration (silent)
            try:
                filter_problematic_tracks(context, threshold=10.0)
            except Exception:
                pass

        # Ensure selection is restored at the end
        _restore_selected_tracks_by_names(clip, saved_selection)

        # If we hit the iteration limit, signal an error condition
        if iterations >= self.max_iterations:
            self.report({"ERROR"}, f"Abbruch durch Safety-Stop nach {self.max_iterations} Iterationen.")

        return {"FINISHED"}

# Registration
classes = (
    KAISERLICHTRACKER_OT_master_operator,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
