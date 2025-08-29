*** /dev/null
--- a/Helper/multi.py
@@
+from __future__ import annotations
+from typing import Dict, Optional, Set
+import bpy
+
+__all__ = ["run_multi_pass"]
+
+def _set_pattern_size(tracking: bpy.types.MovieTracking, new_size: int) -> int:
+    s = tracking.settings
+    clamped = max(3, min(101, int(new_size)))
+    try:
+        s.default_pattern_size = clamped
+    except Exception:
+        pass
+    return int(getattr(s, "default_pattern_size", clamped))
+
+def run_multi_pass(
+    context: bpy.types.Context,
+    *,
+    detect_threshold: float,
+    pre_ptrs: Set[int],
+    scale_low: float = 0.5,
+    scale_high: float = 2.0,
+    adjust_search_with_pattern: bool = True,
+) -> Dict:
+    """
+    Führt 2 zusätzliche Detect-Durchläufe mit identischem threshold aus,
+    variiert Pattern(- und optional Search-)Size, sammelt NUR neue Marker
+    relativ zu pre_ptrs und selektiert diese.
+    """
+    clip = getattr(context, "edit_movieclip", None) or getattr(getattr(context, "space_data", None), "clip", None)
+    if not clip:
+        for c in bpy.data.movieclips:
+            clip = c
+            break
+    if not clip:
+        return {"status": "FAILED", "reason": "no_movieclip"}
+
+    tracking = clip.tracking
+    settings = tracking.settings
+    pattern_o = int(getattr(settings, "default_pattern_size", 15))
+    search_o  = int(getattr(settings, "default_search_size", 51))
+
+    def _sweep(scale: float) -> int:
+        before = {t.as_pointer() for t in tracking.tracks}
+        before |= set(pre_ptrs)  # pre_ptrs sicherstellen
+        eff = _set_pattern_size(tracking, max(3, int(round(pattern_o * float(scale)))))
+        if adjust_search_with_pattern:
+            try:
+                settings.default_search_size = max(5, eff * 2)
+            except Exception:
+                pass
+        try:
+            bpy.ops.clip.detect_features(threshold=float(detect_threshold))
+        except Exception:
+            pass
+        created = [t for t in tracking.tracks if t.as_pointer() not in before]
+        return len(created)
+
+    c_low  = _sweep(scale_low)
+    c_high = _sweep(scale_high)
+
+    # restore sizes
+    _set_pattern_size(tracking, pattern_o)
+    try:
+        settings.default_search_size = search_o
+    except Exception:
+        pass
+
+    # Nur NEUE (Triplets) selektieren
+    new_ptrs = {t.as_pointer() for t in tracking.tracks if t.as_pointer() not in pre_ptrs}
+    for t in tracking.tracks:
+        t.select = (t.as_pointer() in new_ptrs)
+
+    try:
+        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
+    except Exception:
+        pass
+
+    return {
+        "status": "READY",
+        "created_low": int(c_low),
+        "created_high": int(c_high),
+        "selected": int(len(new_ptrs)),
+        "new_ptrs": new_ptrs,
+    }
