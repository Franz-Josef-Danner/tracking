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

# ----------------------------------------------------------------------------
#  Modal-Operator mit deterministischer State-Steuerung
# ----------------------------------------------------------------------------
# Szene-Key für Baseline-Tracklänge (späterer Vergleich)
SCENE_TOTAL_TRACK_LEN_BASE = "kaiserlich_len_baseline_00"


@dataclass
class _AutoCalibState:
    # Pipeline-Flags
    initialized: bool = False
    done: bool = False
    step: int = 0
    notes: Deque[str] = field(default_factory=lambda: deque(maxlen=200))

    did_reset_thresholds: bool = False
    did_detect_adapt: bool = False
    detect_adapt_done_confirmed: bool = False
    did_track_cycle: bool = False

    # Laufzeitstatus für Track-Cycle (nicht-blockierend)
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
    # Namen-Listen zur sauberen Identifikation neuer Tracks (Fix für "nur 1 Track gelöscht")
    baseline_track_names: List[str] = field(default_factory=list)
    created_track_names: List[str]  = field(default_factory=list)
    # Anzahl der abgeschlossenen Track-Cycle-Iterationen. Ein zusätzlicher Track-Cycle
    # wird nach dem ersten Lauf angestoßen, um die Rot-Schwellenwerte auf 0 zu testen.
    track_cycles_done: int = 0

    # Flags für zusätzliche Zyklen. second_cycle wird gesetzt, sobald der erste
    # Durchlauf abgeschlossen wurde und ein zweiter Detect‑/Track‑Zyklus gestartet
    # wird (Rot-Schwellenwerte = 0). third_cycle wird gesetzt, sobald der
    # zweite Durchlauf abgeschlossen wurde und ein dritter Detect‑/Track‑Zyklus
    # gestartet wird (Scale-Min/Max = 0). Diese Flags verhindern, dass die
    # End-Logik zu früh ausgelöst wird.
    second_cycle: bool = False
    third_cycle: bool = False

class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Kaiserlich Tracker — Auto Calibrate (komplette Pipeline, nicht-blockierend)"""
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Kaiserlich Tracker — Auto Calibrate"
    bl_options = {'REGISTER', 'UNDO'}

    _timer: Optional[Any] = None
    _state: _AutoCalibState

    # ------------------------------------------------------------------------
    # Invoke / Modal Setup
    # ------------------------------------------------------------------------
    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)  # ~20 Hz
        wm.modal_handler_add(self)
        self._state = _AutoCalibState()

        clip = get_active_clip(context)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver MovieClip gefunden.")
            return {'CANCELLED'}

        self._state.notes.append("Init OK (modal).")
        return {'RUNNING_MODAL'}

    # ------------------------------------------------------------------------
    # Haupt-State-Machine
    # ------------------------------------------------------------------------
    def modal(self, context: bpy.types.Context, event: bpy.types.Event):
        if event.type == 'ESC':
            return self._teardown(context, cancelled=True)

        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        # 0) Initialisierung
        if not self._state.initialized:
            self._state.initialized = True
            print("[Kaiserlich Tracker][AutoCalibrate] Initialized.")
            return {'RUNNING_MODAL'}

        # 1) Threshold-Reset
        if not self._state.did_reset_thresholds:
            try:
                reset_all_thresholds(context, active_props=[])
                self._state.did_reset_thresholds = True
                print("[Kaiserlich Tracker][AutoCalibrate] Thresholds reset → 1.0")
            except Exception as ex:
                print(f"[AutoCalibrate] Threshold reset failed: {ex!r}")
                # trotzdem fortfahren, um nicht zu blockieren
                self._state.did_reset_thresholds = True
            return {'RUNNING_MODAL'}

        # 2) Detect-Adapt inline (setzt detect_adapt_done_confirmed intern)
        if not self._state.did_detect_adapt:
            print("[Kaiserlich Tracker][AutoCalibrate] Detect-Adapt gestartet.")
            try:
                self._detect_adapt_inline(context)
            except Exception as ex:
                print(f"[AutoCalibrate] Detect-Adapt Fehler: {ex!r}")
                # Fortfahren, aber Flag setzen, damit die Pipeline nicht hängen bleibt
                self._state.detect_adapt_done_confirmed = True
            self._state.did_detect_adapt = True
            return {'RUNNING_MODAL'}

        # 3) Warten, bis Detect-Adapt das Abschluss-Flag gesetzt hat
        if self._state.did_detect_adapt and not self._state.detect_adapt_done_confirmed:
            # Noch keine Bestätigung aus Detect-Adapt → weiter warten
            return {'RUNNING_MODAL'}

        # 4) Track-Cycle nicht-blockierend
        if self._state.detect_adapt_done_confirmed:
            # Initialisieren, falls noch nicht aktiv
            if not self._state.track_active and not self._state.did_track_cycle:
                try:
                    self._track_cycle_start(context)
                    print("[Kaiserlich Tracker][AutoCalibrate] Track-Cycle initialisiert.")
                except Exception as ex:
                    print(f"[AutoCalibrate] Track-Cycle Init Fehler: {ex!r}")
                    # Kein Tracking möglich → Pipeline sauber beenden
                    self._state.did_track_cycle = True
                    return {'RUNNING_MODAL'}
                return {'RUNNING_MODAL'}

            # Tick-basiertes Tracking (ein Frame pro Timer)
            if self._state.track_active:
                still_running = self._track_cycle_tick(context)
                if not still_running:
                    # Tracking abgeschlossen oder abgebrochen
                    self._track_cycle_finish(context)
                    self._state.track_active = False
                    # erhöhe Zähler für abgeschlossene Zyklen
                    self._state.track_cycles_done += 1
                    # Markiere, dass ein Track-Cycle vollständig abgeschlossen wurde. Wir
                    # starten mögliche weitere Detect-/Track‑Zyklen außerhalb dieses
                    # Abschnitts im Modal-State-Loop. Dadurch wird nach jeder
                    # Iteration erst wieder ein Detect-Adapt durchgeführt, bevor ein
                    # neuer Track-Cycle beginnt.
                    self._state.did_track_cycle = True
                    print("[Kaiserlich Tracker][AutoCalibrate] Track-Cycle abgeschlossen.")
                    return {'RUNNING_MODAL'}

        # 5) Abschluss oder Vorbereitung auf weitere Zyklen
        if not self._state.done and self._state.did_track_cycle:
            # Wenn noch kein zweiter Durchlauf durchgeführt wurde, starte diesen:
            if not self._state.second_cycle:
                try:
                    # Setze Rot-Schwellenwerte (X/Y) auf 0,0
                    print("[Kaiserlich Tracker][AutoCalibrate] Rot-Schwellwerte auf 0 gesetzt.")
                    set_scene_props(context.scene,
                                    kaiserlich_rot_thresh_x=0.0,
                                    kaiserlich_rot_thresh_y=0.0)
                except Exception as ex:
                    print(f"[AutoCalibrate] Fehler beim Setzen der Rot-Schwellenwerte: {ex!r}")
                # Flags setzen, um zweiten Detect-/Track‑Durchlauf zu initiieren
                self._state.second_cycle = True
                # Detect-Adapt und Track-Cycle erneut ausführen
                self._state.did_detect_adapt = False
                self._state.detect_adapt_done_confirmed = False
                self._state.did_track_cycle = False
                return {'RUNNING_MODAL'}

            # Wenn der zweite Durchlauf bereits erledigt ist, aber noch kein dritter:
            if self._state.second_cycle and not self._state.third_cycle:
                try:
                    # Setze alle Thresholds auf 1.0 zurück und Scale-Min/Max auf 0.0
                    print("[Kaiserlich Tracker][AutoCalibrate] Thresholds auf 1.0 gesetzt, Scale-Min/Max auf 0.0.")
                    reset_all_thresholds(context, active_props=[])
                    set_scene_props(context.scene,
                                    kaiserlich_scale_thresh_min=0.0,
                                    kaiserlich_scale_thresh_max=0.0)
                except Exception as ex:
                    print(f"[AutoCalibrate] Fehler beim Zurücksetzen der Thresholds: {ex!r}")
                # Flags setzen, um dritten Detect-/Track‑Durchlauf zu initiieren
                self._state.third_cycle = True
                self._state.did_detect_adapt = False
                self._state.detect_adapt_done_confirmed = False
                self._state.did_track_cycle = False
                return {'RUNNING_MODAL'}

            # Wenn sowohl zweiter als auch dritter Durchlauf abgeschlossen wurden, beenden.
            self._state.done = True
            return self._teardown(context, cancelled=False)

        # (entfernt) Dritter Durchlauf darf nur im Abschnitt
        # "5) Abschluss oder Vorbereitung auf weitere Zyklen"
        # nach did_track_cycle==True getriggert werden.

        return {'RUNNING_MODAL'}

    # ------------------------------------------------------------------------
    # Detect-Adapt Inline (komplett, mit Flag-Setzung)
    # ------------------------------------------------------------------------
    def _detect_adapt_inline(self, context: bpy.types.Context):
        scene = context.scene
        ef_target = int(scene.kaiserlich_markers_per_frame)

        # Bootstrap-Parameter laden oder Fallback berechnen
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
            clip = getattr(context.space_data, "clip", None)
            if clip is None:
                raise RuntimeError("Kein aktiver Clip verfügbar (Fallback fehlgeschlagen).")

            hz = clip.size[0]
            vc = clip.size[1]

            scene_obj = getattr(context, "scene", None)
            frame_end = scene_obj.frame_end if scene_obj else None

            tracking_settings = getattr(clip.tracking, "settings", None)
            ma = getattr(tracking_settings, "margin", 100) if tracking_settings else 100
            pz = getattr(tracking_settings, "pattern_size", 50) if tracking_settings else 50
            sz = getattr(tracking_settings, "search_size", 100) if tracking_settings else 100

            md = hz * 0.025
            tr = 0.0001
            za = ef_target * 4
            og = math.ceil(za * 1.1)
            ug = math.floor(za * 0.9)

            print(f"[Kaiserlich Tracker][DetectAdapt][Fallback] "
                  f"hz={hz}, vc={vc}, margin={ma}, md={md:.2f}, "
                  f"pattern={pz}, search={sz}, tr={tr}, og={og}, ug={ug}, frame_end={frame_end}")

        # Baseline erfassen
        pre_snapshot = snapshot_active_markers(context)
        clip = getattr(context.space_data, "clip", None)
        tracking = getattr(clip, "tracking", None) if clip else None
        baseline_start_tracknames: Set[str] = {t.name for t in tracking.tracks} if tracking else set()

        print(f"[Kaiserlich Tracker][DetectAdapt] Ausgangsmarker: {len(pre_snapshot)} | BaselineTracks: {len(baseline_start_tracknames)}")
        # Baseline im State merken, damit wir später exakt die neu entstandenen Tracks identifizieren können.
        self._state.baseline_track_names = list(baseline_start_tracknames)

        max_loops = 8
        loop = 0
        frame_num = scene.frame_current
        deleted_old = 0

        # Startwert für last_md ggf. aus Szene übernehmen
        last_md = md
        if "min_distance_values" in scene:
            md_dict = scene["min_distance_values"]
            if str(frame_num) in md_dict:
                last_md = float(md_dict[str(frame_num)])

        # Adaptive Schleife
        reached = False
        while loop < max_loops:
            loop += 1
            print(f"\n[Kaiserlich Tracker][DetectAdapt] --- LOOP {loop} ---")
            print(f"[Kaiserlich Tracker][DetectAdapt] Aktuelles min_distance = {last_md:.2f}")

            # Detect
            detect_features(
                context,
                placement='FRAME',
                margin=ma,
                threshold=tr,
                min_distance=int(max(1, round(last_md)))
            )

            # Snapshot nach Detect
            post_snapshot = snapshot_active_markers(context)
            alte_marker, neue_marker = classify_markers(pre_snapshot, post_snapshot)
            print(f"[Kaiserlich Tracker][DetectAdapt] Alte Marker: {len(alte_marker)}, Neue Marker: {len(neue_marker)}")

            # Cleanup
            cleaned_new, deleted_old = cleanup_new_markers(
                context,
                alte_marker,
                neue_marker,
                pz=pz,
                hz=hz,
                vc=vc
            )

            remaining = len(cleaned_new)
            diff = remaining - ef_target
            tolerance = ef_target * 0.10  # ±10 %

            if abs(diff) <= tolerance:
                print(f"[Kaiserlich Tracker][DetectAdapt] Ziel erreicht: {remaining}/{ef_target} (±{tolerance:.1f})")
                reached = True
                break

            # Dynamische Anpassung von min_distance
            am = len(neue_marker)
            if am > 0:
                ratio = ef_target / am
                factor = max(0.5, min(2.0, ratio))
                last_md = max(1.0, last_md / factor)
            else:
                last_md *= 1.5
                print("[DetectAdapt] Keine neuen Marker → erhöhe min_distance stark")

            # Für nächsten Loop aufräumen
            if loop < max_loops:
                delete_tracks_by_names(context, [m['track'] for m in neue_marker])
                time.sleep(0.1)

        # Abschlussstatus setzen
        if reached:
            self._state.detect_adapt_done_confirmed = True
        else:
            print("[⚠️ Kaiserlich Tracker][DetectAdapt] Keine stabile Markeranzahl – fahre dennoch fort.")
            self._state.detect_adapt_done_confirmed = True

        # Alle Marker nach Abschluss selektieren (Startpunkt für Tracking)
        if clip and getattr(clip, 'tracking', None):
            for trk in clip.tracking.tracks:
                trk.select = True
            print("[DetectAdapt] Alle Marker nach Abschluss selektiert.")

        # Frame-spezifische min_distance speichern & einfache Interpolation
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
        # Liste der neu angelegten Tracks bestimmen und persistieren
        try:
            if tracking and getattr(tracking, "tracks", None):
                current_names = [t.name for t in tracking.tracks]
                base_set = set(self._state.baseline_track_names or [])
                created = [n for n in current_names if n not in base_set]
                self._state.created_track_names = created
                print(f"[Kaiserlich Tracker][DetectAdapt] Neu erzeugte Tracks: {len(created)} → {created[:5]}{' …' if len(created) > 5 else ''}")
            else:
                self._state.created_track_names = []
                print("[Kaiserlich Tracker][DetectAdapt] ⚠️ Konnte neue Tracks nicht bestimmen (keine Tracking-Daten).")
        except Exception as _e:
            self._state.created_track_names = []
            print(f"[Kaiserlich Tracker][DetectAdapt] ⚠️ Fehler beim Ermitteln neuer Tracks: {_e!r}")

    # ------------------------------------------------------------------------
    # Track-Cycle: Start (Initialisierung, nicht-blockierend)
    # ------------------------------------------------------------------------
    def _track_cycle_start(self, context: bpy.types.Context):
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            raise RuntimeError("Kein aktiver Clip verfügbar.")

        start_frame = scene.frame_start
        end_frame = get_end_frame(context)
        if end_frame < start_frame:
            end_frame = start_frame

        # Selektion erfassen oder fallback auf alle Tracks
        original_selected = collect_selected_track_names(context)
        if not original_selected:
            tracking = getattr(clip, "tracking", None)
            if tracking and tracking.tracks:
                original_selected = [t.name for t in tracking.tracks]
                for tr in tracking.tracks:
                    tr.select = True
                print(f"[TrackCycle] ⚠️ Keine Selektion – alle {len(original_selected)} Tracks aktiviert.")
            else:
                raise RuntimeError("Keine Tracks verfügbar für Tracking.")

        window, area, region, space = find_clip_editor_area(clip)
        if not window:
            raise RuntimeError("Keine CLIP_EDITOR Area gefunden.")

        # State setzen
        self._state.track_active = True
        self._state.track_window = window
        self._state.track_area = area
        self._state.track_region = region
        self._state.track_space = space
        self._state.track_names = list(original_selected)
        self._state.track_original_selected = list(original_selected)
        self._state.track_start_frame = start_frame
        self._state.track_frame_end = end_frame
        self._state.track_frame_current = max(start_frame, int(scene.frame_current))

        # Frame sync
        space.clip_user.frame_current = self._state.track_frame_current
        scene.frame_current = self._state.track_frame_current

        print(f"[Kaiserlich Tracker][TrackCycle] Start {start_frame} → {end_frame} (nicht-blockierend)")

    # ------------------------------------------------------------------------
    # Track-Cycle: Tick (ein Frame pro Timer, nicht-blockierend)
    # ------------------------------------------------------------------------
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

        # --- 2) Formel anwenden (optional) ----------------------------------
        try:
            apply_formula_on_selected_tracks(context, max_frames=5)
        except Exception as e:
            print(f"[TrackCycle] Formel-Fehler: {e}")

        # --- 3) Einen Frame weiter tracken ----------------------------------
        success = track_markers_with_override(
            s.track_window, s.track_area, s.track_region, s.track_space,
            backwards=False, sequence=False
        )
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
        """Setzt die Rot-Schwellenwerte (X und Y) auf 0.0.
        Dies nutzt util_scene.set_scene_props, um die Szene-Attribute sicher zu setzen.
        """
        scene = context.scene
        try:
            # Verwende set_scene_props, um die Attribute zu setzen, falls verfügbar.
            set_scene_props(scene, kaiserlich_rot_thresh_x=0.0, kaiserlich_rot_thresh_y=0.0)
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
            # 1) Playhead sicher auf Ursprungs-Frame fixieren
            start_f = int(self._state.track_start_frame or 1)
            reset_to_frame(context, start_f)
            context.scene.frame_current = start_f
            if self._state.track_space:
                self._state.track_space.clip_user.frame_current = start_f
            bpy.context.view_layer.update()
            print(f"[Kaiserlich Tracker][TrackCycle] ▶️ Playhead fixiert auf Frame {start_f}.")

            # 2) Baseline-Länge der verbleibenden (alten) Tracks speichern
            scene = context.scene
            total_len = int(get_total_track_length(context, start_frame=start_f))
            scene[SCENE_TOTAL_TRACK_LEN_BASE] = total_len
            print(f"[Kaiserlich Tracker][Baseline] Total Track Length ab Frame {start_f} = {total_len} (gespeichert unter '{SCENE_TOTAL_TRACK_LEN_BASE}')")

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
        msg = "Auto Calibrate abgebrochen." if cancelled else "Auto Calibrate abgeschlossen."
        try:
            self.report({'INFO'}, msg)
        except Exception:
            print(f"[Kaiserlich Tracker][AutoCalibrate] {msg}")
        return {'CANCELLED' if cancelled else 'FINISHED'}

# ----------------------------------------------------------------------------
#  Registration
# ----------------------------------------------------------------------------

_classes = (KAISERLICHTRACKER_OT_auto_calibrate,)

def register():
    for cls in _classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
