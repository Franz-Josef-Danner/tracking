import bpy
from typing import List, Tuple, Dict, Any, Optional

# ---- Helper-Imports (nur Einzelfunktionen, keine Gesamt-Short/Deep-Tests) ----
from ..Helper.detect import detect_features
from ..Helper.newmarker import classify_markers
from ..Helper.cleaneup import cleanup_new_markers
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.selection_helper import collect_selected_track_names
from ..Helper.track_markers_helper import track_markers_with_override
from ..Helper.filter_active_tracks import filter_active_tracks_at_frame
from ..Helper.playhead_helper import reset_to_frame, get_start_frame
from ..Helper.util_clip import get_current_track_names
from ..Helper.util_format import fmt8
from ..Helper.util_thresholds import set_all_thresholds_to_one
from ..Helper.delete import delete_track_by_name
from ..Helper.bootstrap import run_bootstrap


# =============================================================================
# Hilfsroutine: Clip-Editor-Override finden (Window/Area/Region/Space)
# =============================================================================
def _find_clip_editor_area(clip) -> Tuple[Optional[bpy.types.Window],
                                          Optional[bpy.types.Area],
                                          Optional[bpy.types.Region],
                                          Optional[bpy.types.SpaceClipEditor]]:
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type != "CLIP_EDITOR":
                continue
            region_window = next((r for r in area.regions if r.type == "WINDOW"), None)
            if not region_window:
                continue
            for space in area.spaces:
                if space.type == "CLIP_EDITOR":
                    # Entweder exakt dieses Clip-Objekt, oder leerer Space ist auch okay
                    if getattr(space, "clip", None) == clip or getattr(space, "clip", None) is None:
                        return window, area, region_window, space
    return None, None, None, None


# =============================================================================
# Operator
# =============================================================================
class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Kaiserlich Tracker — Auto Calibrate (inline Short-Test Orchestrierung)"""
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Kaiserlich Tracker — Auto Calibrate"

    # -------------------------
    # interner Laufzeit-Status
    # -------------------------
    _timer = None
    _phase: str = "INIT"
    _start_frame: int = 0
    _bootstrap: Dict[str, Any] = {}
    _target_markers: int = 25  # Zielmenge für Detect-Adapt
    _eval_frames: int = 120    # Sicherheit: max. Evaluations-Tracking-Länge

    # für Cleanup der im Test erzeugten Tracks
    _current_test_tracks: List[str] = []
    _base_length: int = 0

    # Testmatrix (Paare & Einzelwert) – hier nur als semantischer Ablauf
    _steps: List[Dict[str, Any]] = [
        {"name": "ROT_XY", "keys": ("kaiserlich_rot_thresh_x", "kaiserlich_rot_thresh_y")},
        {"name": "SCALE_MIN_MAX", "keys": ("kaiserlich_scale_thresh_min", "kaiserlich_scale_thresh_max")},
        {"name": "ROT_SCALE_PAIR", "keys": ("kaiserlich_rot_scale_thresh_rot", "kaiserlich_rot_scale_thresh_scale")},
        {"name": "PERSPECTIVE", "keys": ("kaiserlich_perspective_thresh",)},
    ]
    _step_index: int = 0

    # ----------------------------------------------------------------------------
    # Blender Lifecycle
    # ----------------------------------------------------------------------------
    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        clip = getattr(getattr(context, "space_data", None), "clip", None)
        if clip is None:
            self.report({'ERROR'}, "Kein aktiver Clip im CLIP_EDITOR.")
            return {'CANCELLED'}

        # Startframe robust ermitteln
        try:
            self._start_frame = int(get_start_frame(context))
        except Exception:
            self._start_frame = int(context.scene.frame_current)

        # WICHTIG: Sync-Mode deaktivieren, damit Tracking der Playhead-Bewegung nicht folgt
        try:
            clip.tracking.settings.use_sync_mode = False
        except Exception:
            pass

        # Bootstrap-Parameter besorgen (oder Fallback)
        self._bootstrap = self._ensure_bootstrap(context)
        self._target_markers = int(self._bootstrap.get("ef", 25))  # Zielanzahl

        # Alle dynamischen Thresholds auf 1.0 initialisieren (dein Helper)
        try:
            set_all_thresholds_to_one(context)
            self.report({'INFO'}, "[AutoCalibrate] Thresholds auf 1.0 gesetzt.")
        except Exception as e:
            self.report({'WARNING'}, f"[AutoCalibrate] set_all_thresholds_to_one fehlgeschlagen: {e}")

        self._phase = "BASE_DETECT"
        self._current_test_tracks = []
        self._base_length = 0
        self._step_index = 0

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.10, window=context.window)
        wm.modal_handler_add(self)
        self.report({'INFO'}, "[AutoCalibrate] Modal gestartet.")
        return {'RUNNING_MODAL'}

    def modal(self, context: bpy.types.Context, event: bpy.types.Event):
        if event.type == 'ESC':
            self._cleanup_tracks(context, self._current_test_tracks)
            self._finish(context)
            return {'CANCELLED'}

        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        try:
            if self._phase == "BASE_DETECT":
                # 1) Basis: Playhead sauber setzen + Marker setzen (adaptiv)
                try:
                    reset_to_frame(context, int(self._start_frame))
                except Exception:
                    context.scene.frame_current = int(self._start_frame)
                self._current_test_tracks = self._run_detection_adapt(
                    context,
                    md_init=float(self._bootstrap["md"]),
                    target_count=self._target_markers
                )
                self._phase = "BASE_TRACK"
                return {'RUNNING_MODAL'}

            if self._phase == "BASE_TRACK":
                # 2) Basis: Tracken + Länge evaluieren
                tracked_frames = self._run_tracking_inline(context, self._eval_frames)
                self._base_length = tracked_frames
                self.report({'INFO'}, f"[Eval] Base length (selektiert): {self._base_length}")
                # 3) Cleanup + Reset
                self._cleanup_tracks(context, self._current_test_tracks)
                self._phase = "STEP_DETECT"
                return {'RUNNING_MODAL'}

            if self._phase == "STEP_DETECT":
                # 4) Für den aktuellen Step (Paar/Einzel): Playhead zurück + Marker detektieren
                step = self._steps[self._step_index]
                self.report({'INFO'}, f"[STEP {self._step_index+1}/{len(self._steps)}] {step['name']} — Detect")
                try:
                    reset_to_frame(context, int(self._start_frame))
                except Exception:
                    context.scene.frame_current = int(self._start_frame)
                self._current_test_tracks = self._run_detection_adapt(
                    context,
                    md_init=float(self._bootstrap["md"]),
                    target_count=self._target_markers
                )
                self._phase = "STEP_TRACK"
                return {'RUNNING_MODAL'}

            if self._phase == "STEP_TRACK":
                # 5) Tracken & messen
                step = self._steps[self._step_index]
                tracked_frames = self._run_tracking_inline(context, self._eval_frames)
                better = tracked_frames > self._base_length
                self.report({'INFO'}, f"[Eval][{step['name']}] short={tracked_frames} (base={self._base_length})"
                                      f" → {'Verbesserung' if better else 'keine Verbesserung'}")
                # 6) Cleanup + Reset
                self._cleanup_tracks(context, self._current_test_tracks)

                # 7) Step-Fortschritt (Deep-Test-Hook möglich)
                if better:
                    # HIER: Deep-Test modal in Einzelschritten triggern (pro Helper) – Hookpunkt
                    # (z. B. apply-grid-params → detect/track/eval/cleanup …)
                    pass

                # Nächster Step oder Abschluss
                self._step_index += 1
                if self._step_index >= len(self._steps):
                    self._phase = "DONE"
                else:
                    self._phase = "STEP_DETECT"
                return {'RUNNING_MODAL'}

            if self._phase == "DONE":
                self.report({'INFO'}, "[Eval] Alle STEPs abgeschlossen.")
                self._finish(context)
                return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"[AutoCalibrate] Fehler: {e}")
            self._cleanup_tracks(context, self._current_test_tracks)
            self._finish(context)
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

    def cancel(self, context: bpy.types.Context):
        self._cleanup_tracks(context, self._current_test_tracks)
        self._finish(context)

    # ----------------------------------------------------------------------------
    # Kernlogik
    # ----------------------------------------------------------------------------
    def _ensure_bootstrap(self, context: bpy.types.Context) -> Dict[str, Any]:
        """Bootstrap-Parameter aus Helper holen; robust mit Fallbacks."""
        clip = getattr(getattr(context, "space_data", None), "clip", None)
        if clip is None:
            raise RuntimeError("Kein Clip im CLIP_EDITOR.")

        params = {}
        try:
            # run_bootstrap(context, ef) liefert erfahrungsgemäß ein Dict
            params = run_bootstrap(context, ef=self._target_markers)
        except Exception:
            params = {}

        # Fallbacks robust setzen
        size = getattr(clip, "size", [0, 0])
        hz = int(size[0]) if size and len(size) >= 1 else 1920
        vc = int(size[1]) if size and len(size) >= 2 else 1080

        # Defaults: aus deiner letzten Protokollierung entnommen
        return {
            "hz": int(params.get("hz", hz)),
            "vc": int(params.get("vc", vc)),
            "ma": int(params.get("ma", 100)),        # margin
            "md": float(params.get("md", max(8.0, hz * 0.025))),  # min_distance
            "pz": int(params.get("pz", 50)),         # pattern size
            "sz": int(params.get("sz", 100)),        # search size (für detect hier nicht nötig)
            "tr": float(params.get("tr", 0.0001)),   # threshold (detect)
            "ef": int(params.get("ef", 25)),         # target markers
            "og": int(params.get("og", 111)),        # (nur Logging)
            "ug": int(params.get("ug", 90)),         # (nur Logging)
            "frame_end": int(getattr(context.scene, "frame_end", 250)),
        }

    def _run_detection_adapt(self, context: bpy.types.Context, md_init: float, target_count: int) -> List[str]:
        """
        Adaptives Detect → Cleanup (nur neue) in Schleife, um Zielmenge ~target_count zu erreichen.
        Am Ende sind **nur die finalen neuen** Tracks selektiert; Rückgabe: deren Namen.
        """
        ma = int(self._bootstrap.get("ma", 100))
        tr = float(self._bootstrap.get("tr", 0.1))
        pz = int(self._bootstrap.get("pz", 50))
        hz = int(self._bootstrap.get("hz", 1920))
        vc = int(self._bootstrap.get("vc", 1080))

        md = float(md_init)
        loops = 0
        # sicherstellen, dass keine Reste selektiert sind
        clip = getattr(getattr(context, "space_data", None), "clip", None)
        if clip:
            for t in clip.tracking.tracks:
                t.select = False
        pre = snapshot_active_markers(context)  # "alte" Marker vor Detect
        last_cleaned_new: List[Dict[str, Any]] = []

        while loops < 6:
            loops += 1

            # Detect
            detect_features(
                context,
                placement='FRAME',
                margin=ma,
                threshold=tr,
                min_distance=int(max(1, round(md)))
            )
            post = snapshot_active_markers(context)
            old, new = classify_markers(pre, post)

            # Cleanup: nur aktive alte als Baseline, neue nahe an alten verwerfen etc.
            cleaned_new, _deleted_old = cleanup_new_markers(
                context,
                old,
                new,
                pz=pz,
                hz=hz,
                vc=vc
            )

            remaining = len(cleaned_new)
            self.report({'INFO'}, f"[DetectAdapt] Loop {loops} | neue={remaining} | md={fmt8(md)}")

            # Zielnähe erreicht?
            if abs(remaining - target_count) <= max(1, int(target_count * 0.1)):
                last_cleaned_new = cleaned_new
                break

            # md anpassen
            if remaining > 0:
                ratio = target_count / max(1, remaining)
                md = max(1.0, md / ratio)
            else:
                md = md * 1.5

            # Die in *diesem* Loop erzeugten neuen Tracks wieder entfernen,
            # damit der nächste Detect frisch ist.
            for name in [m["track"] for m in cleaned_new]:
                delete_track_by_name(context, name)

            # Baseline für nächste Differenzbildung aktualisieren
            pre = snapshot_active_markers(context)
            last_cleaned_new = cleaned_new

        # Finale Auswahl: nur die **neuen** Tracks selektieren
        new_names = [m["track"] for m in last_cleaned_new]
        clip = getattr(getattr(context, "space_data", None), "clip", None)
        if clip and new_names:
            for trk in clip.tracking.tracks:
                trk.select = (trk.name in new_names)
        return new_names

    def _run_tracking_inline(self, context: bpy.types.Context, max_frames: int) -> int:
        """
        Trackt die aktuell **selektierten** Tracks vorwärts in-place.
        Rückgabe: Anzahl der Frames, in denen nach Selektion noch aktive Tracks existierten.
        """
        clip = getattr(getattr(context, "space_data", None), "clip", None)
        if clip is None:
            self.report({'WARNING'}, "[Track] Kein Clip.")
            return 0

        # Override (Clip-Editor) finden
        window, area, region, space = _find_clip_editor_area(clip)
        if not window or not area or not region or not space:
            self.report({'ERROR'}, "Keine CLIP_EDITOR-Area für Tracking gefunden.")
            return 0
        # sicherstellen, dass der Space wirklich auf den Clip zeigt
        try:
            if getattr(space, "clip", None) is None:
                space.clip = clip
        except Exception:
            pass

        scene = context.scene
        start = int(scene.frame_current)
        # Obergrenze der Track-Schritte an Timeline anpassen
        max_to_end = max(0, int(getattr(scene, "frame_end", start)) - start)
        max_steps = min(int(max_frames), int(max_to_end) if max_to_end > 0 else int(max_frames))
 
        # Sicherstellen, dass es selektierte Tracks gibt
        sel_now = [t.name for t in clip.tracking.tracks if getattr(t, "select", False)]
        if not sel_now:
            self.report({'WARNING'}, "[Track] Keine selektierten Tracks.")
            return 0

        tracked_frames = 0
        for _ in range(max_frames):
            # 1 Schritt tracken
            ok = track_markers_with_override(window, area, region, space, backwards=False, sequence=False)
            if not ok:
                break

            # Frame vorwärts
            scene.frame_current = scene.frame_current + 1
            tracked_frames += 1

            # Nach dem Schritt prüfen, welche selektierten noch aktiv sind
            names, _dropped = filter_active_tracks_at_frame(
                context,
                collect_selected_track_names(context),
                int(scene.frame_current)
            )
            if not names:
                break

        # Playhead nicht automatisch resetten – Cleanup kümmert sich darum,
        # hier wollen wir die gemessene Länge behalten.
        return tracked_frames

    def _cleanup_tracks(self, context: bpy.types.Context, track_names: List[str]) -> None:
        """Löscht ausschließlich die im Test erzeugten Tracks und setzt den Playhead zurück."""
        if track_names:
            for name in track_names:
                try:
                    delete_track_by_name(context, name)
                except Exception:
                    pass
        # Playhead zurück
        try:
            reset_to_frame(context, int(self._start_frame))
        except Exception:
            context.scene.frame_current = int(self._start_frame)

    # ----------------------------------------------------------------------------
    # Abschluss
    # ----------------------------------------------------------------------------
    def _finish(self, context: bpy.types.Context):
        try:
            if self._timer:
                context.window_manager.event_timer_remove(self._timer)
        finally:
            self._timer = None
        # UI-Refresh and Safe End
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        self.report({'INFO'}, "[AutoCalibrate] Ende.")


# =============================================================================
# Register
# =============================================================================
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)
