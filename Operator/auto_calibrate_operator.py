# Operator/auto_calibrate_operator.py
import bpy
import math
from typing import Optional, Tuple, Dict, Any, List

# ---- Pflicht-Helper (fix) ---------------------------------------------------
from ..Helper.util_thresholds import set_all_thresholds_to_one
from ..Helper.util_scene import set_scene_props

# ---- Optionale Helper (Shim) ------------------------------------------------
# Tausche die Namen in den TRY-Blöcken ggf. gegen die in deinem Repo exakten Funktionsnamen aus.
# Falls ein Import fehlschlägt, greifen Fallbacks via bpy.ops/* bzw. einfache Implementierungen.

def _try_import_helper():
    helpers: Dict[str, Any] = {}

    # Detect / Marker setzen (adaptiv)
    try:
        # Beispiel: in deinem Repo könnte dies z.B. util_detect.detect_adaptive heißen
        from ..Helper.util_detect import detect_adaptive as _detect_adaptive
        helpers["detect_adaptive"] = _detect_adaptive
    except Exception:
        helpers["detect_adaptive"] = None

    # Cleanup neuer Marker (reduziert auf Zielmenge etc.)
    try:
        from ..Helper.util_cleanup import cleanup_new_markers as _cleanup_new_markers
        helpers["cleanup_new_markers"] = _cleanup_new_markers
    except Exception:
        helpers["cleanup_new_markers"] = None

    # Tracks löschen (für einen sauberen Neustart pro Test)
    try:
        from ..Helper.util_tracks import delete_all_tracks as _delete_all_tracks
        helpers["delete_all_tracks"] = _delete_all_tracks
    except Exception:
        # Alternativ ein anderer Name in deinem Repo:
        try:
            from ..Helper.util_tracks import delete_tracks_by_names as _delete_tracks_by_names
            def _delete_all_tracks(context):
                # Fallback: löscht alle Tracks der aktiven Clip
                clip = getattr(context.space_data, "clip", None)
                if not clip:
                    return 0
                names = [t.name for t in clip.tracking.tracks]
                _delete_tracks_by_names(context, names)
                return len(names)
            helpers["delete_all_tracks"] = _delete_all_tracks
        except Exception:
            helpers["delete_all_tracks"] = None

    # Tracken (kurz, vorwärts)
    try:
        from ..Helper.util_track import track_markers_with_override as _track_markers_with_override
        def _track_forward(context, steps:int=25, backwards:bool=False):
            # In deinem Repo akzeptiert track_markers_with_override evtl. frames/steps – hier vereinheitlicht
            return _track_markers_with_override(context, steps=steps, backwards=backwards)
        helpers["track_forward"] = _track_forward
    except Exception:
        helpers["track_forward"] = None

    # Selection für Score-Ermittlung
    try:
        from ..Helper.util_selection import filter_active_tracks_at_frame as _filter_active_tracks_at_frame
        helpers["select_active_tracks"] = _filter_active_tracks_at_frame
    except Exception:
        helpers["select_active_tracks"] = None

    # Score messen (z.B. summierte Länge ausgewählter Tracks)
    try:
        from ..Helper.util_eval import measure_total_selected_length as _measure_total_selected_length
        helpers["measure_score"] = _measure_total_selected_length
    except Exception:
        helpers["measure_score"] = None

    # Playhead resetten
    try:
        from ..Helper.util_timeline import reset_to_frame as _reset_to_frame
        helpers["reset_to_frame"] = _reset_to_frame
    except Exception:
        helpers["reset_to_frame"] = None

    return helpers

_HELP = _try_import_helper()


# ---- Kleine Fallbacks (nur wenn Helper fehlen) ------------------------------
def _fallback_reset_to_frame(context, frame:int=1):
    sc = context.scene
    if sc:
        sc.frame_set(frame)

def _fallback_delete_all_tracks(context) -> int:
    clip = getattr(context.space_data, "clip", None)
    if not clip:
        return 0
    cnt = 0
    for tr in list(clip.tracking.tracks):
        clip.tracking.tracks.remove(tr)
        cnt += 1
    return cnt

def _fallback_track_forward(context, steps:int=25, backwards:bool=False):
    # Minimal-Variante: Blender-Operator (vorwärts, keine Backwards-Schleife)
    # Du kannst hier ggf. eigene kleinere Wrapper nutzen.
    try:
        bpy.ops.clip.track_markers(backwards=backwards, sequence=False)
    except Exception:
        pass

def _fallback_detect_adaptive(context, min_distance:float, max_points:int=9999) -> int:
    # Minimal: Blender Standard-Detect (ohne echte Adaptivität)
    # Passe das bei Bedarf an, falls dein Helper fehlt.
    try:
        # Beispiel (die Parameter variieren je nach Setup):
        bpy.ops.clip.detect_features(min_distance=int(min_distance))
    except Exception:
        pass
    # Rückgabe: Anzahl neuer Marker (nicht exakt messbar hier)
    clip = getattr(context.space_data, "clip", None)
    return len(clip.tracking.tracks) if clip else 0

def _fallback_cleanup_new_markers(context, target:int) -> Tuple[int,int]:
    # Dummy: keine echte Reduktion – in deinem Setup bitte Helper verwenden!
    # Return (new_kept, old_deleted)
    clip = getattr(context.space_data, "clip", None)
    if not clip:
        return (0,0)
    return (min(len(clip.tracking.tracks), target), 0)

def _fallback_select_active_tracks(context) -> List[Any]:
    clip = getattr(context.space_data, "clip", None)
    if not clip:
        return []
    return list(clip.tracking.tracks)

def _fallback_measure_score(context, tracks:List[Any]) -> int:
    # Simpler Proxy: Anzahl Marker × aktuelle Framezahl
    sc = context.scene
    if not sc:
        return 0
    return max(0, len(tracks) * sc.frame_current)


# ---- Utility ----------------------------------------------------------------
def _ui_refresh(context):
    # for live updates
    try:
        area = next(a for a in context.screen.areas if a.type in {'CLIP_EDITOR', 'VIEW_3D', 'IMAGE_EDITOR'})
        area.tag_redraw()
    except Exception:
        pass
    try:
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
    except Exception:
        pass

def _detect_and_cleanup(context, min_distance:float, target_count:int, report_fn):
    # Marker erkennen
    detect_fn = _HELP.get("detect_adaptive") or (lambda ctx, **kw: _fallback_detect_adaptive(ctx, kw.get("min_distance", 32.0)))
    new_count = detect_fn(context, min_distance=min_distance)

    # Cleanup auf Zielmenge
    cleanup_fn = _HELP.get("cleanup_new_markers") or (lambda ctx, target: _fallback_cleanup_new_markers(ctx, target))
    kept, deleted = cleanup_fn(context, target=target_count)

    report_fn(f"[Cleanup] Eingabe: {new_count} neue Marker → kept={kept}, del_old={deleted}")
    return kept


def _delete_all_tracks(context) -> int:
    fn = _HELP.get("delete_all_tracks") or _fallback_delete_all_tracks
    return fn(context)

def _reset_playhead(context, frame:int):
    reset_fn = _HELP.get("reset_to_frame") or (lambda ctx, f: _fallback_reset_to_frame(ctx, f))
    reset_fn(context, frame)

def _track_forward(context, steps:int=25, backwards:bool=False):
    fn = _HELP.get("track_forward") or _fallback_track_forward
    return fn(context, steps=steps, backwards=backwards)

def _select_active_tracks(context) -> List[Any]:
    fn = _HELP.get("select_active_tracks") or _fallback_select_active_tracks
    return fn(context)

def _measure_score(context, tracks:List[Any]) -> int:
    fn = _HELP.get("measure_score") or _fallback_measure_score
    return fn(context, tracks)


# -----------------------------------------------------------------------------
#  OPERATOR
# -----------------------------------------------------------------------------
class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Automatische Kalibrierung (modal): Short-Test je Paar → bei Verbesserung Deep-Test (Long-Reduce) → nächstes Paar."""
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Kaiserlich Tracker — Auto Calibrate (Modal)"
    bl_options = {"REGISTER", "UNDO"}

    # Benutzer-Parameter
    short_frames: bpy.props.IntProperty(
        name="Short frames",
        default=40,
        min=5,
        description="Kurzer Tracking-Horizont pro Kandidat (Frames)"
    )
    target_points: bpy.props.IntProperty(
        name="Target markers",
        default=25,
        min=5,
        description="Zielanzahl an Markern für Kurztest"
    )
    start_frame: bpy.props.IntProperty(
        name="Start frame",
        default=1,
        min=1
    )
    deep_init_scale: bpy.props.FloatProperty(
        name="Deep init scale",
        default=4.0,
        min=1.25,
        description="Erster Reduktionsfaktor im Deep-Test (z.B. 4.0 → Wert/4)"
    )
    deep_min_scale: bpy.props.FloatProperty(
        name="Deep min scale",
        default=1.0,
        min=1.0,
        description="Abbruch wenn Faktor unter diesen Wert fällt"
    )

    # interner Zustand
    _phase: str = "INIT"
    _step_idx: int = 0
    _steps: List[str] = None
    _base_len: int = 0
    _pending_deep_step: Optional[str] = None

    # Deep-Test Variablen
    _deep_sf: float = 4.0
    _deep_best: Dict[str, Any] = None
    _deep_candidate: Dict[str, Any] = None

    # Bootstrap
    _bootstrap: Dict[str, Any] = None

    # -------------------------------------------------------------------------
    #  Lifecycle
    # -------------------------------------------------------------------------
    def invoke(self, context, event):
        self._log = lambda msg: self.report({'INFO'}, msg)

        # Reset Thresholds
        set_all_thresholds_to_one(context)
        self._log("[AutoCalibrate] Thresholds auf 1.0 gesetzt.")

        # vorbereiten
        self._phase = "BOOTSTRAP"
        self._steps = ["ROTXY", "SCALE", "ROTSCALE", "PERSPECTIVE"]
        self._step_idx = 0
        self._base_len = 0
        self._pending_deep_step = None
        self._deep_best = {}
        self._deep_candidate = {}

        # Bootstrap-Parameter (Master -> Szene) oder Fallback
        scene = context.scene
        params = scene.get("bootstrap_params", None)
        clip = getattr(context.space_data, "clip", None)
        if not clip:
            self.report({'ERROR'}, "Kein aktiver Movie Clip im Clip Editor.")
            return {'CANCELLED'}

        if params:
            hz = float(params.get('hz', clip.size[0]))
            vc = float(params.get('vc', clip.size[1]))
            ma = int(params.get('ma', 100))
            pz = int(params.get('pz', 50))
            sz = int(params.get('sz', 100))
            tr = float(params.get('tr', 0.0001))
        else:
            hz = float(clip.size[0])
            vc = float(clip.size[1])
            tracking_settings = getattr(clip.tracking, "settings", None)
            ma = getattr(tracking_settings, "margin", 100) if tracking_settings else 100
            pz = getattr(tracking_settings, "pattern_size", 50) if tracking_settings else 50
            sz = getattr(tracking_settings, "search_size", 100) if tracking_settings else 100
            tr = 0.0001

        md = hz * 0.025
        ef_target = self.target_points
        og = math.ceil(ef_target * 1.1)
        ug = math.floor(ef_target * 0.9)

        self._bootstrap = dict(hz=hz, vc=vc, ma=ma, pz=pz, sz=sz, tr=tr, md=md, og=og, ug=ug)

        self._log("[AutoCalibrate] Modal gestartet.")
        self._log(f"[DetectAdapt][Bootstrap] hz={hz}, vc={vc}, margin={ma}, md={md:.2f}, "
                  f"pattern={pz}, search={sz}, tr={tr}, og={og}, ug={ug}, frame_end={context.scene.frame_end}")

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    # -------------------------------------------------------------------------
    def modal(self, context, event):
        report = self._log

        # UI refresh an jeder Iteration
        _ui_refresh(context)

        # Sicherheitsabbruch
        if event.type in {'ESC'}:
            report("[AutoCalibrate] Abgebrochen.")
            return {'CANCELLED'}

        # --- PHASEN-STATE-MACHINE -------------------------------------------
        if self._phase == "BOOTSTRAP":
            # Startzustand → Basiswert ermitteln
            self._phase = "BASE_DETECT"
            return {'RUNNING_MODAL'}

        # 1) Basis: Marker setzen → cleanup → track → Score messen
        if self._phase == "BASE_DETECT":
            kept = _detect_and_cleanup(
                context,
                min_distance=self._bootstrap["md"],
                target_count=self.target_points,
                report_fn=report
            )
            self._phase = "BASE_TRACK"
            return {'RUNNING_MODAL'}

        if self._phase == "BASE_TRACK":
            _reset_playhead(context, self.start_frame)
            _track_forward(context, steps=self.short_frames, backwards=False)
            self._phase = "BASE_MEASURE"
            return {'RUNNING_MODAL'}

        if self._phase == "BASE_MEASURE":
            tracks = _select_active_tracks(context)
            self._base_len = _measure_score(context, tracks)
            report(f"[Eval] Base length (selektiert): {self._base_len}")
            # Cleanup & Reset
            _delete_all_tracks(context)
            _reset_playhead(context, self.start_frame)
            self._phase = "STEP_PREP"
            return {'RUNNING_MODAL'}

        # 2) Pro Step (Paar/Einzelwert)
        if self._phase == "STEP_PREP":
            if self._step_idx >= len(self._steps):
                self._phase = "DONE"
                return {'RUNNING_MODAL'}

            self._current_step = self._steps[self._step_idx]
            report(f"[Step] Starte Kurztest für {self._current_step}")
            # optional: Scene-Props auf initiale Kandidaten setzen (z. B. neutral)
            self._apply_step_neutral(context, self._current_step)
            self._phase = "STEP_SHORT_DETECT"
            return {'RUNNING_MODAL'}

        if self._phase == "STEP_SHORT_DETECT":
            kept = _detect_and_cleanup(
                context,
                min_distance=self._bootstrap["md"],
                target_count=self.target_points,
                report_fn=report
            )
            self._phase = "STEP_SHORT_TRACK"
            return {'RUNNING_MODAL'}

        if self._phase == "STEP_SHORT_TRACK":
            _reset_playhead(context, self.start_frame)
            _track_forward(context, steps=self.short_frames, backwards=False)
            self._phase = "STEP_SHORT_MEASURE"
            return {'RUNNING_MODAL'}

        if self._phase == "STEP_SHORT_MEASURE":
            tracks = _select_active_tracks(context)
            short_len = _measure_score(context, tracks)
            # Cleanup & Reset
            _delete_all_tracks(context)
            _reset_playhead(context, self.start_frame)

            improved = short_len >= self._base_len
            report(f"[Eval][{self._current_step}] short={short_len} (base={self._base_len}) "
                   f"→ {'Verbesserung' if improved else 'keine Verbesserung'}")

            if improved:
                self._pending_deep_step = self._current_step
                self._phase = "DEEP_PREP"
            else:
                self._step_idx += 1
                self._phase = "STEP_PREP"
            return {'RUNNING_MODAL'}

        # 3) Deep-Test (Long-Reduce) für genau dieses Paar
        if self._phase == "DEEP_PREP":
            self._deep_sf = max(self.deep_init_scale, 1.25)
            self._deep_best = {"value": self._get_current_step_value(context, self._pending_deep_step)}
            self._deep_candidate = {"value": self._deep_best["value"]}
            report(f"[Deep][{self._pending_deep_step}] init value={self._deep_best['value']} sf={self._deep_sf}")
            self._phase = "DEEP_ITER"
            return {'RUNNING_MODAL'}

        if self._phase == "DEEP_ITER":
            if self._deep_sf < self.deep_min_scale:
                # Deep fertig → Bestwert übernehmen
                self._apply_step_value(context, self._pending_deep_step, self._deep_best["value"])
                report(f"[Deep][{self._pending_deep_step}] final → {self._deep_best['value']}")
                self._pending_deep_step = None
                self._step_idx += 1
                self._phase = "STEP_PREP"
                return {'RUNNING_MODAL'}

            # Nächsten Kandidaten berechnen (einfaches Teilen)
            cand = self._deep_candidate["value"]
            if isinstance(cand, tuple):
                # Paare skaliert man pro Komponente
                cand = tuple(max(1e-6, c / self._deep_sf) for c in cand)
            else:
                cand = max(1e-6, float(cand) / self._deep_sf)

            # Kandidat anwenden
            self._apply_step_value(context, self._pending_deep_step, cand)

            # Clean + Detect + Kurztrack
            _delete_all_tracks(context)
            _reset_playhead(context, self.start_frame)
            _detect_and_cleanup(context, min_distance=self._bootstrap["md"],
                                target_count=self.target_points, report_fn=report)
            _reset_playhead(context, self.start_frame)
            _track_forward(context, steps=self.short_frames, backwards=False)

            # Score
            tracks = _select_active_tracks(context)
            cand_len = _measure_score(context, tracks)
            _delete_all_tracks(context)
            _reset_playhead(context, self.start_frame)

            report(f"[Deep][{self._pending_deep_step}] cand={cand} → score={cand_len} (target≥{self._base_len})")

            if cand_len >= self._base_len:
                # Erfolg → als Bestwert übernehmen und noch aggressiver testen
                self._deep_best["value"] = cand
                # optional feinere Suche: sf leicht > 1 lassen, sonst sprunghaft
                self._deep_sf = max(1.05, self._deep_sf / 2.0)
                self._deep_candidate["value"] = cand
            else:
                # kein Erfolg → gröber reduzieren
                self._deep_sf = max(1.05, self._deep_sf / 1.5)

            return {'RUNNING_MODAL'}

        if self._phase == "DONE":
            report("[AutoCalibrate] Erfolgreich abgeschlossen.")
            report("[AutoCalibrate] Ende.")
            return {'FINISHED'}

        # Fallback
        return {'RUNNING_MODAL'}

    # -------------------------------------------------------------------------
    #  Step-Anwendung (Paar-/Einzelwert)
    # -------------------------------------------------------------------------
    def _apply_step_neutral(self, context, step: str):
        """Setzt neutrale/aktuelle Werte auf die Scene-Props, bevor der Kurztest beginnt."""
        sc = context.scene
        if step == "ROTXY":
            # neutral: aktuelle Werte beibehalten (oder leichte Default-Absenkung)
            pass
        elif step == "SCALE":
            pass
        elif step == "ROTSCALE":
            pass
        elif step == "PERSPECTIVE":
            pass
        # Keine Änderung notwendig, wir testen ausgehend vom aktuellen Stand.

    def _get_current_step_value(self, context, step: str):
        sc = context.scene
        if step == "ROTXY":
            return (float(sc.get("kaiserlich_rot_thresh_x", 1.0)),
                    float(sc.get("kaiserlich_rot_thresh_y", 1.0)))
        if step == "SCALE":
            return (float(sc.get("kaiserlich_scale_thresh_min", 1.0)),
                    float(sc.get("kaiserlich_scale_thresh_max", 1.0)))
        if step == "ROTSCALE":
            return (float(sc.get("kaiserlich_rot_scale_thresh_rot", 1.0)),
                    float(sc.get("kaiserlich_rot_scale_thresh_scale", 1.0)))
        if step == "PERSPECTIVE":
            return float(sc.get("kaiserlich_perspective_thresh", 1.0))
        return 1.0

    def _apply_step_value(self, context, step: str, value: Any):
        sc = context.scene
        if step == "ROTXY":
            vx, vy = value
            set_scene_props(sc, kaiserlich_rot_thresh_x=float(vx), kaiserlich_rot_thresh_y=float(vy))
            self._log(f"[Apply ROTXY] → ({vx:.6f}, {vy:.6f})")
        elif step == "SCALE":
            vmin, vmax = value
            set_scene_props(sc, kaiserlich_scale_thresh_min=float(vmin), kaiserlich_scale_thresh_max=float(vmax))
            self._log(f"[Apply SCALE] → ({vmin:.6f}, {vmax:.6f})")
        elif step == "ROTSCALE":
            vr, vs = value
            set_scene_props(sc, kaiserlich_rot_scale_thresh_rot=float(vr), kaiserlich_rot_scale_thresh_scale=float(vs))
            self._log(f"[Apply ROT+SCALE] → ({vr:.6f}, {vs:.6f})")
        elif step == "PERSPECTIVE":
            vp = float(value)
            set_scene_props(sc, kaiserlich_perspective_thresh=vp)
            self._log(f"[Apply PERSPECTIVE] → {vp:.6f}")

# -----------------------------------------------------------------------------
#  REGISTER
# -----------------------------------------------------------------------------
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)
