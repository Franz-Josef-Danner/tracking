import bpy
from bpy.types import Operator, Context
from dataclasses import dataclass, field
from typing import Set

from ...Helper.snapshot import snapshot_active_markers
from ...Helper.detect_adapt_helper import run_detect_adapt
from ...Helper.util_clip import get_active_clip
from ...Helper.playhead_helper import reset_to_frame
from ...Helper.filter_active_tracks import filter_active_tracks_at_frame
from ...Helper.formula_helper import apply_formula_on_selected_tracks
from ...Helper.track_length_helper import get_total_track_length
from ...Helper.delete import delete_tracks_by_names
from ...Helper.get_clip_context import get_clip_context


@dataclass
class DeepTestState:
    """Kapselt alle Laufzeitdaten des Deep-Test-Prozesses."""
    counter: int = 0
    stop_flag: bool = False

    basis: float = 0.0
    vergleichswert: float = 0.0
    start: float = 0.0
    ende: float = 0.0
    stufe: float = 0.0
    next_val: float = 0.0

    alte_tracker: Set[str] = field(default_factory=set)
    neu_tracker: Set[str] = field(default_factory=set)
    alle_tracker: Set[str] = field(default_factory=set)


class KAISERLICHTRACKER_OT_deep_test_operator(Operator):
    bl_idname = "kaiserlichtracker.deep_test"
    bl_label = "Kaiserlich Tracker: Deep Test"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: Context):
        self.state = DeepTestState()
        self.state.next_val = 0.0
        self.state.stop_flag = False

        while True:
            self._set_threshold(context)

            # Haupt-Loop über alle Threshold-Stufen
            while not self.state.stop_flag:
                self._set_step_threshold(context)
                if self.state.stop_flag:
                    break  # einziger Abbruchpunkt im Prozess

                # --- Tracking-Testzyklus ---
                self.state.next_val = 1.0
                self._set_step_threshold(context)
                self._track(context)
                self.state.basis = self.state.vergleichswert

                self.state.start = self.state.next_val
                self.state.next_val = 0.00001
                self._set_step_threshold(context)
                self.state.ende = self.state.next_val
                self._track(context)

                if self.state.vergleichswert <= self.state.basis:
                    self.state.stufe += 1
                    continue

                self.state.stufe = abs(self.state.start - self.state.ende) / 2.0
                self.state.next_val = self.state.next_val + self.state.stufe
                self._set_step_threshold(context)
                self._track(context)

                if self.state.vergleichswert < self.state.basis:
                    self._minus_thresh(context)
                else:
                    if self.state.vergleichswert > self.state.basis:
                        self.state.basis = self.state.vergleichswert
                        self._plus_thresh(context)
                    else:
                        self._plus_thresh(context)

            print("[DeepTest] ✅ Alle Stufen abgeschlossen — Prozessende.")
            return {'FINISHED'}

    def _set_threshold(self, context: Context) -> None:
        scene = context.scene
        # Baseline: alles auf 1 zurücksetzen
        scene.kaiserlich_rot_thresh_x = 1.0
        scene.kaiserlich_rot_thresh_y = 1.0
        scene.kaiserlich_scale_thresh_min = 1.0
        scene.kaiserlich_scale_thresh_max = 1.0
        scene.kaiserlich_rot_scale_thresh_rot = 1.0
        scene.kaiserlich_rot_scale_thresh_scale = 1.0
        scene.kaiserlich_perspective_thresh = 1.0

    def _set_step_threshold(self, context: Context) -> None:
        clip = get_active_clip()
        scene = context.scene

        if self.state.stufe == 0:
            # rot_xy
            if clip:
                width, height = clip.size
                # y an Seitenverhältnis koppeln, gekappt auf 1.0
                y_val = min(1.0, self.state.next_val * (height / width if width else 1.0))
                scene.kaiserlich_rot_thresh_x = float(self.state.next_val)
                scene.kaiserlich_rot_thresh_y = float(y_val)
            return

        elif self.state.stufe == 1:
            # scale_min/max
            scene.kaiserlich_scale_thresh_min = float(self.state.next_val)
            scene.kaiserlich_scale_thresh_max = float(min(1.0, self.state.next_val * 1.1))
            return

        elif self.state.stufe == 2:
            # rot_scale: rot
            scene.kaiserlich_rot_scale_thresh_rot = float(self.state.next_val)
            scene.kaiserlich_rot_scale_thresh_scale = 0.0
            return

        elif self.state.stufe == 3:
            # rot_scale: scale
            scene.kaiserlich_rot_scale_thresh_rot = 0.0
            scene.kaiserlich_rot_scale_thresh_scale = float(self.state.next_val)
            return

        elif self.state.stufe == 4:
            # perspective
            scene.kaiserlich_perspective_thresh = float(self.state.next_val)
            return

        elif self.state.stufe >= 5:
            self.state.stop_flag = True
            return

    def _track(self, context: Context) -> None:
        # Vorher/Nachher-Snapshot
        self.state.alte_tracker = snapshot_active_markers(context)
        run_detect_adapt(context)
        self.state.alle_tracker = snapshot_active_markers(context)
        self.state.neu_tracker = set(self.state.alle_tracker) - set(self.state.alte_tracker)

        # Vorwärts-Tracking mit Grenzen
        self._track_forward_with_limits(context)

        # Metrik berechnen
        scene = context.scene
        self.state.vergleichswert = get_total_track_length(
            context,
            start_frame=scene.frame_start,
            include_names=self.state.neu_tracker
        )

        # Aufräumen: nur die neu erzeugten wieder entfernen
        if self.state.neu_tracker:
            delete_tracks_by_names(context, include_names=self.state.neu_tracker)

    def _plus_thresh(self, context: Context) -> None:
        while True:
            self.state.ende = self.state.next_val
            step = abs(self.state.start - self.state.ende) / 2.0
            if step > 0.0001:
                self.state.next_val = self.state.next_val + step
                self._set_step_threshold(context)
                self._track(context)
                if self.state.vergleichswert >= self.state.basis:
                    if self.state.vergleichswert > self.state.basis:
                        self.state.basis = self.state.vergleichswert
                        continue
                    else:
                        continue
                else:
                    self._minus_thresh(context)
            else:
                self.state.stufe += 1
                # neue Stufe starten
                return

    def _minus_thresh(self, context: Context) -> None:
        while True:
            self.state.start = self.state.next_val
            step = abs(self.state.start - self.state.ende) / 2.0
            if step > 0.0001:
                self.state.next_val = self.state.next_val - step
                self._set_step_threshold(context)
                self._track(context)
                if self.state.vergleichswert < self.state.basis:
                    continue
                else:
                    if self.state.vergleichswert > self.state.basis:
                        self.state.basis = self.state.vergleichswert
                        self._plus_thresh(context)
                    else:
                        self._plus_thresh(context)
            else:
                self.state.stufe += 1
                # neue Stufe starten
                return

    def _track_forward_with_limits(
        self,
        context: Context,
        *,
        max_frames: int = 50,
        min_distance_to_end: int = 50,
        log: bool = True
    ) -> int:
        """
        Führt ein begrenztes Vorwärts-Tracking ab der aktuellen Playhead-Position aus.

        Rückgabe:
            Gesamtzahl der getrackten Frames (oder 0 bei Abbruch)
        """
        scene = context.scene
        clip = get_active_clip()
        if not clip or not getattr(clip, "tracking", None):
            if log:
                print("[TrackForward] ❌ Kein aktiver Clip gefunden.")
            return 0

        end_frame = int(scene.frame_end)
        current_frame = int(scene.frame_current)
        remaining = end_frame - current_frame

        # --- Startposition prüfen / korrigieren ---
        if remaining < min_distance_to_end:
            new_start = max(scene.frame_start, end_frame - min_distance_to_end)
            if log:
                print(f"[TrackForward] ⚠️ Weniger als {min_distance_to_end} Frames verbleiben "
                      f"({remaining}) → Starte bei Frame {new_start}.")
            reset_to_frame(context, new_start)
            scene.frame_current = new_start
            current_frame = new_start
        else:
            if log:
                print(f"[TrackForward] ✅ Genug Frames verbleiben ({remaining}). Starte bei {current_frame}.")

        # --- aktive Tracks ermitteln (selektierte) ---
        tracking = clip.tracking
        active_tracks = [t.name for t in tracking.tracks if t.select]
        if not active_tracks:
            if log:
                print("[TrackForward] ⚠️ Keine selektierten Tracks zum Tracken gefunden.")
            return 0

        # --- Kontext holen ---
        ctx_override = get_clip_context()
        if not ctx_override:
            print("[TrackForward] ❌ Kein gültiger Clip-Kontext verfügbar – Abbruch.")
            return 0

        # --- Tracking-Schleife ---
        frames_tracked = 0
        for _ in range(max_frames):
            if current_frame >= end_frame:
                if log:
                    print("[TrackForward] ⏹️ Szenenende erreicht.")
                break

            active_tracks, _dropped = filter_active_tracks_at_frame(context, active_tracks, current_frame)
            if not active_tracks:
                if log:
                    print("[TrackForward] ⏹️ Keine aktiven Tracks mehr – Tracking beendet.")
                break

            try:
                # leichte Anpassungen vorher, wenn konfiguriert
                apply_formula_on_selected_tracks(context, max_frames=5)
            except Exception as ex:
                if log:
                    print(f"[TrackForward] ⚠️ Formel-Fehler: {ex!r}")

            # --- Tracking via Override ---
            with bpy.context.temp_override(**ctx_override):
                result = bpy.ops.clip.track_markers('EXEC_DEFAULT', backwards=False)
            if 'CANCELLED' in str(result):
                if log:
                    print("[TrackForward] ⚠️ Tracking fehlgeschlagen – Abbruch.")
                break

            frames_tracked += 1
            current_frame += 1
            scene.frame_current = current_frame
            # UI-best effort
            try:
                context.space_data.clip_user.frame_current = current_frame
            except Exception:
                pass

        total_len = get_total_track_length(context, start_frame=scene.frame_start, include_names=active_tracks)
        if log:
            print(f"[TrackForward] ✅ Tracking abgeschlossen – {frames_tracked} Frames getrackt, "
                  f"Gesamtlänge {total_len}.")

        return frames_tracked
