import bpy
import math
import time
from contextlib import contextmanager

__all__ = ["perform_marker_detection", "CLIP_OT_detect", "CLIP_OT_detect_once"]

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _deselect_all(tracking):
    for t in tracking.tracks:
        t.select = False

def _remove_tracks_by_name(tracking, names_to_remove):
    """Robustes Entfernen von Tracks per Datablock-API (ohne UI-Kontext)."""
    if not names_to_remove:
        return 0
    removed = 0
    for t in list(tracking.tracks):
        if t.name in names_to_remove:
            try:
                tracking.tracks.remove(t)
                removed += 1
            except Exception:
                pass
    return removed

def _collect_existing_positions(tracking, frame, w, h):
    """Positionen existierender Marker (x,y in px) im Ziel-Frame sammeln."""
    out = []
    for t in tracking.tracks:
        m = t.markers.find_frame(frame, exact=True)
        if m and not m.mute:
            out.append((m.co[0] * w, m.co[1] * h))
    return out

def _resolve_clip(context):
    """Aktiven MovieClip ermitteln (Space → Clip, sonst erster Clip im File)."""
    space = getattr(context, "space_data", None)
    clip = getattr(space, "clip", None) if space else None
    if clip:
        return clip
    try:
        for c in bpy.data.movieclips:
            return c
    except Exception:
        pass
    return None

# ---------------------------------------------
# UI-Context Guard (sicherer CLIP_EDITOR-Kontext)
# ---------------------------------------------

def _find_clip_area(win):
    if not win or not getattr(win, "screen", None):
        return None, None
    for area in win.screen.areas:
        if area.type == "CLIP_EDITOR":
            reg = next((r for r in area.regions if r.type == "WINDOW"), None)
            if reg:
                return area, reg
    return None, None

@contextmanager
def _ensure_clip_context(ctx, clip=None, *, allow_area_switch=True):
    """
    Sichert einen gültigen CLIP_EDITOR-Kontext (area/region/space_data, clip gesetzt).
    Setzt Space in TRACKING-Mode. Greift nur lokal; vermeidet Seiteneffekte.
    """
    win = getattr(ctx, "window", None)
    area, region = _find_clip_area(win)
    switched = False
    old_type = None

    if area is None and allow_area_switch and win and getattr(win, "screen", None):
        try:
            area = win.screen.areas[0]
            old_type = area.type
            area.type = "CLIP_EDITOR"
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            switched = True
        except Exception:
            area = None
            region = None

    override = {}
    if area and region:
        override["area"] = area
        override["region"] = region
        override["space_data"] = area.spaces.active
        sd = area.spaces.active
        # Clip setzen (falls möglich)
        if clip and getattr(sd, "clip", None) is None:
            try:
                sd.clip = clip
            except Exception:
                pass
        # TRACKING-Mode erzwingen
        if hasattr(sd, "mode"):
            try:
                sd.mode = 'TRACKING'
            except Exception:
                pass

    try:
        if override:
            with ctx.temp_override(**override):
                yield
        else:
            yield
    finally:
        if switched:
            try:
                area.type = old_type
            except Exception:
                pass

# ---------------------------------------------
# Harte, verifizierte Löschung
# ---------------------------------------------

def _delete_tracks_strict(context, clip, tracks_to_delete, *, use_override=True):
    """
    Löscht Tracks robust:
      1) Versuch via Operator (mit gültigem CLIP-Kontext)
      2) Harte Datablock-Löschung per Name für alle Survivors
      3) Verifikation + UI-Refresh
    Rückgabe: Liste überlebender Track-Namen (sollte i.d.R. leer sein)
    """
    tracking = clip.tracking
    names = {t.name for t in tracks_to_delete if t}
    if not names:
        return []

    # 1) Operator-Versuch
    with _ensure_clip_context(context, clip=clip, allow_area_switch=use_override):
        try:
            for t in tracking.tracks:
                t.select = False
            for t in tracking.tracks:
                if t.name in names:
                    t.select = True
            res = bpy.ops.clip.delete_track()
            # res ist normalerweise ein Set {'FINISHED'} | {'CANCELLED'}
        except Exception:
            # Operator fehlgeschlagen – wir gehen direkt auf Datablock-Löschung
            pass

    # 2) Harte Löschung für alle verbleibenden Namen
    survivors = [t.name for t in tracking.tracks if t.name in names]
    if survivors:
        _remove_tracks_by_name(tracking, set(survivors))
        # Verifikation wiederholen
        survivors = [t.name for t in tracking.tracks if t.name in names]

    # 3) UI-Refresh (best effort)
    try:
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
    except Exception:
        pass

    return survivors

# ---------------------------------------------------------------------------
# Legacy-Helper (API-kompatibel halten)
# ---------------------------------------------------------------------------

def perform_marker_detection(clip, tracking, threshold, margin_base, min_distance_base):
    """
    Führt detect_features mit skalierten Parametern aus
    und liefert die Anzahl selektierter Tracks zurück (Legacy-Kontrakt).
    """
    factor = math.log10(max(threshold, 1e-6) * 1e6) / 6.0
    margin = max(1, int(margin_base * factor))
    min_distance = max(1, int(min_distance_base * factor))

    try:
        bpy.ops.clip.detect_features(
            margin=int(margin),
            min_distance=int(min_distance),
            threshold=float(threshold),
        )
    except Exception as ex:
        print(f"[Detect] detect_features exception: {ex}")
        return 0

    return sum(1 for t in tracking.tracks if getattr(t, "select", False))

# ---------------------------------------------------------------------------
# Gemeinsame Bound-/Parameteraufbereitung
# ---------------------------------------------------------------------------

def _compute_bounds(context, clip, detection_threshold, marker_adapt, min_marker, max_marker):
    scene = context.scene
    tracking = clip.tracking
    settings = tracking.settings
    image_width = int(clip.size[0])

    # Threshold-Start (Scene.last_detection_threshold → Settings.default)
    if detection_threshold is not None and detection_threshold >= 0.0:
        thr = float(detection_threshold)
    else:
        thr = float(scene.get("last_detection_threshold",
                              float(getattr(settings, "default_correlation_min", 0.75))))
    thr = float(max(1e-4, min(1.0, thr)))

    # marker_adapt / Bounds
    if marker_adapt is not None and marker_adapt >= 0:
        adapt = int(marker_adapt)
    else:
        adapt = int(scene.get("marker_adapt", 20))
    adapt = max(1, adapt)

    basis = int(scene.get("marker_basis", max(adapt, 20)))
    basis_for_bounds = int(adapt * 1.1) if adapt > 0 else int(basis)

    if min_marker is not None and min_marker >= 0:
        mn = int(min_marker)
    else:
        mn = int(max(1, int(basis_for_bounds * 0.9)))

    if max_marker is not None and max_marker >= 0:
        mx = int(max_marker)
    else:
        mx = int(max(2, int(basis_for_bounds * 1.1)))

    # Bases für margin/min_distance
    margin_base = max(1, int(image_width * 0.025))
    min_distance_base = max(1, int(image_width * 0.05))

    return thr, adapt, mn, mx, margin_base, min_distance_base

# ---------------------------------------------------------------------------
# Operator (Modal) – adaptiver Detect, inter-run Cleanup
# ---------------------------------------------------------------------------

class CLIP_OT_detect(bpy.types.Operator):
    bl_idname = "clip.detect"
    bl_label = "Place Marker (Adaptive)"
    bl_description = "Modaler Detect-Zyklus mit interner Threshold-Anpassung und inter-run Cleanup"

    _timer = None
    # Arbeitszustände
    _STATE_DETECT = "DETECT"
    _STATE_WAIT   = "WAIT"
    _STATE_PROC   = "PROCESS"

    # --- optionale Aufruf-Argumente (kompatibel zu älteren Call-Sites) ---
    detection_threshold: bpy.props.FloatProperty(
        name="Detection Threshold (opt.)",
        description="Optionaler Start-Threshold. <0 nutzt Scene/Settings",
        default=-1.0, min=-1.0, max=1.0
    )
    marker_adapt: bpy.props.IntProperty(
        name="Marker Adapt (opt.)",
        description="Optionales Zielzentrum. <0 nutzt Scene.marker_adapt",
        default=-1, min=-1
    )
    min_marker: bpy.props.IntProperty(
        name="Min Marker (opt.)",
        default=-1, min=-1
    )
    max_marker: bpy.props.IntProperty(
        name="Max Marker (opt.)",
        default=-1, min=-1
    )
    margin_base: bpy.props.IntProperty(
        name="Margin Base (px, opt.)",
        default=-1, min=-1
    )
    min_distance_base: bpy.props.IntProperty(
        name="Min Distance Base (px, opt.)",
        default=-1, min=-1
    )
    close_dist_rel: bpy.props.FloatProperty(
        name="Near-Duplicate Dist (rel. Bildbreite)",
        default=0.01, min=0.0, max=1.0
    )
    max_attempts: bpy.props.IntProperty(
        name="Max Attempts",
        default=10, min=1
    )
    use_override: bpy.props.BoolProperty(
        name="Allow Area Switch",
        description="CLIP_EDITOR-Override/Wechsel erlauben",
        default=True
    )

    # interne Laufvariablen
    def _setup_run(self, context):
        self.clip = _resolve_clip(context)
        if self.clip is None:
            self.report({'ERROR'}, "Kein MovieClip gefunden.")
            return False

        self.scene = context.scene
        self.tracking = self.clip.tracking
        self.w, self.h = self.clip.size
        self.frame = int(self.scene.frame_current)

        # Bounds + Parameter
        thr, adapt, mn, mx, mb, mdb = _compute_bounds(
            context, self.clip,
            self.detection_threshold, self.marker_adapt,
            self.min_marker, self.max_marker
        )
        if self.margin_base is not None and self.margin_base >= 0:
            mb = int(self.margin_base)
        if self.min_distance_base is not None and self.min_distance_base >= 0:
            mdb = int(self.min_distance_base)

        self.detection_threshold = float(thr)
        self.marker_adapt = int(adapt)
        self.min_marker = int(mn)
        self.max_marker = int(mx)
        self.margin_base = int(mb)
        self.min_distance_base = int(mdb)

        # Inter-run Cleanup von vorherigen Versuchen
        prev_names = set(self.scene.get("detect_prev_names", []) or [])
        if prev_names:
            _remove_tracks_by_name(self.tracking, prev_names)
            self.scene["detect_prev_names"] = []

        # Snapshot vor Detect
        _deselect_all(self.tracking)
        self.initial_track_names = {t.name for t in self.tracking.tracks}
        self.existing_positions = _collect_existing_positions(self.tracking, self.frame, self.w, self.h)

        # Zustände
        self.attempt = 0
        self.state = self._STATE_DETECT
        self.scene["detect_status"] = "running"
        return True

    def _detect_pass(self, context):
        # Detect in sicherem CLIP-Kontext
        with _ensure_clip_context(context, clip=self.clip, allow_area_switch=self.use_override):
            perform_marker_detection(
                self.clip, self.tracking,
                float(self.detection_threshold),
                int(self.margin_base), int(self.min_distance_base)
            )
            # UI-Refresh
            try:
                bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
            except Exception:
                pass
        self.state = self._STATE_WAIT

    def _process_pass(self, context):
        tracks = self.tracking.tracks
        w, h = self.w, self.h

        # Neue Tracks dieses Versuchs
        new_tracks = [t for t in tracks if t.name not in self.initial_track_names]

        # Near-Duplicate-Filter (px, rel. zur Breite)
        rel = self.close_dist_rel if self.close_dist_rel > 0.0 else 0.01
        distance_px = max(1, int(self.w * rel))
        thr2 = float(distance_px * distance_px)

        close_tracks = []
        existing = self.existing_positions
        if existing and new_tracks:
            for tr in new_tracks:
                m = tr.markers.find_frame(self.frame, exact=True)
                if m and not m.mute:
                    x = m.co[0] * w; y = m.co[1] * h
                    for ex, ey in existing:
                        dx = x - ex; dy = y - ey
                        if (dx * dx + dy * dy) < thr2:
                            close_tracks.append(tr)
                            break

        # Zu nahe neue Tracks löschen – robust
        if close_tracks:
            _delete_tracks_strict(context, self.clip, close_tracks, use_override=self.use_override)

        # Bereinigte neue Tracks
        close_set = set(close_tracks)
        cleaned_tracks = [t for t in new_tracks if t not in close_set]
        anzahl_neu = len(cleaned_tracks)

        # Zielkorridor prüfen
        if anzahl_neu < self.min_marker or anzahl_neu > self.max_marker:
            # Alle neu-erzeugten (bereinigten) Tracks dieses Versuchs wieder entfernen – robust
            if cleaned_tracks:
                survivors = _delete_tracks_strict(context, self.clip, cleaned_tracks, use_override=self.use_override)
                if survivors:
                    # zur Sicherheit für nächsten Run vormerken
                    self.scene["detect_prev_names"] = survivors

            # Threshold adaptieren (proportional zur Abweichung vom Ziel)
            safe_adapt = max(self.marker_adapt, 1)
            self.detection_threshold = max(
                float(self.detection_threshold) * ((anzahl_neu + 0.1) / float(safe_adapt)),
                1e-4,
            )
            self.scene["last_detection_threshold"] = float(self.detection_threshold)

            self.attempt += 1
            if self.attempt >= self.max_attempts:
                self.scene["detect_status"] = "failed"
                context.window_manager.event_timer_remove(self._timer)
                self._timer = None
                self.report({'WARNING'}, "Detect: Max Attempts erreicht (failed).")
                return {'FINISHED'}

            # Nächster Versuch
            self.state = self._STATE_DETECT
            return {'PASS_THROUGH'}

        # Erfolg – Namen für inter-run Cleanup merken
        try:
            self.scene["detect_prev_names"] = [t.name for t in cleaned_tracks]
        except Exception:
            self.scene["detect_prev_names"] = []

        self.scene["detect_status"] = "ready"
        self.scene["last_detection_threshold"] = float(self.detection_threshold)
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        self.report({'INFO'}, f"Detect: {anzahl_neu} neue Marker im Zielkorridor.")
        return {'FINISHED'}

    # --------------- Blender Operator Hooks ---------------

    def modal(self, context, event):
        # ESC: jederzeit abbrechen
        if event.type in {'ESC'}:
            if self._timer:
                context.window_manager.event_timer_remove(self._timer)
                self._timer = None
            self.scene["detect_status"] = "cancelled"
            self.report({'INFO'}, "Detect abgebrochen (ESC).")
            return {'CANCELLED'}

        if event.type == 'TIMER':
            if self.state == self._STATE_DETECT:
                self._detect_pass(context)
                return {'PASS_THROUGH'}

            if self.state == self._STATE_WAIT:
                # kurze Wartephase, dann PROCESS
                self.state = self._STATE_PROC
                return {'PASS_THROUGH'}

            if self.state == self._STATE_PROC:
                return self._process_pass(context)

        return {'PASS_THROUGH'}

    def execute(self, context):
        if not self._setup_run(context):
            return {'CANCELLED'}
        # Timer starten
        self._timer = context.window_manager.event_timer_add(0.05, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        return self.execute(context)

    def cancel(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        try:
            self.scene["detect_status"] = "cancelled"
        except Exception:
            pass
        return {'CANCELLED'}

# ---------------------------------------------------------------------------
# Operator (einmaliger Pass) – synchron, ohne Modalität
# ---------------------------------------------------------------------------

class CLIP_OT_detect_once(bpy.types.Operator):
    bl_idname = "clip.detect_once"
    bl_label = "Place Marker (Once)"
    bl_description = "Einmaliger Detect-Pass mit Near-Duplicate-Filter und Korridor-Check"

    detection_threshold: bpy.props.FloatProperty(
        name="Detection Threshold (opt.)",
        description="Optionaler Start-Threshold. <0 nutzt Scene/Settings",
        default=-1.0, min=-1.0, max=1.0
    )
    marker_adapt: bpy.props.IntProperty(
        name="Marker Adapt (opt.)",
        default=-1, min=-1
    )
    min_marker: bpy.props.IntProperty(
        name="Min Marker (opt.)",
        default=-1, min=-1
    )
    max_marker: bpy.props.IntProperty(
        name="Max Marker (opt.)",
        default=-1, min=-1
    )
    margin_base: bpy.props.IntProperty(
        name="Margin Base (px, opt.)",
        default=-1, min=-1
    )
    min_distance_base: bpy.props.IntProperty(
        name="Min Distance Base (px, opt.)",
        default=-1, min=-1
    )
    close_dist_rel: bpy.props.FloatProperty(
        name="Near-Duplicate Dist (rel. Bildbreite)",
        default=0.01, min=0.0, max=1.0
    )
    use_override: bpy.props.BoolProperty(
        name="Allow Area Switch",
        default=True
    )

    def execute(self, context):
        clip = _resolve_clip(context)
        if clip is None:
            self.report({'ERROR'}, "Kein MovieClip gefunden.")
            return {'CANCELLED'}

        scene = context.scene
        tracking = clip.tracking
        w, h = clip.size
        frame = int(scene.frame_current)

        thr, adapt, mn, mx, mb, mdb = _compute_bounds(
            context, clip,
            self.detection_threshold, self.marker_adapt,
            self.min_marker, self.max_marker
        )
        if self.margin_base is not None and self.margin_base >= 0:
            mb = int(self.margin_base)
        if self.min_distance_base is not None and self.min_distance_base >= 0:
            mdb = int(self.min_distance_base)

        # Inter-run Cleanup
        prev_names = set(scene.get("detect_prev_names", []) or [])
        if prev_names:
            _remove_tracks_by_name(tracking, prev_names)
            scene["detect_prev_names"] = []

        # Snapshot vor Detect
        _deselect_all(tracking)
        initial_names = {t.name for t in tracking.tracks}
        existing_positions = _collect_existing_positions(tracking, frame, w, h)

        with _ensure_clip_context(context, clip=clip, allow_area_switch=self.use_override):
            perform_marker_detection(clip, tracking, float(thr), int(mb), int(mdb))
            try:
                bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
            except Exception:
                pass

            tracks = tracking.tracks
            new_tracks = [t for t in tracks if t.name not in initial_names]

            # Near-Duplicate-Filter
            rel = float(self.close_dist_rel) if (self.close_dist_rel is not None and self.close_dist_rel > 0.0) else 0.01
            distance_px = max(1, int(w * rel))
            thr2 = float(distance_px * distance_px)

            close_tracks = []
            if existing_positions and new_tracks:
                for tr in new_tracks:
                    m = tr.markers.find_frame(frame, exact=True)
                    if m and not m.mute:
                        x = m.co[0] * w; y = m.co[1] * h
                        for ex, ey in existing_positions:
                            dx = x - ex; dy = y - ey
                            if (dx * dx + dy * dy) < thr2:
                                close_tracks.append(tr)
                                break

            if close_tracks:
                _delete_tracks_strict(context, clip, close_tracks, use_override=self.use_override)

            # finale neue Tracks
            close_set = set(close_tracks)
            cleaned_tracks = [t for t in new_tracks if t not in close_set]
            anzahl_neu = len(cleaned_tracks)

            if anzahl_neu < int(mn) or anzahl_neu > int(mx):
                if cleaned_tracks:
                    survivors = _delete_tracks_strict(context, clip, cleaned_tracks, use_override=self.use_override)
                    if survivors:
                        scene["detect_prev_names"] = survivors
                scene["last_detection_threshold"] = float(max(1e-4, thr))
                self.report({'WARNING'}, f"DetectOnce: {anzahl_neu} neue Marker außerhalb Korridor [{mn},{mx}].")
                return {'CANCELLED'}

            try:
                scene["detect_prev_names"] = [t.name for t in cleaned_tracks]
            except Exception:
                scene["detect_prev_names"] = []

        scene["last_detection_threshold"] = float(thr)
        self.report({'INFO'}, f"DetectOnce: {anzahl_neu} neue Marker.")
        return {'FINISHED'}
