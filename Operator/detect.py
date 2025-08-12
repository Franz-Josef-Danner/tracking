import bpy
import math

# --- Backward-Compat: Shim für alte Importe (z.B. optimize_tracking_modal) ---
def perform_marker_detection(clip, tracking, threshold, margin_base, min_distance_base):
    """
    Beibehaltener Legacy-Contract:
    - Skaliert margin/min_distance anhand threshold,
      ident zu früher: factor = log10(threshold * 1e6) / 6
    - Ruft detect_features EINMAL auf
    - Gibt (historisch) die Anzahl selektierter Tracks zurück
    """
    # Schutz gegen ungültige Thresholds
    thr = max(float(threshold), 1e-6)

    factor = math.log10(thr * 1e6) / 6.0
    margin = max(1, int(margin_base * factor))
    min_distance = max(1, int(min_distance_base * factor))

    # Selektion neutralisieren (robuster, falls Call-Sequenzen darauf bauen)
    for t in tracking.tracks:
        t.select = False

    bpy.ops.clip.detect_features(
        margin=margin,
        min_distance=min_distance,
        threshold=thr,
    )

    # Historische Rückgabe: Anzahl selektierter Tracks nach detect
    # (gleiches Verhalten wie vorherige Implementierung)
    selected_count = sum(1 for t in tracking.tracks if t.select)
    return selected_count


def _deselect_all(tracking):
    for t in tracking.tracks:
        t.select = False

def _get_marker_xy_at_frame(track, frame, w, h):
    m = track.markers.find_frame(frame, exact=True)
    if not m or m.mute:
        return None
    return (m.co[0] * w, m.co[1] * h)

def _compute_margin_distance(threshold: float, margin_base: int, min_distance_base: int):
    # identische Skalierung wie zuvor: factor = log10(threshold * 1e6) / 6
    factor = math.log10(max(threshold, 1e-6) * 1e6) / 6.0
    margin = max(1, int(margin_base * factor))
    min_distance = max(1, int(min_distance_base * factor))
    return margin, min_distance

class CLIP_OT_detect_once(bpy.types.Operator):
    """Einmalige Marker-Platzierung mit nachgelagerter Bereinigung; stateless, non-modal."""
    bl_idname = "clip.detect_once"
    bl_label  = "Detect Once (Stateless)"
    bl_description = "Platziert Marker genau einmal mit übergebenen Parametern und bereinigt Duplikate"

    # --- Eingaben aus main ---
    detection_threshold: bpy.props.FloatProperty(
        name="Threshold", default=0.75, min=0.0001, soft_max=1.0
    )
    marker_adapt: bpy.props.IntProperty(
        name="Marker Adapt", default=20, min=0
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

    # Basiswerte; wenn < 0 → automatisch aus Bildbreite
    margin_base: bpy.props.IntProperty(
        name="Margin Base (px)", default=-1
    )
    min_distance_base: bpy.props.IntProperty(
        name="Min Dist Base (px)", default=-1
    )

    # Minimaler Abstand zur Kollisionserkennung (neue vs. bestehende Marker), relativ zur Bildbreite
    close_dist_rel: bpy.props.FloatProperty(
        name="Close Dist (rel. width)", default=0.01, min=0.0, soft_max=0.1
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

        # Auto-Basiswerte aus Bildbreite, falls nicht gesetzt
        margin_base = self.margin_base if self.margin_base >= 0 else int(w * 0.025)
        min_distance_base = self.min_distance_base if self.min_distance_base >= 0 else int(w * 0.05)
        margin, min_distance = _compute_margin_distance(
            self.detection_threshold, margin_base, min_distance_base
        )

        # Bestehende Marker-Positionen im Ziel-Frame sammeln
        existing_positions = []
        for t in tracking.tracks:
            xy = _get_marker_xy_at_frame(t, self.frame, w, h)
            if xy:
                existing_positions.append(xy)

        initial_names = {t.name for t in tracking.tracks}
        initial_count = len(tracking.tracks)

        # Selektion neutralisieren
        _deselect_all(tracking)

        # Detect ausführen (einmalig)
        try:
            bpy.ops.clip.detect_features(
                margin=margin,
                min_distance=min_distance,
                threshold=self.detection_threshold
            )
        except Exception as e:
            scene["detect_status"] = "failed"
            scene["detect_result"] = {
                "error": f"detect_features failed: {e}",
                "new_total": 0,
                "cleaned_total": 0,
                "deleted_close": 0
            }
            self.report({'ERROR'}, f"Detect failed: {e}")
            return {'CANCELLED'}

        # Sichtbar machen (optional)
        try:
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        except Exception:
            pass

        # Neue Tracks bestimmen
        tracks = tracking.tracks
        current_names = {t.name for t in tracks}
        new_tracks = [t for t in tracks if t.name not in initial_names]

        # Zu nahe an bestehenden liegende neue Marker herausfiltern und löschen
        close_px = max(0, int(self.close_dist_rel * w))
        thr2 = float(close_px * close_px)

        close_tracks = []
        if existing_positions and new_tracks and close_px > 0:
            for t in new_tracks:
                xy = _get_marker_xy_at_frame(t, self.frame, w, h)
                if not xy:
                    continue
                x, y = xy
                for ex, ey in existing_positions:
                    dx = x - ex
                    dy = y - ey
                    if (dx * dx + dy * dy) < thr2:
                        close_tracks.append(t)
                        break

        deleted_close = 0
        if close_tracks:
            _deselect_all(tracking)
            for t in close_tracks:
                t.select = True
            try:
                bpy.ops.clip.delete_track()
                deleted_close = len(close_tracks)
            except Exception:
                # Fallback: hartes Entfernen, falls Operator fehlschlägt
                for t in close_tracks:
                    try:
                        tracking.tracks.remove(t)
                        deleted_close += 1
                    except Exception:
                        pass

        # Übrig gebliebene neue Tracks selektieren (optional, hilfreich für UI)
        remaining_new = [t for t in tracks if t.name in (current_names - initial_names) and t not in close_tracks]
        _deselect_all(tracking)
        for t in remaining_new:
            t.select = True

        new_total = len(remaining_new)

        # Ergebnis in Szene zurückgeben (für main)
        scene["detect_result"] = {
            "frame": int(self.frame),
            "threshold": float(self.detection_threshold),
            "marker_adapt": int(self.marker_adapt),
            "min_marker": int(self.min_marker),
            "max_marker": int(self.max_marker),
            "initial_tracks": int(initial_count),
            "added_raw": int(len(new_tracks)),
            "deleted_close": int(deleted_close),
            "new_total": int(new_total),
            "within_bounds": bool(self.min_marker <= new_total <= self.max_marker),
        }

        scene["detect_status"] = "success" if (self.min_marker <= new_total <= self.max_marker) else "out_of_bounds"
        return {'FINISHED'}

def register():
    bpy.utils.register_class(CLIP_OT_detect_once)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_detect_once)

if __name__ == "__main__":
    register()
