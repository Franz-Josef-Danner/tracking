# Operator/Master/master_track_operator.py
import bpy
from typing import List, Tuple, Dict, Deque, Optional
from collections import deque

# ------------------------------------------------------------
# Helper Imports (bestehend)
# ------------------------------------------------------------
from ...Helper.playhead_helper import get_start_frame as ph_get_start_frame, reset_to_frame
# Dieser Helper kapselt das Playhead-Handling: Er klemmt beliebige Frame-Werte hart auf die Szenenrange, liefert die aktuelle (geclampte) Playhead-Position und setzt mit reset_to_frame Szene und alle CLIP_EDITOR-Spaces, die den aktiven Clip anzeigen, synchron auf denselben Ziel-Frame.

from ...Helper.scene import get_end_frame
# Liefert den gültigen Frame-Bereich (frame_start, frame_end) der aktiven Szene defensiv bereinigt (Ende nie kleiner als Start) und stellt komfortable Getter für Start- und Endframe bereit.

from ...Helper.find_clip_editor_area import find_clip_editor_area
# Scannt alle offenen Blender-Fenster. Sucht den ersten CLIP_EDITOR, der entweder: schon genau den gewünschten Clip zeigt, oder noch keinen Clip gesetzt hat. Liefert dir (window, area, region, space_clip) für Context Overrides. Wenn nichts passt: (None, None, None, None) → Pflicht zur Fehlerbehandlung im aufrufenden Code.

from ...Helper.selection_helper import collect_selected_track_names
#Liest den aktuellen Clip aus dem Movie-Clip-Editor-Kontext. Holt dessen Tracking-Daten. Filtert alle Tracks mit t.select == True. Gibt ausschließlich die Track-Namen als List[str] zurück. Rückgabe bei fehlendem Clip/Tracking: leere Liste.

from ...Helper.filter_active_tracks import filter_active_tracks_at_frame
# ermittelt für einen gegebenen Frame alle noch „aktiv“ nutzbaren Tracks aus einer übergebenen Track-Namen-Liste, indem es pro Track den Marker im Ziel-Frame sucht und nur solche Tracks zurückgibt, deren Marker existiert und nicht gemutet ist. Zusätzlich liefert die Funktion die Anzahl der dadurch aussortierten (inaktiven oder nicht gefundenen) Tracks zurück.

from ...Helper.track_markers_helper import track_markers_with_override
# Stellt eine kapselnde Helper-Funktion für bpy.ops.clip.track_markers bereit, die den nötigen Movie-Clip-Editor-Context per temp_override setzt und optional vorwärts/rückwärts sowie im Sequence-Modus tracked. Gibt einen booleschen Erfolgsstatus zurück, anstatt Exceptions nach außen durchzureichen.

from ...Helper.frame_track_progress import compute_marker_progress
# compute_marker_progress berechnet für den aktuellen Movie Clip den Tracking-Fortschritt über die gesamte Szenenlänge: Pro Frame werden die aktiven, nicht gemuteten Marker gezählt (gecappt auf scene.kaiserlich_markers_per_frame), daraus wird ein prozentueller Roh-Fortschritt ermittelt und mit einem Qualitätsfaktor aus compute_track_quality_metrics multipliziert. Das Ergebnis wird als effektiver Fortschritt (value, perc_effektiv) zurückgegeben, in scene.kaiserlich_marker_progress geschrieben und optional die CLIP_EDITOR-UI per Redraw aktualisiert.

from ...Helper.adapt_search_size import adapt_search_size_for_calibrate_tracks
# Dieser Helper passt im aktuellen Frame die search_min/search_max aller in scene["calibrate_tracks"] hinterlegten Tracks dynamisch an: Er ermittelt dafür Referenz-Tracks mit gültigen Markern in F, F+1 und F+2, berechnet aus deren Bewegung (F → F+2) eine mittlere Distanz der drei nächstgelegenen Referenz-Tracks pro Kalibrations-Marker und setzt daraus eine bewegungsbasierte Search-Size im Pixelraum, wobei die pattern-basierte Größe (2 * pattern_size) als Mindestwert dient und die effektive Search-Size pro Achse auf 200 px gekappt wird.

from ...Helper.motion_average import get_from_selected_tracks
# Dieser Helper wertet die Bewegung der (selektierten, nicht gemuteten) Tracks im aktuellen Frame-Fenster aus, bestimmt daraus ein globales Motion-Model (Loc / LocRot / LocScale / LocRotScale + Perspective) und berechnet normalisierte, szenenweite Threshold-Werte. Dabei werden Bewegungs- und Perspektivmetriken historisiert (rolling MAX_HISTORY), Motion-Model-Häufigkeiten berücksichtigt und die finalen Schwellen in Scene-Properties (kaiserlich_*_thresh*, kaiserlich_model_count_*, kaiserlich_threshold_max_val) für nachgelagerte Operatoren bereitgestellt.

from ...Helper.formula_helper import apply_formula_on_selected_tracks
# Setzt für alle ausgewählten Tracks im aktuellen Frame das passende Motion Model (Loc / LocRot / LocScale / LocRotScale / Perspective), basierend auf einer rückwärtsgerichteten Analyse der Markerbewegung über mehrere Frames. Die Funktion berechnet dafür zunächst transformierte Thresholds aus der Szene, ermittelt ein globales Bewegungsmodell, prüft zusätzlich perspektivische Abweichungen (global und pro Marker) und weist anschließend jedem Track das resultierende Modell via apply_motion_model zu.

from ...Helper.threshold_stats import update_threshold_extrema
# Dieser Helper initialisiert und verwaltet alle Scene-Custom-Properties für die Threshold-Extrema (Rotation, Scale, Rot+Scale, Perspektive), bietet einen Hard-Reset der gespeicherten Min/Max-Werte, aktualisiert diese bei jedem Aufruf anhand der aktuellen UI-Thresholds und stellt optional eine Log-Ausgabe der aktuell gelernten Schwellenbereiche bereit.

from ...Helper.update_default_sizes import update_default_sizes
# Dieser Helper liest die aktuellen Tracking-Defaultwerte (Pattern-, Search-Size und Margin) des aktiven MovieClips, skaliert die Pattern-Size schrittweise nach oben (×1,1, geclamped auf 30–100), setzt Search-Size (= 2×Pattern) und default_margin entsprechend nach, schreibt die neuen Defaults zurück und triggert automatisch run_bootstrap, sobald die Pattern-Size das definierte Maximum erreicht.

from ...Helper.correct.correct_selected_by_ref_motion import correct_motion_by_reference
# correct_motion_by_reference analysiert für den aktuellen Frame f die Bewegungsvektoren der drei nächstgelegenen, nicht selektierten Referenz-Tracks (Marker aktiv bei f, f-1, f-2) und korrigiert die Position selektierter Marker nur dann, wenn deren Bewegungsvektor signifikant (> min_vec_diff) von der gemittelten Referenzbewegung abweicht, wobei nur Referenzen innerhalb max_near_dist berücksichtigt werden.

from ...Helper.correct.correct_selected_by_ref_dynamic import correct_motion_by_dynamic_reference


# ------------------------------------------------------------
# STORE CALIBRATE TRACKS (jetzt MIT LOGS)
# ------------------------------------------------------------
def store_calibrate_tracks_in_scene(context, track_names: List[str]) -> None:
    scene = context.scene
    if not track_names:
        print("[FORWARD][CALIBRATE_STORE] ⚠ Keine Track-Namen übergeben – Abbruch.")
        return

    try:
        # Alte Keys entfernen
        for key in ("calibrate_tracks", "calibrate_tracks_uuid_map"):
            if key in scene:
                del scene[key]
        print("[FORWARD][CALIBRATE_STORE] Entferne alte calibrate_tracks Keys.")

        clip = getattr(context.space_data, "clip", None)
        if not clip or not hasattr(clip, "tracking"):
            print("[FORWARD][CALIBRATE_STORE] ⚠ Kein Clip/Tracking gefunden – Speichern übersprungen.")
            return

        # UUID Map erzeugen
        import uuid as _uuid
        uuid_map: Dict[str, str] = {str(_uuid.uuid4()): name for name in track_names}

        scene["calibrate_tracks"] = list(track_names)
        scene["calibrate_tracks_uuid_map"] = str(uuid_map)

        print(f"[FORWARD][CALIBRATE_STORE] ✅ {len(track_names)} Tracks gespeichert.")

    except Exception as e:
        print(f"[FORWARD][CALIBRATE_STORE][ERROR] {e}")


# =====================================================================
# Hauptoperator
# =====================================================================
class KAISERLICHTRACKER_OT_master_track_cycle(bpy.types.Operator):
    bl_idname = "kaiserlich_tracker.master_track_cycle"
    bl_label = "Track Cycle (Modal)"
    bl_description = "Performs a non-blocking forward tracking cycle for all selected markers"
    bl_options = {"REGISTER", "INTERNAL"}

    max_frames: bpy.props.IntProperty(
        name="Max Frames",
        default=0,
        min=0,
        soft_max=100000,
        description="Safety limit (0 = no limit)"
    )

    _timer = None
    _processing_names: List[str]
    _original_selected: List[str]
    _histories: Dict[str, Deque[Tuple[int, float, float]]]
    _window = None
    _area = None
    _region = None
    _space = None
    _start_frame = 0
    _end_frame = 0
    _current_frame = 0
    _frames_processed = 0

    # --------------------------------------------------------
    # Initialization
    # --------------------------------------------------------
    def execute(self, context):
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'ERROR'}, "No active clip found.")
            print("[FORWARD][INIT] ❌ Kein aktiver Clip – Abbruch.")
            return {"CANCELLED"}

        # Start / Ende
        self._start_frame = ph_get_start_frame(context)
        self._end_frame = get_end_frame(context)
        if self._end_frame < self._start_frame:
            self._end_frame = self._start_frame

        # Selektion
        self._original_selected = collect_selected_track_names(context)
        if not self._original_selected:
            self.report({'WARNING'}, "No tracks selected.")
            print("[FORWARD][INIT] ⚠ Keine Tracks selektiert – Abbruch.")
            return {"CANCELLED"}
        self._processing_names = list(self._original_selected)

        # CLIP EDITOR
        self._window, self._area, self._region, self._space = find_clip_editor_area(clip)
        if not self._window:
            self.report({'ERROR'}, "No CLIP_EDITOR area found.")
            print("[FORWARD][INIT] ❌ Kein CLIP_EDITOR – Abbruch.")
            return {"CANCELLED"}

        # Playhead setzen
        self._current_frame = max(self._start_frame, int(scene.frame_current))
        self._space.clip_user.frame_current = self._current_frame
        scene.frame_current = self._current_frame

        # Historien
        self._histories = {name: deque(maxlen=10) for name in self._processing_names}

        # Auswahl fixieren
        for tr in clip.tracking.tracks:
            tr.select = (tr.name in self._original_selected)

        # Calibrate speichern
        store_calibrate_tracks_in_scene(context, self._processing_names)

        # Snapshot
        self._snapshot_tracks = list(self._processing_names)

        # Timer
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)

        print(
            f"[FORWARD][INIT] ✅ Start={self._start_frame}, End={self._end_frame}, "
            f"Frame={self._current_frame}, Tracks={len(self._processing_names)}"
        )
        return {"RUNNING_MODAL"}

    # --------------------------------------------------------
    # Modal Loop
    # --------------------------------------------------------
    def modal(self, context, event):
        if event.type == 'ESC':
            print("[FORWARD][MODAL] ⎋ ESC – Abbruch.")
            self._finish(context, cancelled=True)
            return {"CANCELLED"}

        if event.type != 'TIMER':
            return {"PASS_THROUGH"}

        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            print("[FORWARD][MODAL] ⚠ Kein Clip – Abbruch.")
            self._finish(context, cancelled=True)
            return {"CANCELLED"}

        tracking = clip.tracking

        # Step-Log
        print(f"[FORWARD][STEP] Frame={self._current_frame}, Active={len(self._processing_names)}")

        # Historien
        for name in list(self._processing_names):
            tr = tracking.tracks.get(name)
            if not tr:
                continue
            mk = tr.markers.find_frame(self._current_frame)
            if mk and not mk.mute:
                self._histories[name].append((self._current_frame, mk.co[0], mk.co[1]))

        # Calibration sichern + Korrekturen
        store_calibrate_tracks_in_scene(context, self._processing_names)
        correct_motion_by_reference(context)
        correct_motion_by_dynamic_reference(context)

        # Formel/Motion
        try:
            get_from_selected_tracks(context)
            apply_formula_on_selected_tracks(context)
            print("[FORWARD][STEP] 🔎 Formel/Bewegungsmodell angewendet.")
        except Exception as e:
            print(f"[FORWARD][STEP][FORMULA][ERROR] {e}")

        # Search-Size
        try:
            adapt_search_size_for_calibrate_tracks(context)
            print("[FORWARD][STEP] 📏 adapt_search_size OK.")
        except Exception as e:
            print(f"[FORWARD][STEP][ADAPT_SEARCH][ERROR] {e}")

        # Tracken
        success = track_markers_with_override(
            self._window, self._area, self._region, self._space,
            backwards=False, sequence=False
        )
        if not success:
            print("[FORWARD][STEP] ❌ track_markers_with_override fehlgeschlagen.")
            self._finish(context, cancelled=True)
            return {"CANCELLED"}

        # Frame weiter
        scene = context.scene
        if self._space.clip_user.frame_current == self._current_frame:
            self._space.clip_user.frame_current += 1
        if self._space.clip_user.frame_current > self._end_frame:
            self._space.clip_user.frame_current = self._end_frame

        scene.frame_current = self._space.clip_user.frame_current
        self._current_frame = self._space.clip_user.frame_current
        self._frames_processed += 1

        # Track-Filter
        before_filter = len(self._processing_names)
        self._processing_names, _ = filter_active_tracks_at_frame(
            context, self._processing_names, self._current_frame
        )
        print(f"[FORWARD][STEP] FilterActiveTracks: {before_filter} → {len(self._processing_names)}")

        # Exit
        if self._current_frame >= self._end_frame:
            print("[FORWARD][EXIT] ⏩ End-Frame erreicht.")
            self._finish(context)
            return {"FINISHED"}

        if not self._processing_names:
            print("[FORWARD][EXIT] ❌ Keine aktiven Tracks mehr.")
            self._finish(context)
            return {"FINISHED"}

        if self.max_frames > 0 and self._frames_processed >= self.max_frames:
            print("[FORWARD][EXIT] ⏱ MaxFrames erreicht.")
            self._finish(context)
            return {"FINISHED"}

        return {"RUNNING_MODAL"}

    # --------------------------------------------------------
    # Abschluss / Cleanup
    # --------------------------------------------------------
    def _finish(self, context, cancelled: bool = False):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
        self._timer = None

        print(f"[FORWARD][FINISH] 🧾 cancelled={cancelled}, frames={self._frames_processed}")

        # Auswahl wiederherstellen
        clip = getattr(context.space_data, "clip", None)
        if clip and hasattr(clip, "tracking"):
            for tr in clip.tracking.tracks:
                tr.select = (tr.name in self._original_selected)
            print("[FORWARD][FINISH] Auswahl wiederhergestellt.")

        # Reset Playhead auf Start
        try:
            reset_to_frame(context, self._start_frame)
            print(f"[FORWARD][FINISH] Playhead → {self._start_frame}")
        except Exception as e:
            print(f"[FORWARD][FINISH][RESET][ERROR] {e}")

        # Qualität / Progress
        try:
            from ...Helper.track_quality_metrics import compute_track_quality_metrics
            metrics = compute_track_quality_metrics(context)
            q = float(metrics.get("prozent", 100.0))
            context.scene.kaiserlich_quality_percent = f"{int(round(q))}%"
            print(f"[FORWARD][FINISH] Qualität = {context.scene.kaiserlich_quality_percent}")
        except Exception:
            pass

        try:
            _, perc = compute_marker_progress(context.scene, update_ui=True)
            context.scene.kaiserlich_marker_progress = f"{int(round(perc))}%"
            print(f"[FORWARD][FINISH] Marker-Progress = {context.scene.kaiserlich_marker_progress}")
        except Exception:
            pass

        # Übergabe (nur wenn nicht abgebrochen)
        if not cancelled:
            try:
                print("[FORWARD][HANDOVER] ▶ Starte master_cycle_operator …")
                bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')
            except Exception as e:
                print(f"[FORWARD][HANDOVER][ERROR] {e}")


# ------------------------------------------------------------
# Register
# ------------------------------------------------------------
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_track_cycle)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_track_cycle)
