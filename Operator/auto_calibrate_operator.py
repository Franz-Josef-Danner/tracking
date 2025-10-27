# tracking/Operator/auto_calibrate_operator.py
import bpy
from typing import Dict, List, Tuple, Optional

# --------------- Helper-Importe (aus tracking/Helper) -----------------------
from ..Helper.detect import detect_features
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.newmarker import classify_markers
from ..Helper.cleaneup import cleanup_new_markers
from ..Helper.track_markers_helper import track_markers_with_override
from ..Helper.delete import delete_tracks_by_names
from ..Helper.playhead_helper import reset_to_frame
from ..Helper.selection_helper import collect_selected_track_names
from ..Helper.filter_active_tracks import filter_active_tracks_at_frame
from ..Helper.track_length_helper import get_total_track_length
from ..Helper.find_clip_editor_area import find_clip_editor_area
from ..Helper.util_thresholds import set_all_thresholds_to_one
from ..Helper.util_scene import set_scene_props

# ----------------------------------------------------------------------------
#   OPERATOR: Short- and Deep-Test via einzelne Helper-Aufrufe, modal
# ----------------------------------------------------------------------------
class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Kaiserlich Tracker — Auto Calibrate (Modal)"
    bl_options = {"REGISTER", "UNDO"}

    # Parameter für Kurztest
    short_frames: bpy.props.IntProperty(
        name="Kurztest Frames",
        default=30,
        min=5,
        description="Anzahl der Frames für den Kurztest pro Kandidat"
    )
    target_markers: bpy.props.IntProperty(
        name="Zielmarker",
        default=25,
        min=5,
        description="Gewünschte Markeranzahl pro Kurztest"
    )

    # Interner Zustand
    _phase: str = "INIT"
    _baseline_len: int = 0
    _step_index: int = 0
    _steps = ["ROTXY", "SCALE", "ROTSCALE", "PERSPECTIVE"]
    _pending_deep: Optional[str] = None
    _best_deep_val: Optional[Tuple[float, float]] = None
    _deep_factor: float = 4.0
    _orig_thresholds: Dict[str, float] = {}
    _bootstrap: Dict[str, float] = {}

    # ------------------------------------------------------------------------
    def invoke(self, context, event):
        # Thresholds zurücksetzen
        set_all_thresholds_to_one(context)
        self.report({'INFO'}, "[AutoCalibrate] Thresholds auf 1.0 gesetzt.")

        # Bootstrap: Parameter aus Szene/Clip abgreifen
        clip = getattr(context.space_data, "clip", None)
        if not clip:
            self.report({'ERROR'}, "Kein aktiver Clip.")
            return {'CANCELLED'}

        sc = context.scene
        # Margin, Pattern- und Search-Size aus Tracking-Settings
        ts = getattr(clip.tracking, "settings", None)
        ma = getattr(ts, "margin", 100)
        pz = getattr(ts, "pattern_size", 50)
        sz = getattr(ts, "search_size", 100)
        hz = float(clip.size[0])
        vc = float(clip.size[1])
        md = hz * 0.025
        tr = 0.0001

        # Zielband (±10 %)
        ef = self.target_markers
        og = int(ef * 1.1)
        ug = int(ef * 0.9)
        self._bootstrap = dict(ma=ma, pz=pz, sz=sz, hz=hz, vc=vc, md=md, tr=tr, og=og, ug=ug)

        # Ursprüngliche Threshold-Werte speichern
        self._orig_thresholds = dict(
            rot_x=float(sc.kaiserlich_rot_thresh_x),
            rot_y=float(sc.kaiserlich_rot_thresh_y),
            smin=float(sc.kaiserlich_scale_thresh_min),
            smax=float(sc.kaiserlich_scale_thresh_max),
            rth=float(sc.kaiserlich_rot_scale_thresh_rot),
            sth=float(sc.kaiserlich_rot_scale_thresh_scale),
            pth=float(sc.kaiserlich_perspective_thresh),
        )

        # Phasen-Initialisierung
        self._phase = "BASE_DETECT"
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    # ------------------------------------------------------------------------
    def modal(self, context, event):
        # UI refresh am Ende jeder Iteration
        try:
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        except Exception:
            pass

        # ESC → Abbruch
        if event.type == 'ESC':
            self.report({'INFO'}, "[AutoCalibrate] Abgebrochen.")
            return {'CANCELLED'}

        # Nur auf Timer reagieren
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        # Eine Phase pro Timer-Event abarbeiten
        if self._phase == "BASE_DETECT":
            # Detection Adapt (Initial)
            self._run_detection_adapt(context, self._bootstrap["md"], self.target_markers)
            self._phase = "BASE_TRACK"
            return {'RUNNING_MODAL'}

        if self._phase == "BASE_TRACK":
            # Kurz Tracking
            self._run_tracking(context, frames=self.short_frames)
            self._phase = "BASE_MEASURE"
            return {'RUNNING_MODAL'}

        if self._phase == "BASE_MEASURE":
            # Baseline-Länge messen
            self._baseline_len = self._measure_length(context)
            self.report({'INFO'}, f"[Baseline] Länge = {self._baseline_len}")
            # Cleanup
            self._cleanup_tracks(context)
            # Nächster Schritt
            self._phase = "STEP_INIT"
            return {'RUNNING_MODAL'}

        # ----------- Kurztest für jede Schwelle ----------
        if self._phase == "STEP_INIT":
            if self._step_index >= len(self._steps):
                self._phase = "DONE"
                return {'RUNNING_MODAL'}

            step = self._steps[self._step_index]
            # Schwellen für aktuellen Step etwas verschieben (faktor ±10–25 %)
            self._apply_step_variant(context, step)
            # Detection
            self._phase = "STEP_DETECT"
            return {'RUNNING_MODAL'}

        if self._phase == "STEP_DETECT":
            self._run_detection_adapt(context, self._bootstrap["md"], self.target_markers)
            self._phase = "STEP_TRACK"
            return {'RUNNING_MODAL'}

        if self._phase == "STEP_TRACK":
            self._run_tracking(context, frames=self.short_frames)
            self._phase = "STEP_MEASURE"
            return {'RUNNING_MODAL'}

        if self._phase == "STEP_MEASURE":
            short_len = self._measure_length(context)
            step = self._steps[self._step_index]
            improved = short_len >= self._baseline_len
            self.report({'INFO'}, f"[Kurztest] {step} = {short_len}, Baseline {self._baseline_len}, Verbesserung: {improved}")
            # Cleanup
            self._cleanup_tracks(context)
            # Restore original Thresholds (wichtig vor Deep-Test)
            self._restore_thresholds(context)
            if improved:
                # Deep-Test starten
                self._pending_deep = step
                self._best_deep_val = self._get_current_step_val(context, step)
                self._deep_factor = 4.0
                self._phase = "DEEP_STEP"
            else:
                # Zum nächsten Step
                self._step_index += 1
                self._phase = "STEP_INIT"
            return {'RUNNING_MODAL'}

        # ----------- Deep-Test (Long) -------------
        if self._phase == "DEEP_STEP":
            step = self._pending_deep
            if self._deep_factor < 1.1:
                # Deep-Test beendet → Bestwert setzen und zurück zum nächsten Step
                self._apply_step_val(context, step, self._best_deep_val)
                self.report({'INFO'}, f"[Deep] {step} bester Wert: {self._best_deep_val}")
                self._pending_deep = None
                self._step_index += 1
                self._phase = "STEP_INIT"
                return {'RUNNING_MODAL'}

            # Kandidat berechnen
            current_val = self._get_current_step_val(context, step)
            if isinstance(current_val, tuple):
                cand = tuple(max(1e-6, v / self._deep_factor) for v in current_val)
            else:
                cand = max(1e-6, current_val / self._deep_factor)
            self._apply_step_val(context, step, cand)
            # Detection
            self._run_detection_adapt(context, self._bootstrap["md"], self.target_markers)
            # Tracking
            self._run_tracking(context, frames=self.short_frames)
            # Messen
            score = self._measure_length(context)
            self._cleanup_tracks(context)
            if score >= self._baseline_len:
                # Erfolg → übernehmen
                self._best_deep_val = cand
                # feinere Suche
                self._deep_factor = max(1.1, self._deep_factor / 2.0)
            else:
                # Misserfolg → weniger drastische Reduktion
                self._deep_factor = max(1.1, self._deep_factor / 1.5)
            return {'RUNNING_MODAL'}

        if self._phase == "DONE":
            self.report({'INFO'}, "[AutoCalibrate] Erfolgreich abgeschlossen.")
            return {'FINISHED'}

        return {'RUNNING_MODAL'}

    # ------------------------------------------------------------------------
    #  Hilfsfunktionen
    # ------------------------------------------------------------------------
    def _run_detection_adapt(self, context, md_init: float, target_count: int):
        """Marker adaptiv detektieren, bis Zielmenge erreicht oder max Schleifen."""
        ma = self._bootstrap["ma"]
        tr = self._bootstrap["tr"]
        pz = self._bootstrap["pz"]
        hz = self._bootstrap["hz"]
        vc = self._bootstrap["vc"]
        md = md_init
        loops = 0
        # Snapshot vor dem ersten Detect
        pre = snapshot_active_markers(context)
        while loops < 6:
            loops += 1
            # Marker detektieren
            detect_features(context, placement='FRAME', margin=ma, threshold=tr, min_distance=int(md))
            post = snapshot_active_markers(context)
            old, new = classify_markers(pre, post)
            cleaned_new, _ = cleanup_new_markers(context, old, new, pz=pz, hz=hz, vc=vc)
            remaining = len(cleaned_new)
            # Inneres Logging
            self.report({'INFO'}, f"[DetectAdapt] Loop {loops}, neue={remaining}, md={md:.2f}")
            if abs(remaining - target_count) <= max(1, int(target_count * 0.1)):
                break
            if remaining > 0:
                ratio = target_count / remaining
                md = max(1.0, md / ratio)
            else:
                md = md * 1.5
            # Neue Tracks löschen vor nächster Runde
            delete_tracks_by_names(context, [m['track'] for m in cleaned_new])
            pre = snapshot_active_markers(context)

        # Selektiere die neuen Marker (nicht baseline)
        baseline = {t.name for t in context.space_data.clip.tracking.tracks if t.name not in [m['track'] for m in cleaned_new]}
        for trk in context.space_data.clip.tracking.tracks:
            trk.select = trk.name not in baseline

    def _run_tracking(self, context, frames: int):
        """Trackt selektierte Marker für eine Anzahl Frames (inline)."""
        clip = context.space_data.clip
        if not clip:
            return
        # Find Clip Editor Area for override
        window, area, region, space = find_clip_editor_area(clip)
        if not window:
            self.report({'ERROR'}, "Keine Clip-Editor-Fläche gefunden.")
            return
        scene = context.scene
        start = scene.frame_current
        # Track pro Frame
        for i in range(frames):
            track_markers_with_override(window, area, region, space, backwards=False, sequence=False)
            scene.frame_current += 1
            # Break, wenn keine aktiven Tracks mehr
            names, dropped = filter_active_tracks_at_frame(context, collect_selected_track_names(context), scene.frame_current)
            if not names:
                break

    def _measure_length(self, context) -> int:
        """Liefert Summe der Track-Längen (gesamt oder selektiert)."""
        return get_total_track_length(context, start_frame=context.scene.frame_current)

    def _cleanup_tracks(self, context):
        # Alle Tracks löschen
        names = [t.name for t in context.space_data.clip.tracking.tracks]
        if names:
            delete_tracks_by_names(context, names)
        # Playhead reset
        reset_to_frame(context, self.short_frames)

    def _apply_step_variant(self, context, step: str):
        """Modifiziert die Thresholds leicht pro Step für den Kurztest."""
        sc = context.scene
        f_low, f_high = 0.9, 1.1
        if step == "ROTXY":
            vx = self._orig_thresholds["rot_x"] * f_low
            vy = self._orig_thresholds["rot_y"] * f_high
            set_scene_props(sc, kaiserlich_rot_thresh_x=vx, kaiserlich_rot_thresh_y=vy)
        elif step == "SCALE":
            vmin = self._orig_thresholds["smin"] * f_low
            vmax = self._orig_thresholds["smax"] * f_high
            set_scene_props(sc, kaiserlich_scale_thresh_min=vmin, kaiserlich_scale_thresh_max=vmax)
        elif step == "ROTSCALE":
            vr = self._orig_thresholds["rth"] * f_low
            vs = self._orig_thresholds["sth"] * f_high
            set_scene_props(sc,
                kaiserlich_rot_scale_thresh_rot=vr,
                kaiserlich_rot_scale_thresh_scale=vs
            )
        elif step == "PERSPECTIVE":
            vp = self._orig_thresholds["pth"] * 1.25
            set_scene_props(sc, kaiserlich_perspective_thresh=vp)

    def _restore_thresholds(self, context):
        """Setzt alle Thresholds auf die Ursprungswerte zurück."""
        sc = context.scene
        set_scene_props(sc,
            kaiserlich_rot_thresh_x=self._orig_thresholds["rot_x"],
            kaiserlich_rot_thresh_y=self._orig_thresholds["rot_y"],
            kaiserlich_scale_thresh_min=self._orig_thresholds["smin"],
            kaiserlich_scale_thresh_max=self._orig_thresholds["smax"],
            kaiserlich_rot_scale_thresh_rot=self._orig_thresholds["rth"],
            kaiserlich_rot_scale_thresh_scale=self._orig_thresholds["sth"],
            kaiserlich_perspective_thresh=self._orig_thresholds["pth"],
        )

    def _get_current_step_val(self, context, step: str):
        sc = context.scene
        if step == "ROTXY":
            return (float(sc.kaiserlich_rot_thresh_x), float(sc.kaiserlich_rot_thresh_y))
        if step == "SCALE":
            return (float(sc.kaiserlich_scale_thresh_min), float(sc.kaiserlich_scale_thresh_max))
        if step == "ROTSCALE":
            return (float(sc.kaiserlich_rot_scale_thresh_rot), float(sc.kaiserlich_rot_scale_thresh_scale))
        if step == "PERSPECTIVE":
            return float(sc.kaiserlich_perspective_thresh)
        return 0

    def _apply_step_val(self, context, step: str, value):
        sc = context.scene
        if step == "ROTXY":
            vx, vy = value
            set_scene_props(sc, kaiserlich_rot_thresh_x=vx, kaiserlich_rot_thresh_y=vy)
        elif step == "SCALE":
            vmin, vmax = value
            set_scene_props(sc, kaiserlich_scale_thresh_min=vmin, kaiserlich_scale_thresh_max=vmax)
        elif step == "ROTSCALE":
            vr, vs = value
            set_scene_props(sc, kaiserlich_rot_scale_thresh_rot=vr, kaiserlich_rot_scale_thresh_scale=vs)
        elif step == "PERSPECTIVE":
            set_scene_props(sc, kaiserlich_perspective_thresh=float(value))

# ----------------------------------------------------------------------------
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)
