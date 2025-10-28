# Operator/track_operator.py
import bpy
from typing import List, Tuple, Dict, Deque, Optional
from collections import deque
import math

# ------------------------------------------------------------
# Helper-Importe
# ------------------------------------------------------------
from ..Helper.formula_helper import apply_formula_on_selected_tracks
from ..Helper.playhead_helper import get_start_frame as ph_get_start_frame, reset_to_frame
from ..Helper.scene import get_end_frame
from ..Helper.find_clip_editor_area import find_clip_editor_area
from ..Helper.selection_helper import collect_selected_track_names
from ..Helper.filter_active_tracks import filter_active_tracks_at_frame
from ..Helper.track_markers_helper import track_markers_with_override
from ..Helper.motion_model_controller import (
    quick_stats_from_track,
    apply_adaptive_models_for_tracks,
)

# ------------------------------------------------------------
# Operator
# ------------------------------------------------------------

class KAISERLICHTRACKER_OT_track_cycle(bpy.types.Operator):
    """Frame-by-Frame Tracking mit sichtbarem Fortschritt (nicht blockierend)."""
    bl_idname = "kaiserlich_tracker.track_cycle"
    bl_label = "Track Zyklus (Modal)"
    bl_description = (
        "Trackt selektierte Marker frameweise mit Timer – UI bleibt responsiv, "
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

    use_adaptive_models: bpy.props.BoolProperty(  # type: ignore
        name="Adaptive Motion-Modelle",
        default=True,
        description="Motion-Model je Track adaptiv anpassen"
    )

    adapt_phase: bpy.props.EnumProperty(  # type: ignore
        name="Adaptionsphase",
        items=[
            ("PRE",  "Vor Tracking",   "Anpassung VOR dem Tracking-Schritt"),
            ("POST", "Nach Tracking",  "Anpassung NACH dem Tracking-Schritt"),
            ("BOTH", "Vor & Nach",     "Beide Phasen"),
        ],
        default="POST",
        description="Zeitpunkt der Modellanpassung"
    )

    _timer = None
    _context_cache = None
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
    _clip = None

    # --------------------------------------------------------
    # Initialisierung
    # --------------------------------------------------------

    def execute(self, context):
        scene = context.scene
        self._clip = getattr(context.space_data, "clip", None)
        if self._clip is None:
            self.report({'ERROR'}, "Kein aktiver Clip.")
            return {"CANCELLED"}

        # Start- und Endframes holen
        self._start_frame = ph_get_start_frame(context)
        self._end_frame = get_end_frame(context)
        if self._end_frame < self._start_frame:
            self._end_frame = self._start_frame

        # Selektion erfassen
        self._original_selected = collect_selected_track_names(context)
        if not self._original_selected:
            self.report({'WARNING'}, "Keine Tracks selektiert.")
            return {"CANCELLED"}

        self._processing_names = list(self._original_selected)

        # CLIP_EDITOR Bereich holen
        self._window, self._area, self._region, self._space = find_clip_editor_area(self._clip)
        if not self._window:
            self.report({'ERROR'}, "Keine CLIP_EDITOR Area gefunden.")
            return {"CANCELLED"}

        # Startframe setzen
        self._current_frame = max(self._start_frame, int(scene.frame_current))
        self._space.clip_user.frame_current = self._current_frame
        scene.frame_current = self._current_frame

        # Historien initialisieren
        self._histories = {name: deque(maxlen=10) for name in self._processing_names}

        # Selektion fixieren
        tracking = self._clip.tracking
        for tr in tracking.tracks:
            tr.select = (tr.name in self._original_selected)

        # Timer aktivieren
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)

        print("[Kaiserlich Tracker][Modal] Tracking-Zyklus gestartet...")
        return {"RUNNING_MODAL"}

    # --------------------------------------------------------
    # Metriken
    # --------------------------------------------------------

    def _rich_stats_from_track(self, tr: bpy.types.MovieTrackingTrack) -> Dict[str, Optional[float]]:
        """
        Liefert brauchbare Delta-Werte (Scale/Rot) aus pattern_corners zwischen
        aktuellem und vorherigem Frame. Fällt robust auf quick_stats zurück.
        """
        scene = bpy.context.scene
        curr = tr.markers.find_frame(self._current_frame)
        prev = tr.markers.find_frame(self._current_frame - 1)

        # Fallback, wenn Marker nicht existiert
        if not curr or not prev:
            return quick_stats_from_track(tr)

        # Pattern-Ecken lesen (4x2)
        try:
            pc_curr = curr.pattern_corners
            pc_prev = prev.pattern_corners

            # Größe via Diagonale (0-2)
            def diag_len(pcs):
                return ((pcs[0][0]-pcs[2][0])**2 + (pcs[0][1]-pcs[2][1])**2) ** 0.5

            # Winkel via Kante (0->1)
            def edge_angle_deg(pcs):
                return math.degrees(math.atan2(pcs[1][1]-pcs[0][1],
                                               pcs[1][0]-pcs[0][0]))

            size_prev = diag_len(pc_prev)
            size_curr = diag_len(pc_curr)
            if size_prev > 1e-8:
                ds = (size_curr / size_prev) - 1.0
            else:
                ds = 0.0

            ang_prev = edge_angle_deg(pc_prev)
            ang_curr = edge_angle_deg(pc_curr)
            dr = ang_curr - ang_prev

            # Error nur als Platzhalter, da average_error ohne Solve wenig aussagt
            try:
                err = float(getattr(tr, "average_error", None))
            except Exception:
                err = None

            # Korrelation ist in der API nicht als Markerfeld standardisiert verfügbar;
            # wir lassen sie hier None. (Optional: eigene NCC-Messung implementieren)
            corr = None

            # Survival wird im Controller verwaltet, kann hier None bleiben
            return {
                "error": err,
                "corr": corr,
                "delta_scale": ds,
                "delta_rot": dr,
                "survival": None,
            }
        except Exception:
            # Defensive Rückfallebene
            return quick_stats_from_track(tr)

    def _collect_active_subset_and_stats(self, context, tracking) -> Tuple[List[bpy.types.MovieTrackingTrack], Dict[str, Dict[str, Optional[float]]]]:
        active_names, _ = filter_active_tracks_at_frame(
            context, self._processing_names, self._current_frame
        )
        subset = [tracking.tracks.get(nm) for nm in active_names if tracking.tracks.get(nm)]
        per_stats = {tr.name: self._rich_stats_from_track(tr) for tr in subset}
        return subset, per_stats

    # --------------------------------------------------------
    # Modal-Loop
    # --------------------------------------------------------

    def modal(self, context, event):
        # ESC = Abbruch
        if event.type == 'ESC':
            print("[Kaiserlich Tracker][Modal] ❌ Vom Benutzer abgebrochen.")
            self._finish(context, cancelled=True)
            return {"CANCELLED"}

        # Nur TIMER-Events verarbeiten
        if event.type != 'TIMER':
            return {"PASS_THROUGH"}

        # Clip prüfen (konservativ)
        clip = self._clip or getattr(context.space_data, "clip", None)
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

        # ----------------------------------------------------
        # Adaptive PRE
        # ----------------------------------------------------
        if self.use_adaptive_models and self.adapt_phase in {"PRE", "BOTH"}:
            try:
                subset, per_stats = self._collect_active_subset_and_stats(context, tracking)
                if subset:
                    apply_adaptive_models_for_tracks(
                        subset, per_stats, scene=context.scene,
                        frame_current=self._current_frame, log=True, clip=clip
                    )
            except Exception as e:
                print(f"[Kaiserlich Tracker][Modal] ⚠️ Adaptive-Model-Update (PRE) Fehler: {e}")

        # Formel anwenden (z. B. für Optimierungen)
        try:
            apply_formula_on_selected_tracks(context, max_frames=5)
        except Exception as e:
            print(f"[Kaiserlich Tracker][Modal] ⚠️ apply_formula Fehler: {e}")

        # Tracking-Schritt über Helper
        success = track_markers_with_override(
            self._window, self._area, self._region, self._space,
            backwards=False, sequence=False
        )

        if not success:
            print("[Kaiserlich Tracker][Modal] ⚠️ Tracking-Fehler, breche ab.")
            self._finish(context, cancelled=True)
            return {"CANCELLED"}

        # ----------------------------------------------------
        # Adaptive POST (empfohlen)
        # ----------------------------------------------------
        if self.use_adaptive_models and self.adapt_phase in {"POST", "BOTH"}:
            try:
                subset, per_stats = self._collect_active_subset_and_stats(context, tracking)
                if subset:
                    apply_adaptive_models_for_tracks(
                        subset, per_stats, scene=context.scene,
                        frame_current=self._current_frame, log=True, clip=clip
                    )
            except Exception as e:
                print(f"[Kaiserlich Tracker][Modal] ⚠️ Adaptive-Model-Update (POST) Fehler: {e}")

        # Frame fortsetzen
        scene = context.scene
        if self._space.clip_user.frame_current == self._current_frame:
            self._space.clip_user.frame_current += 1
        if self._space.clip_user.frame_current > self._end_frame:
            self._space.clip_user.frame_current = self._end_frame

        scene.frame_current = self._space.clip_user.frame_current
        self._current_frame = self._space.clip_user.frame_current
        self._frames_processed += 1

        # Aktive Tracks prüfen
        self._processing_names, _ = filter_active_tracks_at_frame(
            context, self._processing_names, self._current_frame
        )

        # ----------------------------------------------------
        # Beendigungskriterien
        # ----------------------------------------------------
        if self._current_frame >= self._end_frame:
            print("[Kaiserlich Tracker][Modal] ✅ Szenenende erreicht.")
            self._finish(context)
            return {"FINISHED"}

        if not self._processing_names:
            print("[Kaiserlich Tracker][Modal] ✅ Keine aktiven Tracks mehr.")
            self._finish(context)
            return {"FINISHED"}

        if self.max_frames > 0 and self._frames_processed >= self.max_frames:
            print("[Kaiserlich Tracker][Modal] ⚠️ Sicherheitslimit erreicht.")
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
        clip = self._clip or getattr(context.space_data, "clip", None)
        if clip and hasattr(clip, "tracking"):
            for tr in clip.tracking.tracks:
                tr.select = (tr.name in self._original_selected)

        try:
            reset_to_frame(context, self._start_frame)
        except Exception as e:
            print(f"[Kaiserlich Tracker][Modal] ⚠️ Fehler beim Frame-Reset: {e}")

        print(
            "[Kaiserlich Tracker][Modal] ✅ Zyklus beendet."
            if not cancelled else
            "[Kaiserlich Tracker][Modal] ❌ Zyklus abgebrochen."
        )


# ------------------------------------------------------------
# Register
# ------------------------------------------------------------

def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_track_cycle)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_track_cycle)
