# Operator/Master/master_track_operator_backwards.py
import bpy
from typing import List, Tuple, Dict, Deque
from collections import deque

# ------------------------------------------------------------
# Helper-Importe
# ------------------------------------------------------------
from ...Helper.formula_helper import apply_formula_on_selected_tracks
from ...Helper.playhead_helper import reset_to_frame
from ...Helper.scene import get_end_frame, get_start_frame as scene_get_start_frame
from ...Helper.find_clip_editor_area import find_clip_editor_area
from ...Helper.selection_helper import collect_selected_track_names
from ...Helper.filter_active_tracks import filter_active_tracks_at_frame
from ...Helper.track_markers_helper import track_markers_with_override
from ..Helper.frame_track_progress import init_marker_progress, update_marker_progress


# ------------------------------------------------------------
# Operator
# ------------------------------------------------------------

class KAISERLICHTRACKER_OT_master_track_cycle_backwards(bpy.types.Operator):
    """Frame-by-Frame Tracking rückwärts mit sichtbarem Fortschritt (nicht blockierend)."""
    bl_idname = "kaiserlich_tracker.master_track_cycle_backwards"
    bl_label = "Track Zyklus Rückwärts (Modal)"
    bl_description = (
        "Trackt selektierte Marker frameweise rückwärts mit Timer – UI bleibt responsiv, "
        "Playhead und Markerupdates sichtbar."
    )
    bl_options = {"REGISTER", "INTERNAL"}

    max_frames: bpy.props.IntProperty(  # type: ignore
        name="Max Frames",
        default=0,
        min=0,
        soft_max=100000,
        description="Sicherheitslimit (0 = kein Limit)"
    )

    _timer = None
    _processing_names: List[str]
    _original_selected: List[str]
    _histories: Dict[str, Deque[Tuple[int, float, float]]]
    _window = None
    _area = None
    _region = None
    _space = None
    _start_frame = 0     # Szenenstart
    _end_frame = 0       # Szenenende
    _reset_frame = 0     # ursprünglicher Playhead
    _current_frame = 0   # Laufzeit-Playhead
    _frames_processed = 0

    # --------------------------------------------------------
    # Initialisierung
    # --------------------------------------------------------

    def execute(self, context):
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'ERROR'}, "Kein aktiver Clip.")
            return {"CANCELLED"}

        # ------------------------------------------
        # Szenen-Start und -Ende bestimmen
        # ------------------------------------------
        # _start_frame = Szenenanfang (nicht Playhead-Position)
        self._start_frame = scene_get_start_frame(context)
        self._end_frame = get_end_frame(context)
        if self._end_frame < self._start_frame:
            self._end_frame = self._start_frame

        # Selektion erfassen
        self._original_selected = collect_selected_track_names(context)
        if not self._original_selected:
            self.report({'WARNING'}, "Keine Tracks selektiert.")
            return {"CANCELLED"}

        self._processing_names = list(self._original_selected)

        # CLIP_EDITOR-Bereich holen
        self._window, self._area, self._region, self._space = find_clip_editor_area(clip)
        if not self._window:
            self.report({'ERROR'}, "Keine CLIP_EDITOR Area gefunden.")
            return {"CANCELLED"}

        # ------------------------------------------
        # Playhead-Startposition bestimmen
        # ------------------------------------------
        # Ursprüngliche Playhead-Position merken (für Reset)
        self._reset_frame = int(scene.frame_current)

        # Initialer Laufzeit-Frame = aktuelle Playhead-Position, auf Range geklemmt
        scene_current = self._reset_frame
        if scene_current < self._start_frame:
            self._current_frame = self._start_frame
        elif scene_current > self._end_frame:
            self._current_frame = self._end_frame
        else:
            self._current_frame = scene_current

        # Playhead setzen
        self._space.clip_user.frame_current = self._current_frame
        scene.frame_current = self._current_frame

        print(f"[Kaiserlich Tracker][ModalBackwards] Init start={self._start_frame}, "
              f"end={self._end_frame}, current={self._current_frame}")

        # Historien initialisieren
        self._histories = {name: deque(maxlen=10) for name in self._processing_names}
        # Fortschritts-Map initialisieren (neue inkrementelle Methode)
        try:
            init_marker_progress(scene)
        except Exception as e:
            print(f"[Kaiserlich Tracker][Init] ⚠️ Fortschritts-Init fehlgeschlagen: {e}")

        # Selektion fixieren
        tracking = clip.tracking
        for tr in tracking.tracks:
            tr.select = (tr.name in self._original_selected)

        # Timer aktivieren
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.25, window=context.window)
        wm.modal_handler_add(self)

        print("[Kaiserlich Tracker][ModalBackwards] Tracking-Zyklus rückwärts gestartet...")
        return {"RUNNING_MODAL"}

    # --------------------------------------------------------
    # Modal-Loop
    # --------------------------------------------------------

    def modal(self, context, event):
        # ESC = Abbruch
        if event.type == 'ESC':
            print("[Kaiserlich Tracker][ModalBackwards] ❌ Vom Benutzer abgebrochen.")
            self._finish(context, cancelled=True)
            return {"CANCELLED"}

        # Nur TIMER-Events verarbeiten
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
            if mk:
                self._histories[name].append((self._current_frame, mk.co[0], mk.co[1]))

        # Formel anwenden (z. B. für Optimierungen)
        try:
            apply_formula_on_selected_tracks(context, max_frames=5)
        except Exception as e:
            print(f"[Kaiserlich Tracker][ModalBackwards] ⚠️ apply_formula Fehler: {e}")

        # Fortschritt der Markerberechnung updaten (UI-sicher)
        try:
            _, perc = compute_marker_progress(context.scene, update_ui=True)
            context.scene.kaiserlich_marker_progress = f"{int(round(perc))}%"
        except Exception as e:
            print(f"[Kaiserlich Tracker][ProgressBackwards] ⚠️ Fortschrittsberechnung fehlgeschlagen: {e}")

        # Tracking-Schritt über Helper (rückwärts)
        success = track_markers_with_override(
            self._window, self._area, self._region, self._space,
            backwards=True, sequence=False
        )

        if not success:
            print("[Kaiserlich Tracker][ModalBackwards] ⚠️ Tracking-Fehler, breche ab.")
            self._finish(context, cancelled=True)
            return {"CANCELLED"}

        # Aktive Tracks prüfen
        self._processing_names, _ = filter_active_tracks_at_frame(
            context, self._processing_names, self._current_frame
        )

        # ----------------------------------------------------
        # Beendigungskriterien (vor Step prüfen)
        # ----------------------------------------------------
        if not self._processing_names:
            print("[Kaiserlich Tracker][ModalBackwards] ✅ Keine aktiven Tracks mehr.")
            self._finish(context)
            return {"FINISHED"}

        if self.max_frames > 0 and self._frames_processed >= self.max_frames:
            print("[Kaiserlich Tracker][ModalBackwards] ⚠️ Sicherheitslimit erreicht.")
            self._finish(context)
            return {"FINISHED"}

        # ----------------------------------------------------
        # Frame rückwärts fortsetzen (analog zu Forward)
        # ----------------------------------------------------
        scene = context.scene

        # Wenn der Helper den Frame NICHT verändert hat, mache den Step selbst
        if self._space.clip_user.frame_current == self._current_frame:
            self._space.clip_user.frame_current -= 1

        # Clamp: nicht unter Szenenstart fallen
        if self._space.clip_user.frame_current < self._start_frame:
            self._space.clip_user.frame_current = self._start_frame

        # Sichtbar übernehmen
        scene.frame_current = self._space.clip_user.frame_current
        self._current_frame = self._space.clip_user.frame_current
        self._frames_processed += 1

        # Nach dem Step: Szenenstart erreicht?
        # (<= bedeutet: beim ersten Frame unterhalb/gleich Start stoppen)
        if self._current_frame <= self._start_frame:
            print("[Kaiserlich Tracker][ModalBackwards] ✅ Szenenanfang erreicht.")
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

        # Ursprüngliche Selektion wiederherstellen
        clip = getattr(context.space_data, "clip", None)
        if clip and hasattr(clip, "tracking"):
            for tr in clip.tracking.tracks:
                tr.select = (tr.name in self._original_selected)

        # Playhead auf ursprüngliche Position zurücksetzen
        try:
            reset_to_frame(context, self._reset_frame)
        except Exception as e:
            print(f"[Kaiserlich Tracker][ModalBackwards] ⚠️ Fehler beim Frame-Reset: {e}")

        print(
            "[Kaiserlich Tracker][ModalBackwards] ✅ Rückwärts-Zyklus beendet."
            if not cancelled else
            "[Kaiserlich Tracker][ModalBackwards] ❌ Rückwärts-Zyklus abgebrochen."
        )

        # Letzter Fortschritts-Refresh bei Abschluss
        try:
            _, perc = compute_marker_progress(context.scene, update_ui=True)
            context.scene.kaiserlich_marker_progress = f"{int(round(perc))}%"
        except Exception as e:
            print(f"[Kaiserlich Tracker][ProgressBackwards] ⚠️ Abschluss-Update fehlgeschlagen: {e}")

        # --------------------------------------------------------
        # Kontextübergabe an Forward-Tracking (Master Track Cycle)
        # --------------------------------------------------------
        if not cancelled:
            try:
                print("[Kaiserlich Tracker][ModalBackwards] ➜ Übergabe an Master Track Cycle (vorwärts)...")

                # Kontext sichern
                clip = getattr(context.space_data, "clip", None)
                if clip is None:
                    print("[Kaiserlich Tracker][ModalBackwards] ⚠️ Kein aktiver Clip – Übergabe übersprungen.")
                    return

                # Clip-Editor-Bereich wiederfinden
                window, area, region, space = find_clip_editor_area(clip)
                if not window:
                    print("[Kaiserlich Tracker][ModalBackwards] ⚠️ Keine CLIP_EDITOR Area – Übergabe übersprungen.")
                    return

                # Neuen Kontext mit temp_override nutzen (Blender 4.x+ API)
                with context.temp_override(window=window, area=area, region=region, space_data=space):
                    bpy.ops.kaiserlich_tracker.master_track_cycle()

                print("[Kaiserlich Tracker][ModalBackwards] ✅ Übergabe erfolgreich gestartet (temp_override).")
            except Exception as e:
                print(f"[Kaiserlich Tracker][ModalBackwards] ❌ Fehler bei Übergabe via temp_override: {e}")

# ------------------------------------------------------------
# Register
# ------------------------------------------------------------

def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_track_cycle_backwards)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_track_cycle_backwards)
