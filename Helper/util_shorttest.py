import bpy
import math, time
from typing import Any, Dict, List, Optional, Set
from collections import deque

# ------------------------------------------------------------
# Helper-Importe
# ------------------------------------------------------------
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.track_length_helper import get_total_track_length
from ..Helper.delete import delete_tracks_by_names
from ..Helper.util_scene import call_get_start_frame, call_reset_to_frame, set_scene_props
from ..Helper.util_clip import get_current_track_names
from ..Helper.util_format import fmt8
from ..Helper.detect import detect_features
from ..Helper.newmarker import classify_markers
from ..Helper.cleaneup import cleanup_new_markers

# Zusätzliche Operator-Helper für Inline TrackCycle
from ..Helper.find_clip_editor_area import find_clip_editor_area
from ..Helper.collect_selected_tracks import collect_selected_track_names
from ..Helper.filter_active_tracks import filter_active_tracks_at_frame
from ..Helper.track_markers_helper import track_markers_with_override
from ..Helper.formula_helper import apply_formula_on_selected_tracks
from ..Helper.playhead_helper import reset_to_frame


# Scene Keys
SCENE_TOTAL_TRACK_LEN_BASE  = "kaiserlich_len_baseline_00"
SCENE_TOTAL_TRACK_LEN_STEP1 = "kaiserlich_len_rot_xy_00"
SCENE_TOTAL_TRACK_LEN_STEP2 = "kaiserlich_len_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP3 = "kaiserlich_len_rot_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP4 = "kaiserlich_len_perspective_0"


# ---------------------------------------------------------------------------
# SHORT TEST (DetectAdapt + TrackCycle inline)
# ---------------------------------------------------------------------------
def short_test_track(
    context=None,
    tracks_to_delete=None,
    run_meta: Optional[Dict[str, Any]] = None,
    report_fn: Optional[Any] = None
):
    """Führt einen einzelnen Short-Test aus (Detect, Track, Delete, Reset).
       Vollständig inline, ohne Operator-Aufrufe.
    """
    start_frame = None
    deleted_explicit: List[str] = []
    deleted_new: List[str] = []
    final_total_len: float = 0.0

    def _safe_get(scene, name):
        try:
            return float(getattr(scene, name))
        except Exception:
            return None

    scene = (context.scene if context else bpy.context.scene)
    if run_meta is None:
        run_meta = {}

    # Meta-Ausgabe
    fields: List[str] = run_meta.get("fields") or [
        "kaiserlich_rot_thresh_x",
        "kaiserlich_rot_thresh_y",
        "kaiserlich_scale_thresh_min",
        "kaiserlich_scale_thresh_max",
        "kaiserlich_rot_scale_thresh_rot",
        "kaiserlich_rot_scale_thresh_scale",
        "kaiserlich_perspective_thresh",
    ]
    tag: str = run_meta.get("tag") or "TEST"
    sf = run_meta.get("sf", None)

    kv = []
    for f in fields:
        v = _safe_get(scene, f)
        if v is not None:
            kv.append(f"{f}={fmt8(v)}")
    if sf is not None:
        kv.insert(0, f"sf={fmt8(sf)}")
    if report_fn and kv:
        report_fn(f"[{tag}] " + " | ".join(kv))

    pre_names: Set[str] = get_current_track_names(context)

    try:
        snapshot_active_markers(context)

        # ------------------------------------------------------------------
        # DetectAdapt Inline Flow
        # ------------------------------------------------------------------
        clip = getattr(context.space_data, "clip", None)
        if not clip:
            raise RuntimeError("Kein aktiver Clip gefunden (DetectAdapt-Flow).")

        hz, vc = clip.size
        tracking_settings = getattr(clip.tracking, "settings", None)
        ma = getattr(tracking_settings, "margin", 100)
        pz = getattr(tracking_settings, "pattern_size", 50)
        sz = getattr(tracking_settings, "search_size", 100)
        ef_target = int(scene.kaiserlich_markers_per_frame)

        md = hz * 0.025
        tr = 0.0001

        pre_snapshot = snapshot_active_markers(context)
        baseline_start_tracknames = {t.name for t in clip.tracking.tracks}

        max_loops = 8
        loop = 0
        last_md = md

        while loop < max_loops:
            loop += 1
            print(f"\n[Kaiserlich Tracker][ShortTest][DetectAdapt] LOOP {loop} | min_distance={last_md:.2f}")

            detect_features(
                context,
                placement='FRAME',
                margin=ma,
                threshold=tr,
                min_distance=int(max(1, round(last_md)))
            )

            # Alle Tracks deselektieren
            for trk in clip.tracking.tracks:
                trk.select = False

            post_snapshot = snapshot_active_markers(context)
            alte_marker, neue_marker = classify_markers(pre_snapshot, post_snapshot)
            cleaned_new, deleted_old = cleanup_new_markers(context, alte_marker, neue_marker, pz=pz, hz=hz, vc=vc)

            print(f"[Kaiserlich Tracker][ShortTest][DetectAdapt] Neue Marker: {len(cleaned_new)} | Alte gelöscht: {deleted_old}")

            remaining = len(cleaned_new)
            diff = remaining - ef_target
            tolerance = ef_target * 0.10
            if abs(diff) <= tolerance:
                print(f"[Kaiserlich Tracker][ShortTest][DetectAdapt] Ziel erreicht ({remaining}/{ef_target})")
                break

            # Anpassung von min_distance
            if len(cleaned_new) > 0:
                ratio = ef_target / len(cleaned_new)
                factor = max(0.5, min(2.0, ratio))
                last_md = max(1.0, last_md / factor)
            else:
                last_md *= 1.5
                print("[Kaiserlich Tracker][ShortTest][DetectAdapt] Keine neuen Marker → erhöhe min_distance.")

            if loop < max_loops:
                delete_tracks_by_names(context, [m['track'] for m in neue_marker])
                time.sleep(0.1)

        # Selektiere nur neu erzeugte Marker
        for trk in clip.tracking.tracks:
            trk.select = (trk.name not in baseline_start_tracknames)

        print(f"[Kaiserlich Tracker][ShortTest][DetectAdapt] Final selektierte Marker: "
              f"{len([t for t in clip.tracking.tracks if t.select])}")

        # ------------------------------------------------------------------
        # Inline TrackCycle Flow (ersetzt Operator-Aufruf)
        # ------------------------------------------------------------------
        clip = getattr(context.space_data, "clip", None)
        if not clip:
            raise RuntimeError("Kein aktiver Clip (TrackCycle Inline).")

        window, area, region, space = find_clip_editor_area(clip)
        if not window:
            raise RuntimeError("Keine CLIP_EDITOR Area gefunden (TrackCycle Inline).")

        tracking = clip.tracking
        start_frame = call_get_start_frame(context)
        end_frame = getattr(scene, "frame_end", start_frame)
        if end_frame < start_frame:
            end_frame = start_frame

        original_selected = collect_selected_tracks(context)
        if not original_selected:
            raise RuntimeError("Keine Tracks selektiert (TrackCycle Inline).")

        processing_names = list(original_selected)
        frames_processed = 0
        max_frames = getattr(scene, "kaiserlich_max_frames", 0) or 0

        print("[Kaiserlich Tracker][InlineTrack] ▶ Starte Tracking-Zyklus...")

        for current_frame in range(start_frame, end_frame + 1):
            # Frame setzen
            space.clip_user.frame_current = current_frame
            scene.frame_current = current_frame

            # Formelberechnung (optional)
            try:
                apply_formula_on_selected_tracks(context, max_frames=5)
            except Exception as e:
                print(f"[Kaiserlich Tracker][InlineTrack] ⚠️ Formel-Fehler: {e}")

            # Tracking-Schritt
            success = track_markers_with_override(
                window, area, region, space,
                backwards=False, sequence=False
            )
            if not success:
                print("[Kaiserlich Tracker][InlineTrack] ⚠️ Tracking-Fehler – Abbruch.")
                break

            frames_processed += 1

            # Aktive Tracks prüfen
            processing_names, _ = filter_active_tracks_at_frame(
                context, processing_names, current_frame
            )

            if not processing_names:
                print("[Kaiserlich Tracker][InlineTrack] ✅ Keine aktiven Tracks mehr.")
                break

            if max_frames > 0 and frames_processed >= max_frames:
                print("[Kaiserlich Tracker][InlineTrack] ⚠️ Sicherheitslimit erreicht.")
                break

        # Abschluss
        try:
            reset_to_frame(context, start_frame)
        except Exception as e:
            print(f"[Kaiserlich Tracker][InlineTrack] ⚠️ Reset-Fehler: {e}")

        print("[Kaiserlich Tracker][InlineTrack] ✅ Tracking-Zyklus abgeschlossen.")

        # Manuelles Löschen falls angegeben
        if tracks_to_delete:
            names = [n.strip() for n in tracks_to_delete if n and n.strip()]
            if names:
                delete_tracks_by_names(context, names)
                deleted_explicit = names

    finally:
        # Abschluss-Cleanup
        if start_frame is not None:
            call_reset_to_frame(start_frame, context)

        try:
            final_total_len = float(get_total_track_length(context))
        except Exception:
            final_total_len = 0.0

        try:
            post_names: Set[str] = get_current_track_names(context)
            new_names = sorted(list(post_names - pre_names))
            if new_names:
                delete_tracks_by_names(context, new_names)
                deleted_new = new_names
        except Exception:
            pass

    return {
        "total_track_length": final_total_len,
        "deleted_explicit": deleted_explicit,
        "deleted_new": deleted_new,
        "start_frame": start_frame,
    }