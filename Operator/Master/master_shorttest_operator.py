# Operator/Master/master_shorttest_operator.py
import bpy
import time
import math
from typing import Optional, List, Dict, Any, Tuple, Set, Deque
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
from ..Helper.filter_and_delete_tracks import filter_and_delete_tracks


# ----------------------------------------------------------------------------
# Scene Keys
# ----------------------------------------------------------------------------
SCENE_TOTAL_TRACK_LEN_BASE = "kaiserlich_len_baseline_00"
SCENE_TOTAL_TRACK_LEN_STEP1 = "kaiserlich_len_rot_xy_00"
SCENE_TOTAL_TRACK_LEN_STEP2 = "kaiserlich_len_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP3 = "kaiserlich_len_rot_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP4 = "kaiserlich_len_perspective_0"


# ----------------------------------------------------------------------------
# State Class
# ----------------------------------------------------------------------------
@dataclass
class _AutoCalibState:
    initialized: bool = False
    done: bool = False
    step: int = 0
    notes: Deque[str] = field(default_factory=lambda: deque(maxlen=200))

    did_reset_thresholds: bool = False
    did_detect_adapt: bool = False
    detect_adapt_done_confirmed: bool = False
    did_track_cycle: bool = False

    track_active: bool = False
    track_window: Optional[bpy.types.Window] = None
    track_area: Optional[bpy.types.Area] = None
    track_region: Optional[bpy.types.Region] = None
    track_space: Optional[bpy.types.Space] = None
    track_names: List[str] = field(default_factory=list)
    track_original_selected: List[str] = field(default_factory=list)
    track_frame_current: int = 0
    track_frame_end: int = 0
    track_start_frame: int = 0

    baseline_track_names: List[str] = field(default_factory=list)
    created_track_names: List[str] = field(default_factory=list)

    track_cycles_done: int = 0
    second_cycle: bool = False
    third_cycle: bool = False
    fourth_cycle: bool = False
    fifth_cycle: bool = False
    cycle_thresholds: Dict[int, Dict[str, float]] = field(default_factory=dict)


# ----------------------------------------------------------------------------
# Operator
# ----------------------------------------------------------------------------
class KAISERLICHTRACKER_OT_master_shorttest_operator(bpy.types.Operator):
    bl_idname = "kaiserlich_tracker.master_shorttest_operator"
    bl_label = "Kaiserlich Tracker — Auto Calibrate"
    bl_options = {'REGISTER', 'UNDO'}

    _timer: Optional[Any] = None
    _state: _AutoCalibState

    # ------------------------------------------------------------------------
    # Invoke
    # ------------------------------------------------------------------------
    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        self._state = _AutoCalibState()
        # NEU: ursprüngliche Playhead-Position des Users sichern (global für gesamten ShortTest)
        try:
            self._state.user_original_frame = int(context.scene.frame_current)
        except Exception:
            self._state.user_original_frame = None
            
        clip = get_active_clip(context)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver MovieClip gefunden.")
            return {'CANCELLED'}

        # Deselect all at start
        try:
            deselected = self._deselect_all_tracks(context)
            print(f"[Kaiserlich Tracker][Selection] {deselected} Tracks deselektiert (Start).")
        except Exception as ex:
            print(f"[Kaiserlich Tracker][Selection] ⚠️ Deselektion fehlgeschlagen: {ex!r}")

        self._state.notes.append("Init OK (modal).")
        return {'RUNNING_MODAL'}

    # ------------------------------------------------------------------------
    # Modal Loop
    # ------------------------------------------------------------------------
    def modal(self, context: bpy.types.Context, event: bpy.types.Event):
        if event.type == 'ESC':
            return self._teardown(context, cancelled=True)
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        # 0) Init
        if not self._state.initialized:
            self._state.initialized = True
            print("[Kaiserlich Tracker][AutoCalibrate] Initialized.")
            return {'RUNNING_MODAL'}

        # 1) Reset Thresholds
        if not self._state.did_reset_thresholds:
            try:
                reset_all_thresholds(context, active_props=[])
                self._state.did_reset_thresholds = True
                print("[Kaiserlich Tracker][AutoCalibrate] Thresholds reset → 1.0")
            except Exception as ex:
                print(f"[AutoCalibrate] Threshold reset failed: {ex!r}")
                self._state.did_reset_thresholds = True
            return {'RUNNING_MODAL'}

        # 2) Detect-Adapt
        if not self._state.did_detect_adapt:
            print("[Kaiserlich Tracker][AutoCalibrate] Detect-Adapt gestartet.")
            try:
                self._detect_adapt_inline(context)
            except Exception as ex:
                print(f"[AutoCalibrate] Detect-Adapt Fehler: {ex!r}")
                self._state.detect_adapt_done_confirmed = True
            self._state.did_detect_adapt = True
            return {'RUNNING_MODAL'}

        # 3) Wait for confirmation
        if self._state.did_detect_adapt and not self._state.detect_adapt_done_confirmed:
            return {'RUNNING_MODAL'}

        # 4) Track Cycle
        if self._state.detect_adapt_done_confirmed:
            if not self._state.track_active and not self._state.did_track_cycle:
                try:
                    self._track_cycle_start(context)
                    print("[Kaiserlich Tracker][AutoCalibrate] Track-Cycle initialisiert.")
                except Exception as ex:
                    print(f"[AutoCalibrate] Track-Cycle Init Fehler: {ex!r}")
                    self._state.did_track_cycle = True
                    return {'RUNNING_MODAL'}
                return {'RUNNING_MODAL'}

            if self._state.track_active:
                still_running = self._track_cycle_tick(context)
                if not still_running:
                    self._track_cycle_finish(context)
                    self._state.track_active = False
                    self._state.track_cycles_done += 1
                    self._state.did_track_cycle = True
                    print("[Kaiserlich Tracker][AutoCalibrate] Track-Cycle abgeschlossen.")
                    return {'RUNNING_MODAL'}
                return {'RUNNING_MODAL'}

        # 5) Abschluss oder Vorbereitung auf weitere Zyklen
        if not self._state.done and self._state.did_track_cycle:
            # Wenn noch kein zweiter Durchlauf durchgeführt wurde, starte diesen:
            if not self._state.second_cycle:
                try:
                    # Setze Rot-Schwellenwerte (X/Y) auf 0,0
                    print("[Kaiserlich Tracker][AutoCalibrate] Rot-Schwellwerte auf 0 gesetzt.")
                    set_scene_props(context.scene,
                                    kaiserlich_rot_thresh_x=0.00001,
                                    kaiserlich_rot_thresh_y=0.00001)
                except Exception as ex:
                    print(f"[AutoCalibrate] Fehler beim Setzen der Rot-Schwellenwerte: {ex!r}")
                # Flags setzen, um zweiten Detect-/Track‑Durchlauf zu initiieren
                self._state.second_cycle = True
                # Merke die in diesem Durchlauf verwendeten Schwellenwerte
                self._state.cycle_thresholds[2] = {
                    'kaiserlich_rot_thresh_x': 0.00001,
                    'kaiserlich_rot_thresh_y': 0.00001,
                }
                # Detect-Adapt und Track-Cycle erneut ausführen
                self._state.did_detect_adapt = False
                self._state.detect_adapt_done_confirmed = False
                self._state.did_track_cycle = False
                return {'RUNNING_MODAL'}

            # Wenn der zweite Durchlauf bereits erledigt ist, aber noch kein dritter:
            if self._state.second_cycle and not self._state.third_cycle:
                try:
                    # Setze alle Thresholds auf 1.0 zurück und Scale-Min/Max auf 0.00001
                    print("[Kaiserlich Tracker][AutoCalibrate] Thresholds auf 1.0 gesetzt, Scale-Min/Max auf 0.00001.")
                    reset_all_thresholds(context, active_props=[])
                    set_scene_props(context.scene,
                                    kaiserlich_scale_thresh_min=0.00001,
                                    kaiserlich_scale_thresh_max=0.00001)
                except Exception as ex:
                    print(f"[AutoCalibrate] Fehler beim Zurücksetzen der Thresholds: {ex!r}")
                # Flags setzen, um dritten Detect-/Track‑Durchlauf zu initiieren
                self._state.third_cycle = True
                # Merke die in diesem Durchlauf verwendeten Schwellenwerte
                self._state.cycle_thresholds[3] = {
                    'kaiserlich_scale_thresh_min': 0.00001,
                    'kaiserlich_scale_thresh_max': 0.00001,
                }
                self._state.did_detect_adapt = False
                self._state.detect_adapt_done_confirmed = False
                self._state.did_track_cycle = False
                return {'RUNNING_MODAL'}

            # Wenn der dritte Durchlauf bereits erledigt ist, aber noch kein vierter:
            if self._state.third_cycle and not getattr(self._state, 'fourth_cycle', False):
                try:
                    # Setze alle Thresholds auf 1.0 zurück und Rot-Scale-Paar auf 0.00001
                    print("[Kaiserlich Tracker][AutoCalibrate] Thresholds auf 1.0 gesetzt, Rot-Scale (rot/scale) auf 0.00001.")
                    reset_all_thresholds(context, active_props=[])
                    set_scene_props(context.scene,
                                    kaiserlich_rot_scale_thresh_rot=0.00001,
                                    kaiserlich_rot_scale_thresh_scale=0.00001)
                except Exception as ex:
                    print(f"[AutoCalibrate] Fehler beim Zurücksetzen der Thresholds für 4. Durchlauf: {ex!r}")
                # Flag setzen und Schwellenwerte merken
                self._state.fourth_cycle = True
                self._state.cycle_thresholds[4] = {
                    'kaiserlich_rot_scale_thresh_rot': 0.00001,
                    'kaiserlich_rot_scale_thresh_scale': 0.00001,
                }
                # Detect-Adapt und Track-Cycle erneut ausführen
                self._state.did_detect_adapt = False
                self._state.detect_adapt_done_confirmed = False
                self._state.did_track_cycle = False
                return {'RUNNING_MODAL'}

            # Wenn der vierte Durchlauf bereits erledigt ist, aber noch kein fünfter:
            if getattr(self._state, 'fourth_cycle', False) and not getattr(self._state, 'fifth_cycle', False):
                try:
                    # Setze alle Thresholds auf 1.0 zurück und Perspective-Thresh auf 0.00001
                    print("[Kaiserlich Tracker][AutoCalibrate] Thresholds auf 1.0 gesetzt, Perspective-Thresh auf 0.00001.")
                    reset_all_thresholds(context, active_props=[])
                    set_scene_props(context.scene,
                                    kaiserlich_perspective_thresh=0.00001)
                except Exception as ex:
                    print(f"[AutoCalibrate] Fehler beim Zurücksetzen der Thresholds für 5. Durchlauf: {ex!r}")
                # Flag setzen und Schwellenwerte merken
                self._state.fifth_cycle = True
                self._state.cycle_thresholds[5] = {
                    'kaiserlich_perspective_thresh': 0.00001,
                }
                # Detect-Adapt und Track-Cycle erneut ausführen
                self._state.did_detect_adapt = False
                self._state.detect_adapt_done_confirmed = False
                self._state.did_track_cycle = False
                return {'RUNNING_MODAL'}

            # Wenn alle zusätzlichen Durchläufe abgeschlossen wurden → Vergleich und Finale
            if self._state.second_cycle and self._state.third_cycle and getattr(self._state, 'fourth_cycle', False) and getattr(self._state, 'fifth_cycle', False):
                try:
                    scene = context.scene
                    # Baseline-Länge aus Szene lesen
                    baseline_len = int(scene.get(SCENE_TOTAL_TRACK_LEN_BASE, 0))

                    # Mapping Cycle → Zielvariable
                    step_map = {
                        2: SCENE_TOTAL_TRACK_LEN_STEP1,  # Rot XY
                        3: SCENE_TOTAL_TRACK_LEN_STEP2,  # Scale
                        4: SCENE_TOTAL_TRACK_LEN_STEP3,  # Rot-Scale
                        5: SCENE_TOTAL_TRACK_LEN_STEP4,  # Perspective
                    }

                    # Vorab bereinigen: alte Werte löschen/leer lassen
                    for key in step_map.values():
                        if key in scene:
                            del scene[key]

                    best_thresholds: Dict[str, float] = {}

                    # Über alle gespeicherten Zyklen (2–5) iterieren und gegen Baseline evaluieren
                    for cycle_num, thresh_dict in self._state.cycle_thresholds.items():
                        step_key = step_map.get(cycle_num)
                        if not step_key:
                            continue
                        length_key = f"kaiserlich_len_cycle_{cycle_num}"
                        cycle_len = int(scene.get(length_key, 0))

                        if cycle_len > baseline_len:
                            # Besser als Baseline → in Zielvariable persistieren
                            scene[step_key] = cycle_len
                            best_thresholds.update(thresh_dict)
                            print(f"[Kaiserlich Tracker][AutoCalibrate] 🔹 Verbesserter Wert in Cycle {cycle_num}: {cycle_len} > {baseline_len} → gespeichert unter '{step_key}'")
                        else:
                            # Kein Zugewinn → Zielvariable bleibt leer
                            print(f"[Kaiserlich Tracker][AutoCalibrate] Kein Zugewinn in Cycle {cycle_num}: {cycle_len} ≤ {baseline_len}")

                    # Beste Thresholds (Aggregat der Gewinner) in Szene persistieren
                    scene["kaiserlich_best_thresholds"] = best_thresholds
                    print(f"[Kaiserlich Tracker][AutoCalibrate] Beste Thresholds: {best_thresholds}")

                except Exception as ex:
                    print(f"[AutoCalibrate] Fehler beim Vergleich der Track-Längen: {ex!r}")

                # Final: Alle Thresholds auf 1.0 zurücksetzen
                try:
                    reset_all_thresholds(context, active_props=[])
                except Exception as ex:
                    print(f"[AutoCalibrate] Fehler beim finalen Reset: {ex!r}")

                self._state.done = True
                return self._teardown(context, cancelled=False)

            # Wenn keine der obigen Bedingungen zutrifft → finale Routine (Fallback)
            self._state.done = True
            return self._teardown(context, cancelled=False)

        return {'RUNNING_MODAL'}
    
    # ------------------------------------------------------------------------
    # Helper: Alle Tracks im aktiven Clip deselektieren
    # ------------------------------------------------------------------------
    def _deselect_all_tracks(self, context: bpy.types.Context) -> int:
        """Setzt track.select = False für alle Tracks im aktiven Clip.
        Returns: Anzahl zuvor selektierter Tracks, die deselektiert wurden.
        """
        clip = getattr(context.space_data, "clip", None)
        tracking = getattr(clip, "tracking", None) if clip else None
        if not tracking or not getattr(tracking, "tracks", None):
            return 0
        changed = 0
        for tr in tracking.tracks:
            if getattr(tr, "select", False):
                tr.select = False
                changed += 1
        return changed
        
    def _detect_adapt_inline(self, context: bpy.types.Context):
        scene = context.scene
        ef_target = int(scene.kaiserlich_markers_per_frame)

        params = scene.get("bootstrap_params", None)
        # --- NEU: Sicherstellen, dass mindestens 50 Frames bis Szenenende verbleiben ---
        current_frame = int(scene.frame_current)
        end_frame = int(get_end_frame(context))
        remaining = end_frame - current_frame

        # Ursprungsposition merken
        self._state.original_frame_position = current_frame

        if remaining < 50:
            # Berechne neuen Startframe so, dass 50 Frames übrig bleiben
            new_start = max(scene.frame_start, end_frame - 50)
            scene.frame_current = new_start

            # Clip-Editor (Space) synchronisieren, falls vorhanden
            try:
                space = getattr(context, "space_data", None)
                if space and getattr(space, "clip_user", None):
                    space.clip_user.frame_current = new_start
            except Exception:
                pass

            print(f"[ShortTest] ⏪ Nur {remaining} Frames bis Szenenende – "
                  f"Playhead verschoben: {current_frame} → {new_start}")
        else:
            print(f"[ShortTest] ✅ Ausreichend Frames ({remaining}) – keine Verschiebung erforderlich.")
        # -------------------------------------------------------------------------------

        # Bootstrap-Parameter
        if params:
            md = float(params.get('md', 100))
            ma = int(round(float(params.get('ma', 100)) * 1.1))
            tr = float(params.get('tr', 0.5))
            pz = int(params.get('pz', 50))
            sz = int(params.get('sz', 100))
            hz = int(params.get('hz', 1))
            vc = int(params.get('vc', 1))
        else:
            clip = getattr(context.space_data, "clip", None)
            if clip is None:
                raise RuntimeError("Kein aktiver Clip verfügbar (Fallback fehlgeschlagen).")
            hz, vc = clip.size
            tracking_settings = getattr(clip.tracking, "settings", None)
            ma = getattr(tracking_settings, "margin", 100)
            pz = getattr(tracking_settings, "pattern_size", 50)
            sz = getattr(tracking_settings, "search_size", 100)
            md = hz * 0.025
            tr = 0.0001

        # --- Baseline-Fix -------------------------------------------------------
        pre_snapshot = snapshot_active_markers(context)
        clip = getattr(context.space_data, "clip", None)
        tracking = getattr(clip, "tracking", None)
        baseline_start_tracknames = set(t.name for t in tracking.tracks) if tracking else set()
        print(f"[Kaiserlich Tracker][DetectAdapt] Ausgangsmarker: {len(pre_snapshot)} | "
              f"BaselineTracks: {len(baseline_start_tracknames)}")

        # --- Adaptive Schleife --------------------------------------------------
        max_loops = 8
        loop = 0
        frame_num = scene.frame_current

        # gespeicherten md-Wert laden
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

            detect_features(
                context,
                placement='FRAME',
                margin=ma,
                threshold=tr,
                min_distance=int(max(1, round(last_md)))
            )

            # Auto-Select fix
            if clip and getattr(clip, "tracking", None):
                for trk in clip.tracking.tracks:
                    trk.select = False

            # Klassifikation
            post_snapshot = snapshot_active_markers(context)
            alte_marker, neue_marker = classify_markers(pre_snapshot, post_snapshot)

            print(f"[Kaiserlich Tracker][DetectAdapt] Alte Marker erkannt: {len(alte_marker)}")
            print(f"[Kaiserlich Tracker][DetectAdapt] Neue Marker erkannt: {len(neue_marker)}")
            if neue_marker:
                print("   ➤ Beispiel neue Marker:", [m['track'] for m in neue_marker[:5]])
            if alte_marker:
                print("   ➤ Beispiel alte Marker:", [m['track'] for m in alte_marker[:5]])

            # Cleanup
            cleaned_new, deleted_old = cleanup_new_markers(
                context,
                alte_marker,
                neue_marker,
                pz=pz,
                hz=hz,
                vc=vc
            )

            neue_marker = cleaned_new
            remaining = len(neue_marker)

            # --- NEU: Dublettenprüfung wie im Vorbild --------------------------
            if clip and getattr(clip, "tracking", None):
                clip_tracks = {t.name for t in clip.tracking.tracks}
                real_new = [m for m in neue_marker if m['track'] not in baseline_start_tracknames and m['track'] in clip_tracks]
                if len(real_new) == 0:
                    print("[Kaiserlich Tracker][DetectAdapt] ❌ Keine echten neuen Marker erkannt – "
                          "Iteration wird fortgesetzt, min_distance wird reduziert.")
                    remaining = 0  # erzwingt erneute Iteration
            # -------------------------------------------------------------------

            print(f"[Kaiserlich Tracker][DetectAdapt] Nach Cleanup: {remaining} neue Marker übrig, {deleted_old} alte gelöscht")

            diff = remaining - ef_target
            tolerance = ef_target * 0.10

            if remaining == 0:
                print("[Kaiserlich Tracker][DetectAdapt] ⚠️ Keine gültigen neuen Marker nach Cleanup – weiterer Versuch nötig.")
            elif abs(diff) <= tolerance and remaining > 0:
                print(f"[Kaiserlich Tracker][DetectAdapt] ✅ Ziel erreicht: {remaining}/{ef_target} Marker (±{tolerance:.1f})")
                break
            else:
                print(f"[Kaiserlich Tracker][DetectAdapt] Abweichung vom Ziel: Δ={diff:+.0f}, Ziel={ef_target}, Toleranz={tolerance:.1f}")

            # --- Neue dynamische md-Anpassung nach Verhältnisformel ---
            if remaining == 0:
                # Sicherheitsfallback, falls alle Marker entfernt
                last_md = max(2.0, last_md * 0.8)
                print("[Kaiserlich Tracker][DetectAdapt] ⚠️ Keine Marker erkannt – Standardreduktion ×0.8 angewendet.")
            else:
                ratio = remaining / max(1, ef_target)
                factor = (((ratio - 1.0) / 2.0) + 1.0)
                new_md = last_md * factor
                new_md = min(max(new_md, 2.0), hz * 0.25)
                print(f"[Kaiserlich Tracker][DetectAdapt] Dynamische Anpassung: ratio={ratio:.3f}, factor={factor:.3f} → md {last_md:.2f} → {new_md:.2f}")
                last_md = new_md

            # Löschung, wenn weiterer Loop folgt
            if loop < max_loops:
                cleaned_names = [m['track'] for m in neue_marker]
                if cleaned_names:
                    delete_tracks_by_names(context, cleaned_names)
                    print(f"[Kaiserlich Tracker][DetectAdapt] {len(cleaned_names)} Marker gelöscht für nächsten Zyklus")
                else:
                    print("[Kaiserlich Tracker][DetectAdapt] Keine Marker zum Löschen gefunden – übersprungen.")
                time.sleep(0.1)

        # Final selektieren
        if clip and getattr(clip, "tracking", None):
            tracking = clip.tracking
            new_tracks = [trk for trk in tracking.tracks if trk.name not in baseline_start_tracknames]
            for trk in tracking.tracks:
                trk.select = False
            for trk in new_tracks:
                trk.select = True
            print(f"[Kaiserlich Tracker][DetectAdapt] Final selektierte Marker: {len(new_tracks)}")

        # Persistenz md-Wert
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
                    t = (f - f_start) / (f_end - f_start)
                    interp_val = v_start + (v_end - v_start) * t
                    md_dict[str(f)] = interp_val

        print(f"[Kaiserlich Tracker][DetectAdapt] Frame {frame_num}: final min_distance = {md_value:.2f}")

        # --- NEU: Playhead wieder auf Ursprungsposition zurücksetzen --------------------
        restore_frame = getattr(self._state, "original_frame_position", None)
        if restore_frame is not None:
            scene.frame_current = int(restore_frame)
            try:
                space = getattr(context, "space_data", None)
                if space and getattr(space, "clip_user", None):
                    space.clip_user.frame_current = int(restore_frame)
            except Exception:
                pass
            print(f"[ShortTest] ⏩ Playhead nach Test wiederhergestellt: Frame {restore_frame}")
        # -------------------------------------------------------------------------------

        self._state.created_track_names = [t.name for t in new_tracks] if new_tracks else []
        self._state.detect_adapt_done_confirmed = True

    # ------------------------------------------------------------------------
    # Track-Cycle: Start (Initialisierung, nicht-blockierend)
    # ------------------------------------------------------------------------
    def _track_cycle_start(self, context: bpy.types.Context):
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            raise RuntimeError("Kein aktiver Clip verfügbar.")
        
        tracking = getattr(clip, "tracking", None)
        new_tracks = getattr(self._state, "created_track_names", [])
        if not (tracking and new_tracks):
            raise RuntimeError("Keine neuen Tracks verfügbar für Tracking.")

        # --------------------------------------------------------------------
        # Startframe bestimmen:
        # - Primär: erster Marker-Frame der neuen Tracks
        # - Fallback: aktueller Frame oder Szenenstart
        # --------------------------------------------------------------------
        marker_frames = [
            tr.markers[0].frame
            for name in new_tracks
            if (tr := tracking.tracks.get(name)) and tr.markers
        ]
        if marker_frames:
            start_frame = min(marker_frames)
            print(f"[TrackCycle] ▶️ Startframe automatisch auf {start_frame} gesetzt (aus neuen Tracks).")
        else:
            start_frame = int(scene.frame_current or scene.frame_start)
            print(f"[TrackCycle] ▶️ Kein Marker-Frame gefunden – Fallback auf {start_frame}.")

        end_frame = get_end_frame(context)
        if end_frame < start_frame:
            end_frame = start_frame

        # --------------------------------------------------------------------
        # Editor-Bereich und State setzen
        # --------------------------------------------------------------------
        window, area, region, space = find_clip_editor_area(clip)
        if not window:
            raise RuntimeError("Keine CLIP_EDITOR Area gefunden.")

        self._state.track_active = True
        self._state.track_window = window
        self._state.track_area = area
        self._state.track_region = region
        self._state.track_space = space
        self._state.track_names = list(new_tracks)
        self._state.track_original_selected = list(new_tracks)
        self._state.track_start_frame = start_frame
        self._state.track_frame_end = end_frame
        self._state.track_frame_current = start_frame

        # --- Fix: Neu erzeugte Tracks selektieren (Pflicht für Tracking) ---
        try:
            for tr in tracking.tracks:
                tr.select = False  # erst alles abwählen
            for name in new_tracks:
                tr = tracking.tracks.get(name)
                if tr:
                    tr.select = True
            print(f"[Kaiserlich Tracker][TrackCycle] 🔹 {len(new_tracks)} neue Tracks selektiert.")
        except Exception as ex:
            print(f"[Kaiserlich Tracker][TrackCycle] ⚠️ Fehler beim Selektieren neuer Tracks: {ex!r}")

        # --- Diagnose: Track-Status zum Start ---
        selected_count = sum(1 for t in tracking.tracks if t.select)
        marker_summary = [
            (t.name, len(t.markers), getattr(t, 'select', False))
            for t in tracking.tracks if t.name in new_tracks
        ]
        print(f"[Debug][TrackStart] Neue Tracks: {len(new_tracks)} | Selektiert: {selected_count}")
        for n, m, s in marker_summary[:10]:
            print(f"   ▶ {n}: {m} Marker, {'SELECTED' if s else 'unselected'}")
        # --- Diagnose: Track-Status zum Start ---
        selected_count = sum(1 for t in tracking.tracks if t.select)
        marker_summary = [
            (t.name, len(t.markers), getattr(t, "select", False))
            for t in tracking.tracks if t.name in new_tracks
        ]
        print(f"[Debug][TrackStart] Neue Tracks: {len(new_tracks)} | Selektiert: {selected_count}")
        for n, m, s in marker_summary[:10]:
            print(f"   ▶ {n}: {m} Marker, {'SELECTED' if s else 'unselected'}")


        # Gesamtanzahl speichern für 75 %-Abbruchbedingung
        self._state.track_total_count = len(new_tracks)

        # Frame synchronisieren
        space.clip_user.frame_current = start_frame
        scene.frame_current = start_frame

        print(f"[Kaiserlich Tracker][TrackCycle] Start {start_frame} → {end_frame} (nicht-blockierend)")

    # ------------------------------------------------------------------------
    # Track-Cycle: Tick (ein Frame pro Timer, nicht-blockierend)
    # ------------------------------------------------------------------------

    def _track_cycle_tick(self, context: bpy.types.Context) -> bool:
        """Führt genau einen Tracking-Schritt aus.
        Gibt True zurück, solange weitergetrackt werden soll; False bei Abschluss/Abbruch.
        """
        s = self._state
        if not s.track_active:
            return False

        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        tracking = getattr(clip, "tracking", None) if clip else None
        if not tracking:
            print("[TrackCycle] Kein Tracking verfügbar – Abbruch.")
            s.track_active = False
            return False

        current = s.track_frame_current
        end = s.track_frame_end

        # --- 1) Aktive Tracks prüfen ---------------------------------------
        active_tracks, dropped = filter_active_tracks_at_frame(context, s.track_names, current)
        if not active_tracks:
            print("[TrackCycle] ✅ Keine aktiven Tracks mehr – Tracking beendet.")
            s.track_active = False
            return False

        s.track_names = active_tracks  # Update der Liste
        if dropped > 0:
            print(f"[TrackCycle] {dropped} inaktive Tracks entfernt → {len(active_tracks)} verbleibend.")

        # --- Neue Abbruchbedingungen ---
        frames_per_track = int(scene.kaiserlich_frames_per_track) * 2
        current_frame_index = current - s.track_start_frame

        # 1. Wenn die gewünschte Frameanzahl pro Track erreicht ist
        if current_frame_index >= frames_per_track:
            print(f"[TrackCycle] ⏹️ Zielanzahl an Frames pro Track erreicht "
                  f"({current_frame_index} ≥ {frames_per_track}) – Tracking beendet.")
            s.track_active = False
            return False

        # 2. Wenn keine aktiven Tracks mehr vorhanden sind
        if len(active_tracks) == 0:
            print(f"[TrackCycle] ✅ Keine aktiven Tracks mehr bei Frame {current} – Tracking beendet.")
            s.track_active = False
            return False

        # 3. Wenn das Szenenende erreicht oder überschritten wurde
        if current >= end:
            print(f"[TrackCycle] ✅ Szenenende erreicht bei Frame {current}.")
            s.track_active = False
            return False
        # --- 2) Formel anwenden (optional) ----------------------------------
        try:
            apply_formula_on_selected_tracks(context, max_frames=5)
        except Exception as e:
            print(f"[TrackCycle] Formel-Fehler: {e}")

        # --- 3) Einen Frame weiter tracken ----------------------------------
        # --- Diagnose: Vor dem Tracking-Schritt ---
        visible_tracks = [t.name for t in tracking.tracks if t.select]
        active_frames = [
            (t.name, [mk.frame for mk in t.markers])
            for t in tracking.tracks if t.name in s.track_names
        ]
        print(f"[Debug][Tick] Selektierte Tracks im Clip: {len(visible_tracks)} → {visible_tracks[:5]}")
        print(f"[Debug][Tick] Aktive Marker-Frames pro Track:")
        for n, frames in active_frames[:10]:
            print(f"   ▶ {n}: {len(frames)} Marker ({frames[:5]}...)")

        success = track_markers_with_override(
            s.track_window, s.track_area, s.track_region, s.track_space,
            backwards=False, sequence=False
        )

        if success:
            post_marker_summary = {
                t.name: len(t.markers)
                for t in tracking.tracks if t.name in s.track_names
            }
            print(f"[Debug][Tick] Nach Tracking: Marker-Anzahlen = {post_marker_summary}")
        if not success:
            print("[TrackCycle] Tracking-Fehler – Abbruch.")
            s.track_active = False
            return False

        # --- 4) Frame fortsetzen -------------------------------------------
        current += 1
        if current > end:
            print("[TrackCycle] ✅ Szenenende erreicht.")
            s.track_active = False
            return False

        scene.frame_current = current
        s.track_space.clip_user.frame_current = current
        s.track_frame_current = current

        return True

    # ------------------------------------------------------------------------
    # Hilfsmethode: Rot-Schwellenwerte auf 0 setzen
    # ------------------------------------------------------------------------
    def _set_rot_thresholds_zero(self, context: bpy.types.Context) -> None:
        """Setzt die Rot-Schwellenwerte (X und Y) auf 0.00001.
        Dies nutzt util_scene.set_scene_props, um die Szene-Attribute sicher zu setzen.
        """
        scene = context.scene
        try:
            # Verwende set_scene_props, um die Attribute zu setzen, falls verfügbar.
            set_scene_props(scene, kaiserlich_rot_thresh_x=0.00001, kaiserlich_rot_thresh_y=0.00001)
            print("[Kaiserlich Tracker][AutoCalibrate] Rot-Schwellwerte auf 0 gesetzt.")
        except Exception as ex:
            print(f"[AutoCalibrate] Fehler beim Setzen der Rot-Schwellwerte auf 0: {ex!r}")

    # ------------------------------------------------------------------------
    # Track-Cycle: Cleanup/Finish
    # ------------------------------------------------------------------------
    def _track_cycle_finish(self, context: bpy.types.Context):
        """Selektions-Reset, Baseline und Cleanup per Namensliste (löscht **alle** neu erzeugten Tracks)."""
        clip = getattr(context.space_data, "clip", None)
        tracking = getattr(clip, "tracking", None) if clip else None

        try:
            # ----------------------------------------------------------------
            # 0) Vorab-Filterung neuer Tracks mit Threshold 30
            # ----------------------------------------------------------------
            new_tracks = getattr(self._state, "created_track_names", [])
            if new_tracks:
                print(f"[Kaiserlich Tracker][FilterDelete] Vor Tracklängen-Messung: {len(new_tracks)} neue Tracks erkannt.")
                try:
                    filter_and_delete_tracks(
                        include_names=new_tracks,
                        threshold=30,
                        clip=clip
                    )
                    print(f"[Kaiserlich Tracker][FilterDelete] ✅ Filter/Delete auf neue Tracks angewendet ({len(new_tracks)} Stück).")
                except Exception as e:
                    print(f"[Kaiserlich Tracker][FilterDelete] ⚠️ Fehler bei Filter/Delete: {e}")
            else:
                print("[Kaiserlich Tracker][FilterDelete] ⚠️ Keine neuen Tracks zum Filtern gefunden.")

            # 1) Letzten aktiven Frame sichern (ohne Off-by-One-Kompensation)
            end_f = int(self._state.track_frame_current or context.scene.frame_current)
            scene = context.scene
            scene.frame_current = end_f
            if self._state.track_space:
                self._state.track_space.clip_user.frame_current = end_f

            # Sicherstellen, dass View-Layer den letzten Tracking-Status widerspiegelt
            try:
                bpy.context.view_layer.update()
                print(f"[TrackCycle] View-Layer synchronisiert (Frame {end_f}).")
            except Exception as ex:
                print(f"[TrackCycle] ⚠️ View-Layer-Update fehlgeschlagen: {ex!r}")

            # 2) Gesamt-Track-Länge der verbleibenden Tracks messen, bevor irgendetwas gelöscht wird
            total_len = int(
                get_total_track_length(
                    context,
                    start_frame=int(self._state.track_start_frame or 1),
                    include_names=getattr(self._state, "created_track_names", []),
                )
            )
            print(
                f"[Kaiserlich Tracker][TrackLen] Nur neue Tracks berücksichtigt "
                f"({len(getattr(self._state, 'created_track_names', []))} Namen gefiltert)."
            )
            cycle_idx = int(getattr(self._state, "track_cycles_done", 0)) + 1
            key_cycle = f"kaiserlich_len_cycle_{cycle_idx}"
            scene[key_cycle] = total_len

            # Baseline im ersten Zyklus zusätzlich speichern (wie bisher)
            if cycle_idx == 1:
                scene[SCENE_TOTAL_TRACK_LEN_BASE] = total_len
                print(f"[Kaiserlich Tracker][Baseline] Total Track Length (Frame {end_f}) = {total_len} (gespeichert unter '{SCENE_TOTAL_TRACK_LEN_BASE}' und '{key_cycle}')")
            else:
                print(f"[Kaiserlich Tracker][Baseline] Total Track Length (Frame {end_f}) = {total_len} (gespeichert unter '{key_cycle}')")

            # 3) Danach Playhead auf Tracking-Start-Frame zurücksetzen (für internen Folgezyklus)
            start_f = int(self._state.track_start_frame or 1)
            reset_to_frame(context, start_f)
            context.scene.frame_current = start_f
            if self._state.track_space:
                self._state.track_space.clip_user.frame_current = start_f
            print(f"[Kaiserlich Tracker][TrackCycle] ▶️ Playhead zurück auf Frame {start_f} (nach Messung).")

            # HINWEIS: Nicht dauerhaft auf Startframe "stehen bleiben".
            # Die finale Rücksetzung auf die ursprüngliche User-Position erfolgt zentral in _teardown().
            # --- Persistente Sammelstruktur für spätere Analyse ---
            # Speichert alle gemessenen Längen in einer Liste unter 'kaiserlich_len_results'
            results = scene.get("kaiserlich_len_results", [])
            results.append({
                "cycle": cycle_idx,
                "length": total_len,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "thresholds": self._state.cycle_thresholds.get(cycle_idx, {}),
            })
            scene["kaiserlich_len_results"] = results

            # Optional: Fortschritt loggen
            print(f"[Kaiserlich Tracker][Persistenz] Zyklus {cycle_idx}: Länge={total_len}, Thresholds={self._state.cycle_thresholds.get(cycle_idx, {})}")

            # --- Best-Value Tracking (fortlaufend) ---
            best_len = scene.get("kaiserlich_len_best", 0)
            if total_len > best_len:
                scene["kaiserlich_len_best"] = total_len
                scene["kaiserlich_len_best_cycle"] = cycle_idx
                scene["kaiserlich_len_best_thresholds"] = self._state.cycle_thresholds.get(cycle_idx, {})
                print(f"[Kaiserlich Tracker][Persistenz] 🔹 Neuer Bestwert in Zyklus {cycle_idx}: {total_len}")

            # 3) Alle neu erzeugten Tracks deterministisch per Namen löschen
            deleted_total = 0
            # Primäre Quelle: created_track_names (wurde in _detect_adapt_inline gesetzt)
            names_to_delete = list(dict.fromkeys(getattr(self._state, "created_track_names", [])))
            # Fallback: falls leer, letzte aktive Liste verwenden (kann nur 1 Name enthalten)
            if not names_to_delete:
                names_to_delete = list(dict.fromkeys(self._state.track_names or []))

            if names_to_delete:
                for name in names_to_delete:
                    try:
                        deleted_total += delete_tracks_by_names(context, [name])
                    except Exception as _e:
                        print(f"[Kaiserlich Tracker][Cleanup] ⚠️ Fehler beim Löschen von '{name}': {_e!r}")
                print(f"[Kaiserlich Tracker][Cleanup] {deleted_total} Tracks gelöscht (pro Name).")
            else:
                print("[Kaiserlich Tracker][Cleanup] ⚠️ Keine gültigen Tracks zum Löschen gefunden.")

        except Exception as e:
            print(f"[Kaiserlich Tracker][Cleanup] ⚠️ Fehler beim Abschlusslauf: {e}")

        print("[Kaiserlich Tracker][TrackCycle] ✅ Zyklus vollständig abgeschlossen.")
        return None

    # ------------------------------------------------------------------------
    # Cleanup / Teardown (muss innerhalb der Klasse definiert sein)
    # ------------------------------------------------------------------------
    def _teardown(self, context: bpy.types.Context, cancelled: bool):
        """Timer sicher entfernen und Operator sauber beenden."""
        wm = context.window_manager
        if getattr(self, "_timer", None):
            try:
                wm.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None

        # NEU: globale Wiederherstellung der ursprünglichen User-Playhead-Position
        try:
            if getattr(self._state, "user_original_frame", None) is not None:
                restore = int(self._state.user_original_frame)
                context.scene.frame_current = restore
                if getattr(context, "space_data", None) and getattr(context.space_data, "clip_user", None):
                    context.space_data.clip_user.frame_current = restore
                print(f"[ShortTest] ⏩ Playhead global wiederhergestellt: {restore}")
        except Exception as _e:
            print(f"[ShortTest] ⚠️ Globale Wiederherstellung fehlgeschlagen: {_e!r}")

        msg = "Auto Calibrate abgebrochen." if cancelled else "Auto Calibrate abgeschlossen."
        try:
            self.report({'INFO'}, msg)
        except Exception:
            print(f"[Kaiserlich Tracker][AutoCalibrate] {msg}")
        # ------------------------------------------------------------
        # NEU: Automatischer Übergang zu DeepTest nach erfolgreichem Abschluss
        # ------------------------------------------------------------
        if not cancelled:
            try:
                print("[Kaiserlich Tracker][ShortTest] ➜ Übergabe an DeepTest-Operator geplant (asynchron)...")
                clip = get_active_clip(context)
                window, area, region, space = find_clip_editor_area(clip)

                if not window:
                    print("[Kaiserlich Tracker][ShortTest] ⚠️ Kein gültiger CLIP_EDITOR-Kontext für Übergabe gefunden.")
                else:
                    def _launch_deeptest():
                        try:
                            with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                                bpy.ops.kaiserlich_tracker.deep_test_operator('INVOKE_DEFAULT')
                                print("[Kaiserlich Tracker][ShortTest] DeepTest-Operator erfolgreich (asynchron) gestartet.")
                        except Exception as ex:
                            print(f"[Kaiserlich Tracker][ShortTest] ⚠️ Fehler beim Start des DeepTest-Operators: {ex!r}")
                        return None

                    bpy.app.timers.register(_launch_deeptest, first_interval=0.1)

            except Exception as ex:
                print(f"[Kaiserlich Tracker][ShortTest] ⚠️ Planung der Übergabe an DeepTest-Operator fehlgeschlagen: {ex!r}")

        return {'CANCELLED' if cancelled else 'FINISHED'}

# ----------------------------------------------------------------------------
# Registration
# ----------------------------------------------------------------------------
_classes = (KAISERLICHTRACKER_OT_master_shorttest_operator,)

def register():
    for cls in _classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
