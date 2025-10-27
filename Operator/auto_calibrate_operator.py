# Operator/auto_calibrate_operator.py
import bpy
import time
from collections import deque
from typing import Any, Dict, List, Optional, Tuple, Set

# ---- Low-Level Helper (atomare Schritte, keine langen Block-Schleifen) -----
from ..Helper.util_format import fmt8
from ..Helper.util_thresholds import set_all_thresholds_to_one
from ..Helper.util_scene import set_scene_props, call_get_start_frame
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.delete import delete_tracks_by_names
from ..Helper.find_clip_editor_area import find_clip_editor_area
from ..Helper.selection_helper import collect_selected_track_names
from ..Helper.filter_active_tracks import filter_active_tracks_at_frame
from ..Helper.track_markers_helper import track_markers_with_override
from ..Helper.formula_helper import apply_formula_on_selected_tracks
from ..Helper.playhead_helper import reset_to_frame

# Detection/Cleanup
from ..Helper.detect import detect_features
from ..Helper.newmarker import classify_markers
from ..Helper.cleaneup import cleanup_new_markers


# -----------------------------------------------------------------------------
#  Bootstrap: Master-Parameter bevorzugen, sonst Fallback aus Clip/Settings
# -----------------------------------------------------------------------------
def _bootstrap_params(context, scene, ef_target: int):
    """
    Liefert Startparameter für Detect-Adapt.
    Rückgabe:
        md, ma, tr, pz, sz, hz, vc, og, ug, frame_end, source
    """
    import math

    params = scene.get("bootstrap_params", None)
    if params:
        # ✅ Normale Initialisierung aus Master-Operator
        md = float(params.get('md', 100.0))
        ma = params.get('ma', 30)
        try:
            ma = int(ma)
        except Exception:
            ma = 30
        ma = int(round(ma * 1.1))  # leichte Anhebung gemäß Vorgabe

        tr = float(params.get('tr', 0.5))
        pz = int(params.get('pz', 50))
        sz = int(params.get('sz', 0))
        hz = int(params.get('hz', 1))
        vc = bool(params.get('vc', False))

        # Zielbänder aus ef_target ableiten
        za = max(1, int(ef_target) * 4)
        og = int(math.ceil(za * 1.1))
        ug = int(math.floor(za * 0.9))

        frame_end = getattr(scene, "frame_end", None)
        source = "master"
        return md, ma, tr, pz, sz, hz, vc, og, ug, frame_end, source

    # ⚠️ Fallback-Bootstrap falls kein Master-Bootstrap existiert
    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        raise RuntimeError("Kein aktiver Clip verfügbar (Fallback fehlgeschlagen).")

    # --- Basisinformationen aus Clip ---
    hz = int(clip.size[0])
    vc = int(clip.size[1])
    frame_end = getattr(scene, "frame_end", None)

    # --- Parameter aus Tracking-Settings ---
    tracking_settings = getattr(clip, "tracking", None)
    tracking_settings = getattr(tracking_settings, "settings", None)
    ma = int(getattr(tracking_settings, "margin", 100) if tracking_settings else 100)
    pz = int(getattr(tracking_settings, "pattern_size", 50) if tracking_settings else 50)
    sz = int(getattr(tracking_settings, "search_size", 100) if tracking_settings else 100)

    # --- Abgeleitete Startwerte ---
    md = float(hz) * 0.025
    tr = 0.0001
    za = max(1, int(ef_target) * 4)
    og = int(math.ceil(za * 1.1))
    ug = int(math.floor(za * 0.9))

    print(f"[Kaiserlich Tracker][DetectAdapt][Fallback] "
          f"hz={hz}, vc={vc}, margin={ma}, md={md:.2f}, "
          f"pattern={pz}, search={sz}, tr={tr}, og={og}, ug={ug}, frame_end={frame_end}")
    source = "fallback"
    return md, ma, tr, pz, sz, hz, vc, og, ug, frame_end, source


# -----------------------------------------------------------------------------
#  MODAL AUTO-CALIBRATE (ShortTest inline: Detect-Adapt + frameweises Tracking)
# -----------------------------------------------------------------------------
class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Automatische Kalibrierung (ShortTest: Detect-Adapt + Inline-TrackCycle) mit Live-UI."""
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Kaiserlich Tracker — Auto Calibrate (Modal, Inline)"
    bl_options = {"REGISTER", "INTERNAL"}

    tracks_to_delete: bpy.props.StringProperty(
        name="Tracks to delete (comma-separated)",
        default="",
        description="Optional: Namen der zu löschenden Tracks (Komma-getrennt)"
    )

    # ---- Runtime State ------------------------------------------------------
    _timer = None
    _budget_ms: float = 12.0          # CPU-Budget pro Tick (UI bleibt smooth)
    _phase: str = "INIT"              # INIT -> DA_INIT -> DA_DETECT/CLASS/DECIDE -> TRACK_INIT -> TRACK_FRAME -> DONE
    _scene = None
    _clip = None
    _window = _area = _region = _space = None

    # Detect-Adapt State
    _hz = 0
    _vc = 0
    _ma = 100
    _pz = 50
    _sz = 100
    _ef_target = 25
    _md = 0.0
    _tr = 0.0001
    _loop = 0
    _max_loops = 8
    _baseline_start_names: Set[str] = set()
    _pre_snapshot = None
    _last_detect_new: List[Dict[str, Any]] = []
    _last_deleted_old: int = 0
    _og = 0
    _ug = 0

    # Tracking-State
    _start_frame: int = 0
    _end_frame: int = 0
    _cur_frame: int = 0
    _original_selected: List[str] = []
    _frames_processed: int = 0
    _max_frames: int = 0  # 0 = kein Limit

    # ------------------------------------------------------------
    def _r(self, msg: str):
        try:
            self.report({'INFO'}, msg)
        except Exception:
            pass
        print(msg)

    # ------------------------------------------------------------
    def execute(self, context):
        self._scene = context.scene
        self._clip = getattr(context.space_data, "clip", None)
        if not self._clip:
            self.report({'ERROR'}, "Kein aktiver Clip.")
            return {'CANCELLED'}

        # Reset & Basissetup
        set_all_thresholds_to_one(context)
        self._r("[AutoCalibrate] Thresholds auf 1.0 gesetzt.")

        # Modal starten
        self._phase = "DA_INIT"
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        self._r("[AutoCalibrate] Modal gestartet.")
        return {'RUNNING_MODAL'}

    # ------------------------------------------------------------
    def cancel(self, context):
        self._cleanup(context, cancelled=True)

    # ------------------------------------------------------------
    def modal(self, context, event):
        if event.type == 'ESC':
            self._cleanup(context, cancelled=True)
            return {'CANCELLED'}

        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        t0 = time.perf_counter()
        progressed = False

        try:
            while (time.perf_counter() - t0) * 1000.0 < self._budget_ms:
                if self._phase == "DA_INIT":
                    self._da_init(context); progressed = True; continue
                if self._phase == "DA_DETECT":
                    self._da_detect(context); progressed = True; continue
                if self._phase == "DA_CLASS":
                    self._da_classify_cleanup(context); progressed = True; continue
                if self._phase == "DA_DECIDE":
                    if self._da_decide_next(context):
                        progressed = True
                        continue
                    else:
                        # Ziel erreicht oder MaxLoops → weiter zu Tracking
                        self._phase = "TRACK_INIT"
                        progressed = True
                        continue
                if self._phase == "TRACK_INIT":
                    self._track_init(context); progressed = True; continue
                if self._phase == "TRACK_FRAME":
                    if not self._track_one_frame(context):
                        # fertig
                        self._phase = "DONE"
                    progressed = True
                    continue
                if self._phase == "DONE":
                    self._finish(context)
                    return {'FINISHED'}
                break

            if progressed:
                try:
                    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
                except:
                    pass

            return {'RUNNING_MODAL'}

        except Exception as e:
            self.report({'ERROR'}, f"[AutoCalibrate] Fehler: {e}")
            self._cleanup(context, cancelled=True)
            return {'CANCELLED'}

    # ===================== Detect-Adapt ==========================
    def _da_init(self, context):
        scene = self._scene

        # Ziel: Marker pro Frame (Default 25)
        self._ef_target = int(getattr(scene, "kaiserlich_markers_per_frame", 25) or 25)

        # --- Bootstrap laden ---
        md, ma, tr, pz, sz, hz, vc, og, ug, frame_end, source = _bootstrap_params(context, scene, self._ef_target)

        # Operator-State setzen
        self._hz, self._vc = hz, vc
        self._ma, self._pz, self._sz = int(ma), int(pz), int(sz)
        self._md, self._tr = float(md), float(tr)
        self._og, self._ug = int(og), int(ug)

        # Logging
        self._r(f"[ShortTest][Bootstrap:{source}] ef_target={self._ef_target} "
                f"hz={self._hz} vc={self._vc} margin={self._ma} "
                f"md={fmt8(self._md)} pz={self._pz} sz={self._sz} tr={self._tr} "
                f"og={self._og} ug={self._ug} frame_end={frame_end}")

        # Baseline & Snapshot
        self._baseline_start_names = {t.name for t in self._clip.tracking.tracks}
        self._pre_snapshot = snapshot_active_markers(context)

        # Loop-Setup
        self._loop = 0
        self._max_loops = 8
        self._phase = "DA_DETECT"

    def _da_detect(self, context):
        self._loop += 1
        self._r(f"[ShortTest][Detect] LOOP={self._loop} md={fmt8(self._md)}")
        detect_features(
            context,
            placement='FRAME',
            margin=self._ma,
            threshold=self._tr,
            min_distance=int(max(1, round(self._md))),
        )
        # Für saubere Klassifikation: alle deselektieren
        for trk in self._clip.tracking.tracks:
            trk.select = False
        self._phase = "DA_CLASS"

    def _da_classify_cleanup(self, context):
        post = snapshot_active_markers(context)
        alte, neue = classify_markers(self._pre_snapshot, post)
        cleaned_new, deleted_old = cleanup_new_markers(
            context, alte, neue, pz=self._pz, hz=self._hz, vc=self._vc
        )
        self._last_detect_new = cleaned_new
        self._last_deleted_old = deleted_old
        self._r(f"[ShortTest][Cleanup] new={len(cleaned_new)} del_old={deleted_old}")
        self._phase = "DA_DECIDE"

    def _da_decide_next(self, context) -> bool:
        """Return True, wenn eine weitere Detect-Iteration gewünscht ist."""
        remaining = len(self._last_detect_new)

        # Zielband-Check: nutze og/ug als weiches Fenster rund um Zielmenge*4 (aus Bootstrap)
        # plus zusätzlich ±10%-Toleranz rund um ef_target als harte Bedingung.
        diff = remaining - self._ef_target
        tolerance = max(1, int(self._ef_target * 0.10))

        if abs(diff) <= tolerance:
            self._r(f"[ShortTest] Ziel erreicht ({remaining}/{self._ef_target})")
            # Selektiere neue Marker (alles, was nicht baseline war)
            for trk in self._clip.tracking.tracks:
                trk.select = (trk.name not in self._baseline_start_names)
            return False  # weiter zum Tracking

        # Noch nicht im Ziel → min_distance adaptieren
        if remaining > 0:
            ratio = self._ef_target / remaining
            factor = max(0.5, min(2.0, ratio))
            self._md = max(1.0, self._md / factor)
        else:
            self._md *= 1.5
            self._r("[ShortTest] Keine neuen Marker → erhöhe min_distance.")

        # Cleanup der neu erzeugten Marker, falls weitere Loops folgen
        if self._loop < self._max_loops:
            try:
                delete_tracks_by_names(context, [m['track'] for m in self._last_detect_new])
            except Exception:
                pass

        if self._loop >= self._max_loops:
            self._r("[ShortTest] Max Loops erreicht.")
            # Marker selektieren, die nicht baseline sind (was übrig blieb)
            for trk in self._clip.tracking.tracks:
                trk.select = (trk.name not in self._baseline_start_names)
            return False

        self._phase = "DA_DETECT"
        return True

    # ===================== Frameweises Tracking ==================
    def _track_init(self, context):
        self._r("[InlineTrack] ▶ Start")
        self._window, self._area, self._region, self._space = find_clip_editor_area(self._clip)
        if not self._window:
            raise RuntimeError("Keine CLIP_EDITOR Area gefunden.")

        self._start_frame = int(call_get_start_frame(context))
        self._end_frame = int(getattr(self._scene, "frame_end", self._start_frame))
        if self._end_frame < self._start_frame:
            self._end_frame = self._start_frame

        self._original_selected = collect_selected_track_names(context)
        if not self._original_selected:
            raise RuntimeError("Keine Tracks selektiert (InlineTrack).")

        # Selektion fixieren
        for tr in self._clip.tracking.tracks:
            tr.select = (tr.name in self._original_selected)

        # Start-Frame setzen
        self._cur_frame = max(self._start_frame, int(self._scene.frame_current))
        self._space.clip_user.frame_current = self._cur_frame
        self._scene.frame_current = self._cur_frame

        self._frames_processed = 0
        self._max_frames = int(getattr(self._scene, "kaiserlich_max_frames", 0) or 0)
        self._phase = "TRACK_FRAME"

    def _track_one_frame(self, context) -> bool:
        """Trackt genau EINEN Frame. Return False, wenn fertig."""
        # Formel/Optimierung
        try:
            apply_formula_on_selected_tracks(context, max_frames=5)
        except Exception as e:
            print(f"[InlineTrack] ⚠️ Formel-Fehler: {e}")

        # Tracking
        ok = track_markers_with_override(
            self._window, self._area, self._region, self._space,
            backwards=False, sequence=False
        )
        if not ok:
            self._r("[InlineTrack] ⚠️ Tracking-Fehler, Abbruch.")
            return False

        self._frames_processed += 1

        # Nächster Frame
        if self._space.clip_user.frame_current == self._cur_frame:
            self._space.clip_user.frame_current += 1
        if self._space.clip_user.frame_current > self._end_frame:
            self._space.clip_user.frame_current = self._end_frame

        self._scene.frame_current = self._space.clip_user.frame_current
        self._cur_frame = self._space.clip_user.frame_current

        # Aktivität prüfen
        processing_names, _ = filter_active_tracks_at_frame(context, self._original_selected, self._cur_frame)

        # Stop-Kriterien
        if self._cur_frame >= self._end_frame:
            self._r("[InlineTrack] ✅ Szenenende erreicht.")
            return False
        if not processing_names:
            self._r("[InlineTrack] ✅ Keine aktiven Tracks mehr.")
            return False
        if self._max_frames > 0 and self._frames_processed >= self._max_frames:
            self._r("[InlineTrack] ⚠️ Sicherheitslimit erreicht.")
            return False

        return True  # weiter tracken

    # ===================== Abschluss & Cleanup ===================
    def _finish(self, context):
        # Ursprungs-Selektion wiederherstellen
        for tr in self._clip.tracking.tracks:
            tr.select = (tr.name in self._original_selected)

        try:
            reset_to_frame(context, self._start_frame)
        except Exception as e:
            print(f"[InlineTrack] ⚠️ Reset-Fehler: {e}")

        # Optional: explizit genannte Tracks löschen
        if self.tracks_to_delete:
            names = [n.strip() for n in self.tracks_to_delete.split(",") if n.strip()]
            if names:
                delete_tracks_by_names(context, names)

        self._r("[AutoCalibrate] Erfolgreich abgeschlossen.")
        self._cleanup(context, cancelled=False)

    def _cleanup(self, context, cancelled: bool):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
        self._timer = None
        self._phase = "DONE"
        self._r("[AutoCalibrate] Abgebrochen." if cancelled else "[AutoCalibrate] Ende.")


# -----------------------------------------------------------------------------
#  Register / Unregister
# -----------------------------------------------------------------------------
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)
