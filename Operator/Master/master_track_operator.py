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

from ...Helper.validate_motion_forward_helper import _get_positions_backward
# Validiert in der aktuellen Szene die Vorwärtsbewegung der calibrate_tracks, indem rückwärts gerichtete Bewegungsvektoren (dx, dy) über mehrere Frames aus den best- bzw. good_tracks als Referenzmittelwert berechnet werden und alle Kalibrier-Marker, deren Bewegungsabweichung über einem aus scene.max_error_value abgeleiteten Schwellwert liegt, im aktuellen Frame gezielt gemutet werden; sämtliche Schritte (Track-Auflösung, Vektorerzeugung, Threshold, Mute-Aktionen, Statistiken) werden detailliert geloggt.

from ...Helper.update_default_sizes import update_default_sizes
# Dieser Helper liest die aktuellen Tracking-Defaultwerte (Pattern-, Search-Size und Margin) des aktiven MovieClips, skaliert die Pattern-Size schrittweise nach oben (×1,1, geclamped auf 30–100), setzt Search-Size (= 2×Pattern) und default_margin entsprechend nach, schreibt die neuen Defaults zurück und triggert automatisch run_bootstrap, sobald die Pattern-Size das definierte Maximum erreicht.

from ..Helper.correct_selected_by_ref_motion import correct_motion_by_reference
# correct_motion_by_reference analysiert für den aktuellen Frame f die Bewegungsvektoren der drei nächstgelegenen, nicht selektierten Referenz-Tracks (Marker aktiv bei f, f-1, f-2) und korrigiert die Position selektierter Marker nur dann, wenn deren Bewegungsvektor signifikant (> min_vec_diff) von der gemittelten Referenzbewegung abweicht, wobei nur Referenzen innerhalb max_near_dist berücksichtigt werden.

# ------------------------------------------------------------
# Neuer Korrektur-Helper
# ------------------------------------------------------------
from ...Helper.marker_position_forward_calibration import (
    _resolve_reference_key,
    correct_marker_positions
)

# ------------------------------------------------------------
# Interner Helper: Speicherung aktiver Tracks in Scene-String
# ------------------------------------------------------------
def store_calibrate_tracks_in_scene(context, track_names: List[str]) -> None:
    """
    Speichert aktive Kalibrierungs-Tracks in der Szene:
      calibrate_tracks        → reine Namen (LISTE)
      calibrate_tracks_uuid_map → UUID→Name Mapping (STRING)
    """
    scene = context.scene
    if not track_names:
        return

    try:
        # Alte Keys entfernen
        for key in ("calibrate_tracks", "calibrate_tracks_uuid_map"):
            if key in scene:
                del scene[key]

        clip = getattr(context.space_data, "clip", None)
        if not clip or not hasattr(clip, "tracking"):
            return

        # UUID Map erzeugen (nur im Scene-String, nicht im Track)
        import uuid as _uuid
        uuid_map: Dict[str, str] = {
            str(_uuid.uuid4()): name for name in track_names
        }

        # WICHTIG: Namen als LISTE speichern, nicht als String
        scene["calibrate_tracks"] = list(track_names)

        # Map bleibt String (JSON/Python-String)
        scene["calibrate_tracks_uuid_map"] = str(uuid_map)

        # logging removed

    except Exception as e:
        # logging removed
        pass

# =====================================================================
# Hauptoperator
# =====================================================================
class KAISERLICHTRACKER_OT_master_track_cycle(bpy.types.Operator):
    bl_idname = "kaiserlich_tracker.master_track_cycle"
    bl_label = "Track Cycle (Modal)"
    bl_description = "Performs a non-blocking forward tracking cycle for all selected markers"
    bl_options = {"REGISTER", "INTERNAL"}

    max_frames: bpy.props.IntProperty(  # type: ignore
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
            return {"CANCELLED"}

        # Start- und End-Frame
        self._start_frame = ph_get_start_frame(context)
        self._end_frame = get_end_frame(context)
        if self._end_frame < self._start_frame:
            self._end_frame = self._start_frame

        # Aktuelle Track-Selektion
        self._original_selected = collect_selected_track_names(context)
        if not self._original_selected:
            self.report({'WARNING'}, "No tracks selected.")
            return {"CANCELLED"}

        self._processing_names = list(self._original_selected)

        # Clip-Editor finden
        self._window, self._area, self._region, self._space = find_clip_editor_area(clip)
        if not self._window:
            self.report({'ERROR'}, "No CLIP_EDITOR area found.")
            return {"CANCELLED"}

        # Startframe setzen
        self._current_frame = max(self._start_frame, int(scene.frame_current))
        self._space.clip_user.frame_current = self._current_frame
        scene.frame_current = self._current_frame

        # Historien vorbereiten
        self._histories = {name: deque(maxlen=10) for name in self._processing_names}

        # Auswahl fixieren
        tracking = clip.tracking
        for tr in tracking.tracks:
            tr.select = (tr.name in self._original_selected)

        # --------------------------------------------------------
        # Referenz-Key bestimmen
        # --------------------------------------------------------
        self._active_ref_key = _resolve_reference_key(scene)

        # --------------------------------------------------------
        # NEU: Aktuell selektierte und aktive Tracks speichern
        # --------------------------------------------------------
        store_calibrate_tracks_in_scene(context, self._processing_names)
        # ============================================================
        # SNAPSHOT DER SELEKTIERTEN TRACKS SPEICHERN
        # ============================================================
        # Diese Liste dient später zur Überprüfung, ob nach Cleanup noch
        # mindestens ein ursprünglicher Marker übrig ist.
        self._snapshot_tracks = list(self._processing_names)
        # --------------------------------------------------------
        # Timer starten
        # --------------------------------------------------------
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    # --------------------------------------------------------
    # Modal Loop
    # --------------------------------------------------------

    def modal(self, context, event):
        if event.type == 'ESC':
            self._finish(context, cancelled=True)
            return {"CANCELLED"}

        if event.type != 'TIMER':
            return {"PASS_THROUGH"}

        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self._finish(context, cancelled=True)
            return {"CANCELLED"}

        tracking = clip.tracking

        # Historien aktualisieren
        for name in list(self._processing_names):
            tr = tracking.tracks.get(name)
            if not tr:
                continue
            mk = tr.markers.find_frame(self._current_frame)
            if mk and not mk.mute:
                self._histories[name].append((self._current_frame, mk.co[0], mk.co[1]))

        # -----------------------------------------------
        # 1) Vor jedem Calibration-Step sichern
        # -----------------------------------------------
        store_calibrate_tracks_in_scene(context, self._processing_names)
correct_motion_by_reference(context)
        # Danach würde marker_position_forward_calibration.py aufgerufen werden
        # (hier nur vorbereitend, damit calibrate_tracks aktuell ist)

        # -----------------------------------------------
        # 2) Adaptive Formel
        # -----------------------------------------------
        try:
            # Frames-per-track wird intern aus Scene gelesen
            get_from_selected_tracks(context)
            apply_formula_on_selected_tracks(context)
            scene = context.scene
            best_raw = scene.get("best_tracks")
            good_raw = scene.get("good_tracks")

            def _has_tracks(val):
                if not val:
                    return False
                if isinstance(val, str):
                    return bool(val.strip())
                return True

        except Exception:
            pass
        
        # -----------------------------------------------
        # 3) ACTIVE CALIBRATION STEP (mit good/best Referenz)
        # -----------------------------------------------
        try:
            scene = context.scene

            # Aktuelle Kalibrierungstracks
            calibrate_raw = scene.get("calibrate_tracks", "")
            if isinstance(calibrate_raw, str):
                calibrate_tracks = [
                    t.strip() for t in calibrate_raw.split(",") if t.strip()
                ]
            else:
                calibrate_tracks = []

            # Keine calibrate_tracks → kein Calibration Step
            if not calibrate_tracks:
                pass
            else:
                # -------------------------------------------
                # Referenz bestimmen: best_tracks > good_tracks
                # -------------------------------------------
                ref_tracks = []

                best_raw = scene.get("best_tracks", "")
                good_raw = scene.get("good_tracks", "")

                if isinstance(best_raw, str) and best_raw.strip():
                    ref_tracks = [t.strip() for t in best_raw.split(",") if t.strip()]
                elif isinstance(good_raw, str) and good_raw.strip():
                    ref_tracks = [t.strip() for t in good_raw.split(",") if t.strip()]

                # Ohne Referenzen → KEIN Calibration Step
                if not ref_tracks:
                    pass
                else:
                    # Frames definieren (vorher, aktuell, nachher)
                    f_a = self._current_frame
                    f_b = max(self._start_frame, f_a - 1)
                    f_c = min(self._end_frame, f_a + 1)

                    # Korrektur ausführen
                    correct_marker_positions(
                        scene,
                        ref_tracks,        # ← WICHTIG: good/best als Referenz
                        calibrate_tracks,  # ← zu korrigierende Tracks
                        f_a, f_b, f_c
                    )

        except Exception:
            pass


        # -----------------------------------------------
        # 4) adapt search size
        # -----------------------------------------------
        try:
            adapt_search_size_for_calibrate_tracks(context)
        except Exception:
            pass

        # -----------------------------------------------
        # 5) Tracking-Step
        # -----------------------------------------------
        success = track_markers_with_override(
            self._window, self._area, self._region, self._space,
            backwards=False, sequence=False
        )
        if not success:
            self._finish(context, cancelled=True)
            return {"CANCELLED"}

        # Frame fortsetzen
        scene = context.scene
        if self._space.clip_user.frame_current == self._current_frame:
            self._space.clip_user.frame_current += 1
        if self._space.clip_user.frame_current > self._end_frame:
            self._space.clip_user.frame_current = self._end_frame

        scene.frame_current = self._space.clip_user.frame_current
        self._current_frame = self._space.clip_user.frame_current
        self._frames_processed += 1

        # Aktive Tracks filtern
        self._processing_names, _ = filter_active_tracks_at_frame(
            context, self._processing_names, self._current_frame
        )

        # Abbruchbedingungen
        if self._current_frame >= self._end_frame:
            self._finish(context)
            return {"FINISHED"}

        if not self._processing_names:
            self._finish(context)
            return {"FINISHED"}

        if self.max_frames > 0 and self._frames_processed >= self.max_frames:
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

        # Ursprüngliche Auswahl wiederherstellen
        clip = getattr(context.space_data, "clip", None)
        if clip and hasattr(clip, "tracking"):
            for tr in clip.tracking.tracks:
                tr.select = (tr.name in self._original_selected)

        # Zurücksetzen
        try:
            reset_to_frame(context, self._start_frame)
        except Exception:
            pass

        # Progress aktualisieren
        try:
            from ...Helper.track_quality_metrics import compute_track_quality_metrics
            metrics = compute_track_quality_metrics(context)
            quality_percent = float(metrics.get("prozent", 100.0))
            context.scene.kaiserlich_quality_percent = f"{int(round(quality_percent))}%"
        except Exception:
            pass

        try:
            _, perc = compute_marker_progress(context.scene, update_ui=True)
            context.scene.kaiserlich_marker_progress = f"{int(round(perc))}%"
        except Exception:
            pass
        # ============================================================
        # NEU: Marker-Längenvalidierung (aktive Marker pro Track)
        # ============================================================
        try:
            scene = context.scene
            clip_obj = getattr(context.space_data, "clip", None)
            if clip_obj:
                from ...Helper.find_clip_editor_area import find_clip_editor_area
                from ...Helper.delete import delete_tracks_by_names

                window, area, region, space = find_clip_editor_area(clip_obj)
                if window and area and region and space:
                    with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                        tracking = clip_obj.tracking

                        # Mindestanzahl Frames pro Track
                        min_frames = 0
                        try:
                            if hasattr(scene, "kaiserlich_frames_per_track"):
                                val = getattr(scene, "kaiserlich_frames_per_track", None)
                            else:
                                val = scene.get("kaiserlich_frames_per_track", None)
                            if isinstance(val, (int, float)) and val > 0:
                                min_frames = int(val)
                        except Exception:
                            pass

                        flagged_names = []
                        deleted_info = []
                        kept_info = []

                        def _is_marker_disabled(track, marker) -> bool:
                            if getattr(track, "mute", False):
                                return True
                            if getattr(marker, "mute", False):
                                return True
                            try:
                                if "disabled" in marker and bool(marker["disabled"]):
                                    return True
                            except Exception:
                                pass
                            return False

                        if min_frames > 0:
                            for t in tracking.tracks:
                                try:
                                    active_frames = {
                                        m.frame for m in t.markers
                                        if hasattr(m, "frame") and not _is_marker_disabled(t, m)
                                    }
                                    active_length = len(active_frames)
                                    if active_length < min_frames:
                                        flagged_names.append(t.name)
                                        deleted_info.append((t.name, active_length))
                                    else:
                                        kept_info.append((t.name, active_length))
                                except Exception:
                                    pass
                        else:
                            for t in tracking.tracks:
                                try:
                                    active_frames = {
                                        m.frame for m in t.markers
                                        if hasattr(m, "frame") and not _is_marker_disabled(t, m)
                                    }
                                    kept_info.append((t.name, len(active_frames)))
                                except Exception:
                                    pass

                        if flagged_names:
                            delete_tracks_by_names(bpy.context, flagged_names)
                        # ----------------------------------------------------
                        # NEU: Snapshot-Überlebensprüfung
                        # ----------------------------------------------------
                        surviving_tracks = {
                            t.name for t in tracking.tracks
                            if t.name in getattr(self, "_snapshot_tracks", [])
                        }

                        if not surviving_tracks:
                            print("[TRACK_SNAPSHOT] ❌ Alle ursprünglichen Marker wurden entfernt.")
                            print(f"[TRACK_SNAPSHOT] Ursprünglich: {self._snapshot_tracks}")
                            print(f"[TRACK_SNAPSHOT] Überlebend:   (keiner)")

                            print("[TRACK_SNAPSHOT][RECOVERY] 🔄 Keine ursprünglichen Tracks überlebt → Search Size erweitern & Detect neu starten.")

                            # 1) Clean Reset auf Startframe
                            try:
                                reset_to_frame(context, self._start_frame)
                            except Exception:
                                pass

                            # 2) Search-Size Recovery anwenden
                            try:
                                update_default_sizes(context)
                                print("[TRACK_SNAPSHOT][RECOVERY] ✔ update_default_sizes ausgeführt.")
                            except Exception:
                                print("[TRACK_SNAPSHOT][RECOVERY] ❌ Fehlgeschlagen: update_default_sizes")

                            # 2b) Pattern-Size-Verlauf prüfen und ggf. Threshold anheben
                            try:
                                scene = context.scene
                                print("\n[TRACE][PATTERN_CHECK] ---- BEGIN STATS ----")

                                # 🟦 Clip sicher holen (unabhängig vom UI-Kontext)
                                clip_local = None
                                try:
                                    if hasattr(context.scene, "tracking"):
                                        tracking_obj = getattr(context.scene, "tracking", None)
                                        if tracking_obj and hasattr(tracking_obj, "active"):
                                            clip_local = getattr(tracking_obj, "active", None)
                                except Exception:
                                    clip_local = None

                                # 🟦 Default-Pattern-Size robust aus aktiven TrackingSettings ermitteln (inline ohne Funktion)
                                current_pz = None
                                tracking_settings = None
                                try:
                                    scr = getattr(context, "screen", None)
                                    if scr and hasattr(scr, "areas"):
                                        for _area in scr.areas:
                                            if _area.type == 'CLIP_EDITOR':
                                                for _space in _area.spaces:
                                                    if _space.type == 'CLIP_EDITOR' and getattr(_space, "clip", None):
                                                        _clip = _space.clip
                                                        if getattr(_clip, "tracking", None) and getattr(_clip.tracking, "settings", None):
                                                            tracking_settings = _clip.tracking.settings
                                                            break
                                                if tracking_settings:
                                                    break
                                    if not tracking_settings:
                                        _space_clip = getattr(getattr(context, "space_data", None), "clip", None)
                                        if _space_clip and getattr(_space_clip, "tracking", None) and getattr(_space_clip.tracking, "settings", None):
                                            tracking_settings = _space_clip.tracking.settings
                                    if not tracking_settings:
                                        _scene_clip = getattr(getattr(context, "scene", None), "clip", None)
                                        if _scene_clip and getattr(_scene_clip, "tracking", None) and getattr(_scene_clip.tracking, "settings", None):
                                            tracking_settings = _scene_clip.tracking.settings
                                except Exception:
                                    tracking_settings = None

                                try:
                                    if tracking_settings:
                                        raw_val = getattr(tracking_settings, "default_pattern_size", None)
                                        if isinstance(raw_val, int):
                                            if 5 <= raw_val <= 1000:
                                                current_pz = raw_val
                                            else:
                                                print(f"[TRACE][PATTERN_CHECK] out-of-range default_pattern_size={raw_val} (ignored)")
                                except Exception:
                                    current_pz = None

                                print(f"[TRACE][PATTERN_CHECK] current default_pattern_size = {current_pz}")

                                if current_pz is not None:
                                    try:
                                        last_pz = int(scene.get("kaiserlich_last_pattern_size_recovery", 0))
                                    except Exception:
                                        last_pz = 0
                                    print(f"[TRACE][PATTERN_CHECK] last saved reference = {last_pz}")

                                    # 🟥 FALL 1: Pattern fällt nach letztem Wert → Threshold hart erhöhen (×10)
                                    if current_pz < last_pz:
                                        # 🔧 Nur Marker-Multiplikator erhöhen
                                        mult = float(scene.get("kaiserlich_marker_multiplier", 2.0))
                                        new_mult = mult + 0.2
                                        scene["kaiserlich_marker_multiplier"] = new_mult
                                
                                        print(f"[TRACE][PATTERN_CHECK] 🔻 Pattern DROP detected! Marker multiplier raised "
                                              f"{mult} ➜ {new_mult} (+0.1)")

                                        # 👉 Immer den aktuellen Pattern-Size als Referenz speichern
                                        scene["kaiserlich_last_pattern_size_recovery"] = int(current_pz)
                                        print(f"[TRACE][PATTERN_CHECK] 💾 pattern reference updated → {current_pz}")
                                        print("[TRACE][PATTERN_CHECK] ---- END STATS ----\n")
                                        # WICHTIG: Keine TR-Änderung, aber Recovery weiterführen
                                        # Kein StopIteration, normale Recovery-Kette

                                    # Kein Drop (gleich oder größer) → trotzdem immer Referenz aktualisieren
                                    scene["kaiserlich_last_pattern_size_recovery"] = int(current_pz)
                                    print(f"[TRACE][PATTERN_CHECK] 💾 pattern reference updated → {current_pz}")

                                else:
                                    print("[TRACE][PATTERN_CHECK] ❌ current_pz could not be read → No threshold change")

                                print("[TRACE][PATTERN_CHECK] ---- END STATS ----\n")
                            # ⚠ StopIteration = gezieltes Abbrechen nach Threshold-Boost,
                            # kein Fehler, Recovery läuft normal weiter
                            except StopIteration:
                                pass

                            # ⚠ Alle anderen Fehler melden
                            except Exception as e:
                                print(f"[TRACK_SNAPSHOT][RECOVERY] ⚠ Pattern-Size-Check fehlgeschlagen: {e}")
                            # 3) Weiterleitung an den Master Detect-Adapt Operator
                            try:
                                # 🔐 Threshold-Fix: neuen Wert sicher in bootstrap_params speichern
                                try:
                                    params = scene.get("bootstrap_params", {})
                                    if isinstance(params, dict):
                                        # ergibt sich aus Pattern-Check (base_tr wurde überschrieben)
                                        base_tr = float(params.get('tr', 0.0001))
                                        # bei Bedarf könnte hier weitere Logik greifen → aber wichtig ist: schreiben!
                                        scene["bootstrap_params"] = dict(params)
                                        print(f"[THRESHOLD][STORE] tr={base_tr}")
                                except Exception as e:
                                    print(f"[THRESHOLD][STORE] ⚠ Speichern fehlgeschlagen: {e}")
        
                                bpy.ops.kaiserlich_tracker.master_detect_adapt('INVOKE_DEFAULT')
                                print("[TRACK_SNAPSHOT][RECOVERY] 🚀 Weiterleitung → master_detect_adapt_operator")
                                # Logging aktuell eingesetzter Schwellenwerte
                                try:
                                    p = context.scene.get("bootstrap_params", {})
                                    if isinstance(p, dict) and "tr" in p:
                                        print(f"[THRESHOLD][HANDOVER] tr={p.get('tr')} (handover to detect_adapt)")
                                except Exception:
                                    pass
                                # ----------------------------------------------------
                                # HARD EXIT: Dieser Operator muss komplett beendet werden
                                # keine Weitergabe an master_cycle_operator!
                                # ----------------------------------------------------
                                self._timer = None
                                return {'FINISHED'}
                            except Exception:
                                print("[TRACK_SNAPSHOT][RECOVERY] ❌ Übergabe fehlgeschlagen: master_detect_adapt_operator")

                                return {'CANCELLED'}  # Sicherheitsfallback
                        else:
                            print(f"[TRACK_SNAPSHOT] ✔ Überlebende ursprüngliche Tracks: {', '.join(surviving_tracks)}")

                        try:
                            print(f"[TRACK_LENGTH_VALIDATION] min_frames={min_frames} "
                                  f"deleted={len(deleted_info)} kept={len(kept_info)} (active frames only)")
                            if deleted_info:
                                print("  Deleted Tracks:", ", ".join(f"{n}:{l}" for n, l in deleted_info))
                            else:
                                print("  Deleted Tracks: None")
                            if kept_info:
                                print("  Kept Tracks:", ", ".join(f"{n}:{l}" for n, l in kept_info))
                            else:
                                print("  Kept Tracks: None")
                        except Exception:
                            pass
        except Exception:
            pass
        # Folge-Operator starten
        if not cancelled:
            try:
                # ----------------------------------------------------
                # 🌐 Forward-Cycle erfolgreich → Reset Pattern-Peak
                # ----------------------------------------------------
                scene = context.scene
                if "kaiserlich_last_pattern_size_recovery" in scene:
                    try:
                        del scene["kaiserlich_last_pattern_size_recovery"]
                        print("[TRACE][PATTERN_CHECK] 🔄 Reset last_pz (successful cycle)")
                    except Exception:
                        pass
                # ----------------------------------------------------
                # 🔁 Marker-Multiplier vor Übergabe zurücksetzen
                # ----------------------------------------------------
                try:
                    prev_mult = float(scene.get("kaiserlich_marker_multiplier", 2.0))
                    scene["kaiserlich_marker_multiplier"] = 2.0
                    print(f"[TRACE][MULTIPLIER] 🔄 Reset multiplier {prev_mult} ➜ 2.0 (handover)")
                except Exception:
                    print("[TRACE][MULTIPLIER] ⚠ Multiplier reset failed")
                
                bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')
            except Exception:
                pass


# ------------------------------------------------------------
# Register
# ------------------------------------------------------------
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_track_cycle)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_track_cycle)
