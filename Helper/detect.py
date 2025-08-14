
import bpy
import math
import time

__all__ = [
    "perform_marker_detection",
    "run_detect_adaptive",
    "run_detect_once",
    "CLIP_OT_detect",
    "CLIP_OT_detect_once",
]

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
    space = getattr(context, "space_data", None)
    clip = getattr(space, "clip", None) if space else None
    if clip:
        return clip
    # Fallback: first movieclip
    try:
        for c in bpy.data.movieclips:
            return c
    except Exception:
        pass
    return None

# ---------------------------------------------------------------------------
# Legacy-Helper (API-kompatibel halten)
# ---------------------------------------------------------------------------

def perform_marker_detection(clip, tracking, threshold, margin_base, min_distance_base):
    """
    Führt detect_features mit skalierten Parametern aus
    und liefert die Anzahl selektierter Tracks zurück (Legacy-Kontrakt).
    """
    # einfache Skalierung (stabil gegenüber sehr kleinen Thresholds)
    factor = max(0.25, min(4.0, float(threshold) * 10.0))
    margin = max(1, int(margin_base * factor))
    min_distance = max(1, int(min_distance_base * factor))

    try:
        bpy.ops.clip.detect_features(
            margin=int(margin),
            min_distance=int(min_distance),
            threshold=float(threshold),
        )
    except Exception as ex:
        # im Fehlerfall keine Selektion
        print(f"[Detect] detect_features exception: {ex}")
        return 0

    return sum(1 for t in tracking.tracks if getattr(t, "select", False))

# ---------------------------------------------------------------------------
# Nicht-modale, einmalige Detection – Funktions-API (für Helper-Aufrufer)
# ---------------------------------------------------------------------------

def _compute_bounds(scene, image_width, detection_threshold, marker_adapt, min_marker, max_marker):
    # Threshold
    if detection_threshold is None or detection_threshold < 0.0:
        detection_threshold = float(
            scene.get("last_detection_threshold",
                      float(getattr(getattr(scene, "tracking_settings", None), "default_correlation_min", 0.75)))
        )
    detection_threshold = float(max(1e-4, min(1.0, detection_threshold)))

    # adapt / bounds
    if marker_adapt is None or marker_adapt < 0:
        marker_adapt = int(scene.get("marker_adapt", int(scene.get("marker_basis", 20))))
    marker_adapt = int(max(1, marker_adapt))
    basis_for_bounds = int(max(1, int(marker_adapt * 1.1)))

    if min_marker is None or min_marker < 0:
        min_marker = int(max(1, int(basis_for_bounds * 0.9)))
    if max_marker is None or max_marker < 0:
        max_marker = int(max(2, int(basis_for_bounds * 1.1)))

    # bases
    margin_base = max(1, int(image_width * 0.025))
    min_distance_base = max(1, int(image_width * 0.05))

    return detection_threshold, marker_adapt, min_marker, max_marker, margin_base, min_distance_base

def run_detect_once(context, *, start_frame=None, detection_threshold=-1.0,
                    marker_adapt=-1, min_marker=-1, max_marker=-1,
                    margin_base=-1, min_distance_base=-1,
                    close_dist_rel=0.01, handoff_to_pipeline=False):
    """
    Führt einen synchronen, einfachen Detect-Pass aus und liefert ein Ergebnis-Dict.
    KEINE nachgelagerte Pipeline-Steuerung. Side-Effects minimiert.
    """
    clip = _resolve_clip(context)
    if clip is None:
        return {"status": "failed", "reason": "no_clip"}

    tracking = clip.tracking
    scene = context.scene
    image_width = int(clip.size[0])

    # Parameter vorbereiten
    thr, adapt, mn, mx, mb, mdb = _compute_bounds(scene, image_width, detection_threshold, marker_adapt, min_marker, max_marker)
    if margin_base is not None and margin_base >= 0:
        mb = int(margin_base)
    if min_distance_base is not None and min_distance_base >= 0:
        mdb = int(min_distance_base)

    # Frame setzen
    if start_frame is not None:
        try:
            scene.frame_set(int(start_frame))
        except Exception:
            pass

    frame = int(scene.frame_current)
    w, h = clip.size

    # Vorherige neue Tracks entfernen (inter-run cleanup)
    prev_names = set(scene.get("detect_prev_names", []) or [])
    if prev_names:
        _remove_tracks_by_name(tracking, prev_names)
        scene["detect_prev_names"] = []

    # Snapshot vor Detect
    initial_names = {t.name for t in tracking.tracks}
    existing_positions = _collect_existing_positions(tracking, frame, w, h)

    # Detect
    _deselect_all(tracking)
    count_sel = perform_marker_detection(clip, tracking, thr, mb, mdb)

    # Depsgraph "anticken"
    try:
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
    except Exception:
        pass

    # Neue Tracks ermitteln
    tracks = tracking.tracks
    new_tracks = [t for t in tracks if t.name not in initial_names]

    # Near-Duplicate-Filter
    rel = float(close_dist_rel) if (close_dist_rel is not None and close_dist_rel > 0.0) else 0.01
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
                    if (dx*dx + dy*dy) < thr2:
                        close_tracks.append(tr)
                        break

    # nahe/doppelte Tracks löschen
    if close_tracks:
        for t in tracks:
            t.select = False
        for t in close_tracks:
            t.select = True
        try:
            bpy.ops.clip.delete_track()
        except Exception:
            _remove_tracks_by_name(tracking, {t.name for t in close_tracks})

    # finale neue Tracks
    close_set = set(close_tracks)
    cleaned_tracks = [t for t in new_tracks if t not in close_set]
    anzahl_neu = len(cleaned_tracks)

    if anzahl_neu < int(mn) or anzahl_neu > int(mx):
        # neu erzeugte wieder entfernen
        if cleaned_tracks:
            for t in tracks:
                t.select = False
            for t in cleaned_tracks:
                t.select = True
            try:
                bpy.ops.clip.delete_track()
            except Exception:
                _remove_tracks_by_name(tracking, {t.name for t in cleaned_tracks})

        # threshold anpassen und zurückmelden (einmaliger Versuch)
        safe_adapt = max(int(adapt), 1)
        new_thr = max(float(thr) * ((anzahl_neu + 0.1) / float(safe_adapt)), 1e-4)
        scene["last_detection_threshold"] = float(new_thr)
        return {"status": "retry", "new_tracks": anzahl_neu, "threshold": float(new_thr)}

    # Erfolg – Namen merken für inter-run cleanup
    try:
        scene["detect_prev_names"] = [t.name for t in cleaned_tracks]
    except Exception:
        scene["detect_prev_names"] = []

    # bewusst keine Pipeline-Flags setzen
    scene["last_detection_threshold"] = float(thr)
    return {"status": "success", "new_tracks": anzahl_neu, "threshold": float(thr)}

def run_detect_adaptive(context, **kwargs):
    """Wiederholt run_detect_once() bis Erfolg oder max. Versuche."""
    max_attempts = int(kwargs.pop("max_attempts", 10))
    attempt = 0
    last = None
    while attempt < max_attempts:
        last = run_detect_once(context, **kwargs)
        if last.get("status") == "success":
            return last
        attempt += 1
        if last.get("status") == "retry":
            lt = last.get("threshold")
            if lt is not None:
                kwargs["detection_threshold"] = float(lt)
    return last if last else {"status": "failed", "reason": "no_attempt"}

    def poll(cls, context):
        return (
            context.area and
            context.area.type == "CLIP_EDITOR" and
            getattr(context.space_data, "clip", None)
        )

    def execute(self, context):
        scene = context.scene
        scene["detect_status"] = "pending"

        # Guard: kein paralleler Pipeline-Run (optional)
        if scene.get("tracking_pipeline_active", False):
            scene["detect_status"] = "failed"
            return {'CANCELLED'}

        self.clip = getattr(context.space_data, "clip", None)
        if self.clip is None:
            scene["detect_status"] = "failed"
            return {'CANCELLED'}

        self.tracking = self.clip.tracking
        settings = self.tracking.settings
        image_width = int(self.clip.size[0])

        # --- Threshold-Start ---
        if self.detection_threshold >= 0.0:
            self.detection_threshold = float(self.detection_threshold)
        else:
            self.detection_threshold = float(
                scene.get("last_detection_threshold",
                          float(getattr(settings, "default_correlation_min", 0.75)))
            )

        # --- marker_adapt / Bounds ---
        if self.marker_adapt >= 0:
            adapt = int(self.marker_adapt)
        else:
            adapt = int(scene.get("marker_adapt", 20))
        self.marker_adapt = adapt

        basis = int(scene.get("marker_basis", max(adapt, 20)))
        basis_for_bounds = int(self.marker_adapt * 1.1) if self.marker_adapt > 0 else int(basis)

        if self.min_marker >= 0:
            self.min_marker = int(self.min_marker)
        else:
            self.min_marker = int(basis_for_bounds * 0.9)

        if self.max_marker >= 0:
            self.max_marker = int(self.max_marker)
        else:
            self.max_marker = int(basis_for_bounds * 1.1)

        # --- Bases ---
        self.margin_base = self.margin_base if self.margin_base >= 0 else max(1, int(image_width * 0.025))
        self.min_distance_base = self.min_distance_base if self.min_distance_base >= 0 else max(1, int(image_width * 0.05))

        # --- Frame optional setzen ---
        if self.frame and self.frame > 0:
            try:
                scene.frame_set(int(self.frame))
            except Exception:
                pass

        # --- Cleanup der Tracks aus dem VORHERIGEN Run ---
        prev_names = set(scene.get("detect_prev_names", []) or [])
        if prev_names:
            _remove_tracks_by_name(self.tracking, prev_names)
            scene["detect_prev_names"] = []

        # Iterationsverwaltung
        self.attempt = 0
        self.max_attempts = 20
        self.state = self._STATE_DETECT

        _deselect_all(self.tracking)

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.01, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        scene = context.scene

        if self.state == self._STATE_DETECT:
            if self.attempt == 0:
                _deselect_all(self.tracking)

            self.frame = int(scene.frame_current)

            # Snapshots vor Detect
            tracks = self.tracking.tracks
            self.width, self.height = self.clip.size
            w, h = self.width, self.height

            self.existing_positions = _collect_existing_positions(self.tracking, self.frame, w, h)
            self.initial_track_names = {t.name for t in tracks}
            self._len_before = len(tracks)

            # Detect
            perform_marker_detection(
                self.clip,
                self.tracking,
                float(self.detection_threshold),
                int(self.margin_base),
                int(self.min_distance_base),
            )

            # Redraw forcieren
            try:
                bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
            except Exception:
                pass

            # Weiter in WAIT
            self.state = self._STATE_WAIT
            return {'PASS_THROUGH'}

        if self.state == self._STATE_WAIT:
            tracks = self.tracking.tracks
            if len(tracks) != self._len_before:
                current_names = {t.name for t in tracks}
                if current_names != self.initial_track_names:
                    self.state = self._STATE_PROC
            return {'PASS_THROUGH'}

        if self.state == self._STATE_PROC:
            tracks = self.tracking.tracks
            w, h = self.width, self.height

            # Neue Tracks dieses Versuchs
            new_tracks = [t for t in tracks if t.name not in self.initial_track_names]

            # Near-Duplicate-Filter (px, rel. zur Breite)
            rel = self.close_dist_rel if self.close_dist_rel > 0.0 else 0.01
            distance_px = max(1, int(self.width * rel))
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

            # Zu nahe neue Tracks löschen
            if close_tracks:
                for t in tracks:
                    t.select = False
                for t in close_tracks:
                    t.select = True
                try:
                    bpy.ops.clip.delete_track()
                except Exception:
                    _remove_tracks_by_name(self.tracking, {t.name for t in close_tracks})

            # Bereinigte neue Tracks
            close_set = set(close_tracks)
            cleaned_tracks = [t for t in new_tracks if t not in close_set]
            anzahl_neu = len(cleaned_tracks)

            # Zielkorridor prüfen
            if anzahl_neu < self.min_marker or anzahl_neu > self.max_marker:
                # Alle neu-erzeugten (bereinigten) Tracks dieses Versuchs wieder entfernen
                if cleaned_tracks:
                    for t in tracks:
                        t.select = False
                    for t in cleaned_tracks:
                        t.select = True
                    try:
                        bpy.ops.clip.delete_track()
                    except Exception:
                        _remove_tracks_by_name(self.tracking, {t.name for t in cleaned_tracks})

                # Threshold adaptieren (proportional zur Abweichung vom Ziel)
                safe_adapt = max(self.marker_adapt, 1)
                self.detection_threshold = max(
                    float(self.detection_threshold) * ((anzahl_neu + 0.1) / float(safe_adapt)),
                    1e-4,
                )
                scene["last_detection_threshold"] = float(self.detection_threshold)

                self.attempt += 1
                if self.attempt >= self.max_attempts:
                    scene["detect_status"] = "failed"
                    if self._timer is not None:
                        context.window_manager.event_timer_remove(self._timer)
                    return {'FINISHED'}

                # Nächster Versuch
                self.state = self._STATE_DETECT
                return {'PASS_THROUGH'}

            # Erfolg: final erzeugte Tracks für nächsten Run merken (inter-run cleanup)
            try:
                scene["detect_prev_names"] = [t.name for t in cleaned_tracks]
            except Exception:
                scene["detect_prev_names"] = []

            # --- Handoff steuern: Default = KEIN Pipeline-Start ---
            if self.handoff_to_pipeline:
                scene["detect_status"] = "success"
                scene["pipeline_do_not_start"] = False
            else:
                scene["detect_status"] = "standalone_success"
                scene["pipeline_do_not_start"] = True

            if self._timer is not None:
                context.window_manager.event_timer_remove(self._timer)
            return {'FINISHED'}

        return {'PASS_THROUGH'}

    def cancel(self, context):
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
