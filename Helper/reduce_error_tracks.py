*** /dev/null
--- a/Helper/reduce_error_tracks.py
@@
+from __future__ import annotations
+import math
+import bpy
+from typing import Dict, Any, List, Tuple
+
+__all__ = ("run_reduce_error_tracks", "get_avg_reprojection_error")
+
+def _resolve_clip(context: bpy.types.Context):
+    clip = getattr(context, "edit_movieclip", None)
+    if not clip:
+        clip = getattr(getattr(context, "space_data", None), "clip", None)
+    if not clip and bpy.data.movieclips:
+        clip = next(iter(bpy.data.movieclips), None)
+    return clip
+
+def _active_tracking_object(clip) -> bpy.types.MovieTrackingObject | None:
+    try:
+        tr = clip.tracking
+        obj = getattr(tr, "objects", None)
+        if obj is None:
+            return None
+        # prefer the active object; fall back to the "Camera" object
+        active = getattr(obj, "active", None)
+        if active:
+            return active
+        # legacy: first or named "Camera"
+        cam = None
+        for o in obj:
+            if o.name == "Camera":
+                cam = o
+                break
+        return cam or (obj[0] if len(obj) else None)
+    except Exception:
+        return None
+
+def get_avg_reprojection_error(context: bpy.types.Context) -> float | None:
+    """
+    Liefert den durchschnittlichen Solve-Error in Pixeln, wenn vorhanden.
+    Primär: reconstruction.average_error des aktiven Tracking-Objekts.
+    Fallback: Mittelwert der Track.average_error über alle Tracks mit gültigem Wert.
+    """
+    clip = _resolve_clip(context)
+    if not clip:
+        return None
+    # Primärquelle: Reconstruction
+    try:
+        obj = _active_tracking_object(clip)
+        if obj and obj.reconstruction and getattr(obj.reconstruction, "is_valid", False):
+            ae = float(getattr(obj.reconstruction, "average_error", float("nan")))
+            if ae == ae and ae > 0.0:  # not NaN
+                return ae
+    except Exception:
+        pass
+    # Fallback: Tracks mitteln (nur gültige Werte)
+    vals: List[float] = []
+    try:
+        for t in clip.tracking.tracks:
+            try:
+                v = float(getattr(t, "average_error", float("nan")))
+                if v == v and v > 0.0:
+                    vals.append(v)
+            except Exception:
+                continue
+    except Exception:
+        return None
+    if not vals:
+        return None
+    return sum(vals) / len(vals)
+
+def run_reduce_error_tracks(context: bpy.types.Context, *, max_to_delete: int) -> Dict[str, Any]:
+    """
+    Löscht die 'max_to_delete' schlechtesten Tracks (höchster average_error).
+    Gibt Telemetrie zurück: wie viele/ welche Tracks entfernt wurden.
+    """
+    clip = _resolve_clip(context)
+    if not clip or max_to_delete <= 0:
+        return {"status": "NOOP", "deleted": 0, "names": []}
+    tracks = list(clip.tracking.tracks)
+    # Nur Tracks mit sinnvollem Fehlerwert bewerten; sonst ans Ende setzen (nicht löschen)
+    def _err(t) -> float:
+        try:
+            v = float(getattr(t, "average_error", float("nan")))
+            return v if (v == v and v >= 0.0) else -1.0
+        except Exception:
+            return -1.0
+    # Sortierung: absteigend nach Fehler; ungültige (-1) ans Ende
+    tracks_sorted = sorted(tracks, key=_err, reverse=True)
+    # Filter: nur mit gültigem Fehler >= 0
+    worst = [t for t in tracks_sorted if _err(t) >= 0.0]
+    if not worst:
+        return {"status": "NO_VALID_ERRORS", "deleted": 0, "names": []}
+    # Begrenzen
+    k = min(int(max_to_delete), 5, len(worst))
+    to_remove = worst[:k]
+    names = [t.name for t in to_remove]
+    # Löschen via API (robust, ohne Operator-Override)
+    removed = 0
+    for t in to_remove:
+        try:
+            clip.tracking.tracks.remove(t)
+            removed += 1
+        except Exception:
+            pass
+    try:
+        bpy.context.view_layer.update()
+    except Exception:
+        pass
+    return {"status": "OK", "deleted": removed, "names": names}
