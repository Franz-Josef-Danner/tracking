# Operator/auto_calibrate_operator.py

import bpy
from typing import Iterable, List, Set, Optional

from ..Helper.snapshot import snapshot_active_markers
from ..Helper.track_length_helper import get_total_track_length
from ..Helper.delete import delete_tracks_by_names
from ..Helper.playhead_helper import get_start_frame, reset_to_frame

SCENE_TOTAL_TRACK_LEN_BASE  = "kaiserlich_len_baseline_00"
SCENE_TOTAL_TRACK_LEN_STEP1 = "kaiserlich_len_rot_xy_00"
SCENE_TOTAL_TRACK_LEN_STEP2 = "kaiserlich_len_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP3 = "kaiserlich_len_rot_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP4 = "kaiserlich_len_perspective_0"

# ---- Utility ---------------------------------------------------------------

def set_all_thresholds_to_one(context: bpy.types.Context) -> None:
    scene = context.scene
    props: Iterable[str] = (
        "kaiserlich_rot_thresh_x",
        "kaiserlich_rot_thresh_y",
        "kaiserlich_scale_thresh_min",
        "kaiserlich_scale_thresh_max",
        "kaiserlich_rot_scale_thresh_rot",
        "kaiserlich_rot_scale_thresh_scale",
        "kaiserlich_perspective_thresh",
    )
    for p in props:
        if hasattr(scene, p):
            try:
                setattr(scene, p, 1.0)
            except Exception:
                pass  # fail-soft


def _call_get_start_frame(context=None):
    try:
        return get_start_frame(context) if context is not None else get_start_frame()
    except TypeError:
        return get_start_frame()


def _call_reset_to_frame(frame, context=None):
    try:
        return reset_to_frame(context, frame) if context is not None else reset_to_frame(frame)
    except TypeError:
        return reset_to_frame(frame)


def _get_active_clip(context: Optional[bpy.types.Context]) -> Optional[bpy.types.MovieClip]:
    try:
        if context and getattr(context, "space_data", None):
            clip = getattr(context.space_data, "clip", None)
            if clip:
                return clip
    except Exception:
        pass
    try:
        return bpy.data.movieclips[0] if bpy.data.movieclips else None
    except Exception:
        return None


def _list_track_names_from_clip(clip: Optional[bpy.types.MovieClip]):
    if not clip:
        return []
    try:
        return [t.name for t in clip.tracking.tracks]
    except Exception:
        return []


def _get_current_track_names(context: Optional[bpy.types.Context]) -> Set[str]:
    clip = _get_active_clip(context)
    return set(_list_track_names_from_clip(clip))


def short_test_track(context=None, tracks_to_delete=None):
    """
    Reihenfolge:
      1) snapshot_active_markers
      2) bpy.ops.kaiserlich_tracker.detect_adapt
      2.5) get_start_frame
      3) bpy.ops.kaiserlich_tracker.track_cycle
      4) delete_tracks_by_names (explizit/optional)
      5) reset_to_frame(start)
      6) delete newly created tracks (Delta)
      7) FINAL: get_total_track_length (nur zurückgeben, keine globale Szene-Length mehr)
    Returns:
      dict: {"total_track_length": float, "deleted_explicit": [str], "deleted_new": [str], "start_frame": int|None}
    """
    start_frame = None
    deleted_explicit: List[str] = []
    deleted_new: List[str] = []
    final_total_len: float = 0.0

    # Vorher-Stand der Tracks für Delta-Ermittlung
    pre_names: Set[str] = _get_current_track_names(context)

    try:
        # 1) Snapshot
        try:
            (snapshot_active_markers(context) if context is not None else snapshot_active_markers())
        except TypeError:
            snapshot_active_markers()

        # 2) Detect-Adapt
        result = bpy.ops.kaiserlich_tracker.detect_adapt('EXEC_DEFAULT')
        if 'CANCELLED' in result:
            raise RuntimeError("Detect-Adapt wurde abgebrochen.")

        # 2.5) Start-Frame
        start_frame = _call_get_start_frame(context)

        # 3) Track Cycle
        result = bpy.ops.kaiserlich_tracker.track_cycle('EXEC_DEFAULT')
        if 'CANCELLED' in result:
            raise RuntimeError("Tracking Cycle wurde abgebrochen.")

        # 4) Optional: explizit angegebene Tracks löschen
        if tracks_to_delete:
            names = [n.strip() for n in tracks_to_delete if n and n.strip()]
            if names:
                try:
                    (delete_tracks_by_names(context, names) if context is not None else delete_tracks_by_names(names))
                except TypeError:
                    delete_tracks_by_names(names)
                deleted_explicit = names

    finally:
        # 5) Playhead zurücksetzen (best effort)
        if start_frame is not None:
            try:
                _call_reset_to_frame(start_frame, context)
            except Exception:
                pass

        # 6) FINAL: Gesamtlänge (VOR Delta-Cleanup) bestimmen
        try:
            if context is not None:
                try:
                    final_total_len = float(get_total_track_length(context))
                except TypeError:
                    final_total_len = float(get_total_track_length())
            else:
                final_total_len = float(get_total_track_length())
        except Exception:
            final_total_len = 0.0  # fail-soft

        # 7) NEU: neu erzeugte Tracks löschen (Delta) – Szene aufräumen
        try:
            post_names: Set[str] = _get_current_track_names(context)
            new_names = sorted(list(post_names - pre_names))
            if new_names:
                try:
                    (delete_tracks_by_names(context, new_names) if context is not None
                     else delete_tracks_by_names(new_names))
                except TypeError:
                    delete_tracks_by_names(new_names)
                deleted_new = new_names
        except Exception:
            pass

    return {
        "total_track_length": final_total_len,   # Wert VOR Cleanup
        "deleted_explicit": deleted_explicit,
        "deleted_new": deleted_new,
        "start_frame": start_frame,
    }


def _set_scene_props(scene: bpy.types.Scene, **kwargs) -> None:
    """Best-effort Setter für Scene-Properties (float-cast, fail-soft)."""
    for k, v in kwargs.items():
        try:
            if hasattr(scene, k):
                setattr(scene, k, float(v))
        except Exception:
            pass  # fail-soft


def short_test_pipeline(context=None):
    """
    Fährt 5 Tests in einem Run. Test 1 ist die Baseline.
    Persistiert nur die Step-Werte in Scene (optional auch BASE).

    Steps:
      BASE) alle relevanten Thresholds = 1.0                              -> short_test_track -> (optional) Scene[SCENE_TOTAL_TRACK_LEN_BASE]
      1)    rot_thresh_x=0, rot_thresh_y=0                                -> Scene[SCENE_TOTAL_TRACK_LEN_STEP1]
      2)    rot_thresh_x=1, rot_thresh_y=1, scale_min=0, scale_max=0      -> Scene[SCENE_TOTAL_TRACK_LEN_STEP2]
      3)    scale_min=1, scale_max=1, rot_scale_rot=0, rot_scale_scale=0  -> Scene[SCENE_TOTAL_TRACK_LEN_STEP3]
      4)    rot_scale_rot=1, rot_scale_scale=1, perspective_thresh=0      -> Scene[SCENE_TOTAL_TRACK_LEN_STEP4]

    Returns:
      dict: {"baseline": int, "step1": int, "step2": int, "step3": int, "step4": int}
    """
    scene = (context.scene if context is not None else bpy.context.scene)

    results = {"baseline": 0, "step1": 0, "step2": 0, "step3": 0, "step4": 0}

    # --- BASELINE (alle = 1.0) ---
    try:
        _set_scene_props(scene,
            kaiserlich_rot_thresh_x=1.0,
            kaiserlich_rot_thresh_y=1.0,
            kaiserlich_scale_thresh_min=1.0,
            kaiserlich_scale_thresh_max=1.0,
            kaiserlich_rot_scale_thresh_rot=1.0,
            kaiserlich_rot_scale_thresh_scale=1.0,
            kaiserlich_perspective_thresh=1.0,
        )
        rb = short_test_track(context=context)
        results["baseline"] = int(float(rb.get("total_track_length", 0.0)))
        # optional: historisch persistieren
        try:
            scene[SCENE_TOTAL_TRACK_LEN_BASE] = results["baseline"]
        except Exception:
            pass
    except Exception:
        pass

    # --- STEP 1 ---
    try:
        _set_scene_props(scene,
            kaiserlich_rot_thresh_x=0.0,
            kaiserlich_rot_thresh_y=0.0,
        )
        r1 = short_test_track(context=context)
        results["step1"] = int(float(r1.get("total_track_length", 0.0)))
        try:
            scene[SCENE_TOTAL_TRACK_LEN_STEP1] = results["step1"]
        except Exception:
            pass
    except Exception:
        pass

    # --- STEP 2 ---
    try:
        _set_scene_props(
            scene,
            kaiserlich_rot_thresh_x=1.0,
            kaiserlich_rot_thresh_y=1.0,
            kaiserlich_scale_thresh_min=0.0,
            kaiserlich_scale_thresh_max=0.0,
        )
        r2 = short_test_track(context=context)
        results["step2"] = int(float(r2.get("total_track_length", 0.0)))
        try:
            scene[SCENE_TOTAL_TRACK_LEN_STEP2] = results["step2"]
        except Exception:
            pass
    except Exception:
        pass

    # --- STEP 3 ---
    try:
        _set_scene_props(
            scene,
            kaiserlich_scale_thresh_min=1.0,
            kaiserlich_scale_thresh_max=1.0,
            kaiserlich_rot_scale_thresh_rot=0.0,
            kaiserlich_rot_scale_thresh_scale=0.0,
        )
        r3 = short_test_track(context=context)
        results["step3"] = int(float(r3.get("total_track_length", 0.0)))
        try:
            scene[SCENE_TOTAL_TRACK_LEN_STEP3] = results["step3"]
        except Exception:
            pass
    except Exception:
        pass

    # --- STEP 4 ---
    try:
        _set_scene_props(
            scene,
            kaiserlich_rot_scale_thresh_rot=1.0,
            kaiserlich_rot_scale_thresh_scale=1.0,
            kaiserlich_perspective_thresh=0.0,
        )
        r4 = short_test_track(context=context)
        results["step4"] = int(float(r4.get("total_track_length", 0.0)))
        try:
            scene[SCENE_TOTAL_TRACK_LEN_STEP4] = results["step4"]
        except Exception:
            pass
    except Exception:
        pass
    try:
        _set_scene_props(scene, kaiserlich_perspective_thresh=1.0)
    except Exception:
        pass

    return results

# ---- Comparison Utility -----------------------------------------------------

def _get_scene_int(scene: bpy.types.Scene, key: str) -> Optional[int]:
    """Liest scene[key] oder scene.key und castet robust nach int. None falls nicht vorhanden."""
    try:
        if key in scene.keys():
            val = scene[key]
        elif hasattr(scene, key):
            val = getattr(scene, key)
        else:
            return None
        return int(float(val))
    except Exception:
        return None

def compare_len_steps_to_total(context=None):
    """
    Vergleicht STEP1..STEP4 (int) gegen die BASELINE (int, aus Scene[SCENE_TOTAL_TRACK_LEN_BASE]).
    Rückgabe liefert Werte und Relationen ('better'|'equal'|'worse'|'missing').

    Returns:
      dict: {
        'baseline': Optional[int],
        'values': {'STEP1': Optional[int], ...},
        'relations': {'STEP1': 'better|equal|worse|missing', ...},
        'better_or_equal': [steps...],   # nur die, die >= baseline sind
        'all_present': bool              # True, wenn baseline und alle steps vorhanden
      }
    """
    scene = (context.scene if context is not None else bpy.context.scene)

    base = _get_scene_int(scene, SCENE_TOTAL_TRACK_LEN_BASE)
    v1 = _get_scene_int(scene, SCENE_TOTAL_TRACK_LEN_STEP1)
    v2 = _get_scene_int(scene, SCENE_TOTAL_TRACK_LEN_STEP2)
    v3 = _get_scene_int(scene, SCENE_TOTAL_TRACK_LEN_STEP3)
    v4 = _get_scene_int(scene, SCENE_TOTAL_TRACK_LEN_STEP4)

    values = {"STEP1": v1, "STEP2": v2, "STEP3": v3, "STEP4": v4}
    relations = {}

    def _rel(v, b):
        if v is None or b is None:
            return "missing"
        if v > b:
            return "better"
        if v == b:
            return "equal"
        return "worse"

    for k, v in values.items():
        relations[k] = _rel(v, base)

    better_or_equal = [k for k, r in relations.items() if r in ("better", "equal")]
    all_present = (base is not None) and all(v is not None for v in values.values())

    return {
        "baseline": base,
        "values": values,
        "relations": relations,
        "better_or_equal": better_or_equal,
        "all_present": all_present,
    }

# ---- Operator --------------------------------------------------------------

class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Auto-calibrate: setzt alle Ziel-Parameter auf 1.0 und führt danach Detect-Adapt & Tracking aus."""
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "KAISERLICHTRACKER — Auto Calibrate"
    bl_options = {"REGISTER", "UNDO"}

    tracks_to_delete: bpy.props.StringProperty(
        name="Tracks to delete (comma-separated)",
        default="",
        description="Optional: Namen der zu löschenden Tracks, getrennt durch Kommas"
    )

    def execute(self, context):
        try:
            # UI-Feedback
            set_all_thresholds_to_one(context)
            self.report({'INFO'}, "KaiserlichTracker: Thresholds => 1.0")

            names = [n.strip() for n in self.tracks_to_delete.split(",") if n.strip()]
            result = short_test_track(context=context, tracks_to_delete=names)

            final_len = result.get('total_track_length', 0.0)
            self.report({'INFO'}, f"Auto-Calibrate finalisiert. Track-Länge gesamt: {final_len}")
            if result.get("deleted_explicit"):
                self.report({'INFO'}, f"Explizit gelöschte Tracks: {', '.join(result['deleted_explicit'])}")
            if result.get("deleted_new"):
                self.report({'INFO'}, f"Neu erzeugte Tracks entfernt: {', '.join(result['deleted_new'])}")
            if result.get("start_frame") is not None:
                self.report({'INFO'}, f"Playhead zurückgesetzt auf Frame {result['start_frame']}")

            # ---- Ergänzend: Short Test Pipeline fahren und Ergebnisse persistieren ----
            try:
                pipeline_results = short_test_pipeline(context=context)
                bl = pipeline_results.get('baseline', 0)
                s1 = pipeline_results.get('step1', 0)
                s2 = pipeline_results.get('step2', 0)
                s3 = pipeline_results.get('step3', 0)
                s4 = pipeline_results.get('step4', 0)
                self.report(
                    {'INFO'},
                    (f"Short-Test-Pipeline abgeschlossen | "
                     f"Baseline={bl} | Step1={s1} Step2={s2} Step3={s3} Step4={s4}")
                )
            except Exception as e:
                self.report({'ERROR'}, f"Short-Test-Pipeline fehlgeschlagen: {e}")

            # --- NEU: Ergänzend Vergleich STEP1..STEP4 vs. Baseline triggern ---
            try:
                cmp_res = compare_len_steps_to_total(context)
                base = cmp_res.get("baseline")
                vals = cmp_res.get("values", {})
                rels = cmp_res.get("relations", {})
                ge_list = cmp_res.get("better_or_equal", [])
                self.report(
                    {'INFO'},
                    (f"Baseline={base} | "
                     f"STEP1={vals.get('STEP1')}({rels.get('STEP1')}) "
                     f"STEP2={vals.get('STEP2')}({rels.get('STEP2')}) "
                     f"STEP3={vals.get('STEP3')}({rels.get('STEP3')}) "
                     f"STEP4={vals.get('STEP4')}({rels.get('STEP4')})")
                )
                self.report({'INFO'}, "≥ Baseline: " + (", ".join(ge_list) if ge_list else "none"))
            except Exception as e:
                self.report({'ERROR'}, f"Vergleich (STEPs vs. Baseline) fehlgeschlagen: {e}")

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Auto-Calibrate fehlgeschlagen: {e}")
            return {'CANCELLED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)
