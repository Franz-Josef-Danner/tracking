import bpy
import math
import time

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

    bpy.ops.clip.detect_features(
        margin=margin,
        min_distance=min_distance,
        threshold=float(threshold),
    )
    return sum(1 for t in tracking.tracks if getattr(t, "select", False))


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
        description="Optionales Unterlimit. <0 wird aus marker_adapt/basis berechnet",
        default=-1, min=-1
    )
    max_marker: bpy.props.IntProperty(
        name="Max Marker (opt.)",
        description="Optionales Oberlimit. <0 wird aus marker_adapt/basis berechnet",
        default=-1, min=-1
    )
    frame: bpy.props.IntProperty(
        name="Frame (opt.)",
        description="Optionaler Ziel-Frame. 0 nutzt aktuellen Scene-Frame",
        default=0, min=0
    )
    margin_base: bpy.props.IntProperty(
        name="Margin Base (px, opt.)",
        description="<0 → auto (2.5% Bildbreite)",
        default=-1
    )
    min_distance_base: bpy.props.IntProperty(
        name="Min Distance Base (px, opt.)",
        description="<0 → auto (5% Bildbreite)",
        default=-1
    )
    close_dist_rel: bpy.props.FloatProperty(
        name="Close Dist (rel. width, opt.)",
        description="Relative Abstandsschwelle für Duplikat-Filter (0.0–0.1). 0 → Default 0.01",
        default=0.0, min=0.0, max=0.1
    )
    handoff_to_pipeline: bpy.props.BoolProperty(
        name="Handoff to Pipeline",
        description="Bei Erfolg 'success' signalisieren und Main/Pipeline weiterlaufen lassen",
        default=False
    )

    @classmethod
    def poll(cls, context):
        return (
            context.area and
            context.area.type == "CLIP_EDITOR" and
            getattr(context.space_data, "clip", None)
        )

    def execute(self, context):
        scene = context.scene
        scene["detect_status"] = "pending"

        # Guard: kein paralleler Pipeline-Run
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
        basis_for_bounds = int(adapt * 1.1) if adapt > 0 else int(basis)

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
        if self.frame > 0:
            try:
                scene.frame_set(self.frame)
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
        wm.modal_handler_add(self)
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

            # Detect (Legacy-Helper beibehalten)
            perform_marker_detection(
                self.clip,
                self.tracking,
                float(self.detection_threshold),
                int(self.margin_base),
                int(self.min_distance_base),
            )

            # Redraw forcieren, damit RNA/Depsgraph neue Tracks liefern
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)

            # Weiter in WAIT
            self.state = self._STATE_WAIT
            return {'PASS_THROUGH'}

        if self.state == self._STATE_WAIT:
            tracks = self.tracking.tracks
            # Sobald sich die Track-Anzahl ändert, weiter
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
                scene["detect_status"] = "success"            # altes Verhalten: erlaubt Downstream/Pipeline
                scene["pipeline_do_not_start"] = False
            else:
                scene["detect_status"] = "standalone_success" # bewusst kein Trigger-Keyword
                scene["pipeline_do_not_start"] = True         # harte Bremse für Main

            context.window_manager.event_timer_remove(self._timer)
            return {'FINISHED'}

        return {'PASS_THROUGH'}

    def cancel(self, context):
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)


# ---------------------------------------------------------------------------
# Alias für Abwärtskompatibilität: erwarteter Name + erwarteter bl_idname
# ---------------------------------------------------------------------------

class CLIP_OT_detect_once(CLIP_OT_detect):
    """Alias von CLIP_OT_detect – identische Implementierung, anderer Name/ID."""
    bl_idname = "clip.detect_once"
    bl_label  = "Detect Once (Adaptive)"


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

def register():
    bpy.utils.register_class(CLIP_OT_detect)
    bpy.utils.register_class(CLIP_OT_detect_once)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_detect_once)
    bpy.utils.unregister_class(CLIP_OT_detect)

if __name__ == "__main__":
    register()
