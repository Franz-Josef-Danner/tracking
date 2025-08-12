import bpy
import math

def _deselect_all(tracking):
    for t in tracking.tracks:
        t.select = False

def _get_marker_xy_at_frame(track, frame, w, h):
    m = track.markers.find_frame(frame, exact=True)
    if not m or m.mute:
        return None
    return (m.co[0] * w, m.co[1] * h)

def _compute_margin_distance(threshold: float, margin_base: int, min_distance_base: int):
    # Identische Skalierung wie zuvor: factor = log10(threshold * 1e6) / 6
    factor = math.log10(max(threshold, 1e-6) * 1e6) / 6.0
    margin = max(1, int(margin_base * factor))
    min_distance = max(1, int(min_distance_base * factor))
    return margin, min_distance

def _remove_tracks_by_name(tracking, names_to_remove):
    """Entfernt Tracks hart per Datablock-API (robust gegen Operator-Fehler)."""
    removed = 0
    for t in list(tracking.tracks):
        if t.name in names_to_remove:
            try:
                tracking.tracks.remove(t)
                removed += 1
            except Exception:
                pass
    return removed

def _detect_once_core(clip, frame, threshold, margin_base, min_distance_base,
                      existing_positions, close_dist_rel):
    """
    Führt genau EINE detect_features-Runde aus, bereinigt zu nahe Neue
    und liefert (new_track_names, deleted_close_count).
    """
    tracking = clip.tracking
    w, h = clip.size

    margin, min_distance = _compute_margin_distance(threshold, margin_base, min_distance_base)

    initial_names = {t.name for t in tracking.tracks}
    _deselect_all(tracking)

    bpy.ops.clip.detect_features(
        margin=margin,
        min_distance=min_distance,
        threshold=float(threshold)
    )

    tracks = tracking.tracks
    current_names = {t.name for t in tracks}
    new_names = list(current_names - initial_names)

    wpx = w  # für Lesbarkeit
    close_px = max(0, int(close_dist_rel * wpx))
    thr2 = float(close_px * close_px)

    close_names = set()
    if existing_positions and new_names and close_px > 0:
        for t in (tr for tr in tracks if tr.name in new_names):
            xy = _get_marker_xy_at_frame(t, frame, w, h)
            if not xy:
                continue
            x, y = xy
            for ex, ey in existing_positions:
                dx = x - ex
                dy = y - ey
                if (dx * dx + dy * dy) < thr2:
                    close_names.add(t.name)
                    break

    deleted_close = 0
    if close_names:
        deleted_close += _remove_tracks_by_name(tracking, close_names)
        # Refresh Name-Liste nach Löschung
        new_names = [n for n in new_names if n not in close_names]

    _deselect_all(tracking)
    for t in tracks:
        if t.name in new_names:
            t.select = True

    return new_names, deleted_close

class CLIP_OT_detect_once(bpy.types.Operator):
    """Einmalige Marker-Platzierung mit adaptiver Threshold-Steuerung bis Zielanzahl erreicht ist."""
    bl_idname = "clip.detect_once"
    bl_label  = "Detect Once (Adaptive)"
    bl_description = "Platziert Marker adaptiv (Threshold-Steuerung) bis die Zielanzahl erreicht ist"

    # Eingaben
    detection_threshold: bpy.props.FloatProperty(
        name="Start-Threshold", default=0.75, min=1e-6, soft_max=1.0
    )
    marker_adapt: bpy.props.IntProperty(
        name="Marker Adapt (Zielzentrum)", default=20, min=0
    )
    min_marker: bpy.props.IntProperty(
        name="Min Marker", default=18, min=0
    )
    max_marker: bpy.props.IntProperty(
        name="Max Marker", default=22, min=0
    )
    frame: bpy.props.IntProperty(
        name="Frame", default=1, min=0
    )

    margin_base: bpy.props.IntProperty(
        name="Margin Base (px)", default=-1
    )
    min_distance_base: bpy.props.IntProperty(
        name="Min Dist Base (px)", default=-1
    )

    close_dist_rel: bpy.props.FloatProperty(
        name="Close Dist (rel. width)", default=0.01, min=0.0, soft_max=0.1
    )

    max_iters: bpy.props.IntProperty(
        name="Max Iterationen", default=8, min=1, max=32
    )
    thr_min: bpy.props.FloatProperty(
        name="Threshold Min", default=1e-6, min=1e-8, soft_max=0.5
    )
    thr_max: bpy.props.FloatProperty(
        name="Threshold Max", default=1.0, min=1e-6, max=1.0
    )
    use_binary_search: bpy.props.BoolProperty(
        name="Binärsuche", description="Nutze Binärsuche zwischen thr_min/thr_max statt rein multiplikativ",
        default=True
    )

    @classmethod
    def poll(cls, context):
        return (
            context.area
            and context.area.type == "CLIP_EDITOR"
            and getattr(context.space_data, "clip", None) is not None
        )

    def execute(self, context):
        scene = context.scene
        scene["detect_status"] = "pending"

        clip = context.space_data.clip
        tracking = clip.tracking
        w, h = clip.size

        prev_names = set(context.scene.get("detect_prev_names", []) or [])
        if prev_names:
            try:
                _remove_tracks_by_name(tracking, prev_names)
            except Exception:
                pass
            context.scene["detect_prev_names"] = []
            
        margin_base = self.margin_base if self.margin_base >= 0 else int(w * 0.025)
        min_distance_base = self.min_distance_base if self.min_distance_base >= 0 else int(w * 0.05)

        existing_positions = []
        for t in tracking.tracks:
            xy = _get_marker_xy_at_frame(t, self.frame, w, h)
            if xy:
                existing_positions.append(xy)

        initial_names = {t.name for t in tracking.tracks}
        initial_count = len(tracking.tracks)

        lo = float(self.thr_min)
        hi = float(self.thr_max)
        cur = float(min(max(self.detection_threshold, lo), hi))

        last_new_names = []
        total_deleted_close = 0
        status = "out_of_bounds"

        for it in range(self.max_iters):
            if last_new_names:
                _remove_tracks_by_name(tracking, set(last_new_names))
                last_new_names = []

            try:
                new_names, deleted_close = _detect_once_core(
                    clip=clip,
                    frame=self.frame,
                    threshold=cur,
                    margin_base=margin_base,
                    min_distance_base=min_distance_base,
                    existing_positions=existing_positions,
                    close_dist_rel=self.close_dist_rel
                )
            except Exception as e:
                scene["detect_status"] = "failed"
                scene["detect_result"] = {
                    "error": f"detect_features failed at iter {it}: {e}",
                    "iter": it,
                    "threshold": float(cur),
                    "new_total": 0,
                    "deleted_close": int(total_deleted_close),
                }
                self.report({'ERROR'}, f"Detect failed at iter {it}: {e}")
                return {'CANCELLED'}

            last_new_names = new_names
            new_total = len(new_names)
            total_deleted_close += deleted_close

            if self.min_marker <= new_total <= self.max_marker:
                status = "success"
                break

            if self.use_binary_search:
                if new_total < self.min_marker:
                    hi = cur
                    cur = max(lo, (lo + cur) * 0.5)
                elif new_total > self.max_marker:
                    lo = cur
                    cur = min(hi, (cur + hi) * 0.5)
            else:
                if new_total < self.min_marker:
                    cur *= 0.7  # mehr Features
                else:
                    cur *= 1.3  # weniger Features
                cur = min(max(cur, lo), hi)

        within = self.min_marker <= len(last_new_names) <= self.max_marker
        scene["detect_result"] = {
            "frame": int(self.frame),
            "threshold": float(cur),
            "marker_adapt": int(self.marker_adapt),
            "min_marker": int(self.min_marker),
            "max_marker": int(self.max_marker),
            "initial_tracks": int(initial_count),
            "added_raw": int(len(last_new_names) + total_deleted_close),  # vor Close-Delete
            "deleted_close": int(total_deleted_close),
            "new_total": int(len(last_new_names)),
            "within_bounds": bool(within),
            "iters": int(min(self.max_iters, it + 1)),
            "search_mode": "binary" if self.use_binary_search else "multiplicative",
        }
        scene["detect_status"] = "success" if within else "out_of_bounds"

        try:
            context.scene["detect_prev_names"] = list(last_new_names)
        except Exception:
            pass

        try:
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        except Exception:
            pass
        return {'FINISHED'}


# --- Register ----------------------------------------------------------------

def register():
    bpy.utils.register_class(CLIP_OT_detect_once)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_detect_once)

if __name__ == "__main__":
    register()

# --- Backward-compatibility shim --------------------------------------------
# Export beibehalten, damit: from .detect import perform_marker_detection funktioniert
__all__ = [
    "CLIP_OT_detect_once",
    "perform_marker_detection",
]

def perform_marker_detection(
    context,
    *,
    frame: int,
    marker_adapt: int,
    marker_min: int,
    marker_max: int,
    detection_threshold: float | None = None,
    thr_min: float = 1e-6,
    thr_max: float = 1.0,
    max_iters: int = 8,
    use_binary_search: bool = True,
    margin_base: int = -1,
    min_distance_base: int = -1,
    close_dist_rel: float = 0.01,
):
    """
    Kompatibilitäts-Wrapper für ältere Call-Sites.
    Startet CLIP_OT_detect_once und liefert scene['detect_result'] zurück.
    """
    # Sinnvolle Defaults aus alter Pipeline ableiten
    if detection_threshold is None:
        detection_threshold = 0.75

    # Sicherstellen, dass wir im CLIP_EDITOR laufen
    area = region = space = None
    win = context.window
    if win and win.screen:
        for a in win.screen.areas:
            if a.type == 'CLIP_EDITOR':
                for r in a.regions:
                    if r.type == 'WINDOW':
                        area, region, space = a, r, a.spaces.active
                        break
                if area:
                    break

    # Operator im gültigen Override ausführen
    if area and region and space:
        with context.temp_override(area=area, region=region, space_data=space):
            res = bpy.ops.clip.detect_once(
                frame=frame,
                marker_adapt=marker_adapt,
                min_marker=marker_min,
                max_marker=marker_max,
                detection_threshold=float(detection_threshold),
                thr_min=float(thr_min),
                thr_max=float(thr_max),
                max_iters=int(max_iters),
                use_binary_search=bool(use_binary_search),
                margin_base=int(margin_base),
                min_distance_base=int(min_distance_base),
                close_dist_rel=float(close_dist_rel),
            )
    else:
        # Fallback: ohne Override (falls poll() greift)
        res = bpy.ops.clip.detect_once(
            frame=frame,
            marker_adapt=marker_adapt,
            min_marker=marker_min,
            max_marker=marker_max,
            detection_threshold=float(detection_threshold),
            thr_min=float(thr_min),
            thr_max=float(thr_max),
            max_iters=int(max_iters),
            use_binary_search=bool(use_binary_search),
            margin_base=int(margin_base),
            min_distance_base=int(min_distance_base),
            close_dist_rel=float(close_dist_rel),
        )

    # Einheitliche Rückgabe wie früher: Dict aus scene["detect_result"]
    # (bei Fehlern None/KeyError robust handhaben)
    try:
        return context.scene.get("detect_result", None)
    except Exception:
        return None
