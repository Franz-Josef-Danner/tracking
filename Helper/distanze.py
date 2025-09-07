# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/distanze.py
Löscht neu gesetzte Marker, die näher als ein Mindestabstand zu alten (nicht gemuteten)
Markern liegen – strikt framegenau. Es wird nur geloggt:
 - "[DISTANZE] TooClose track=… frame=… d2=…"
 - "[DISTANZE] Deleted track=… frame=… method=…"
"""
from __future__ import annotations
from typing import Iterable, Set, Dict, Any, Optional, Tuple
import bpy
from mathutils import Vector

__all__ = ("run_distance_cleanup",)
LOG_PREFIX = "DISTANZE"
DETECT_LAST_THRESHOLD_KEY = "last_detection_threshold"

def _resolve_clip(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    try:
        area = context.area
        if area and area.type == "CLIP_EDITOR":
            sp = area.spaces.active
            return getattr(sp, "clip", None)
    except Exception:
        pass
    try:
        return context.scene.clip
    except Exception:
        pass
    try:
        return next(iter(bpy.data.movieclips), None)
    except Exception:
        return None

def _ensure_clip_context() -> dict:
    wm = bpy.context.window_manager
    if not wm:
        return {}
    for win in wm.windows:
        scr = getattr(win, "screen", None)
        if not scr:
            continue
        for area in scr.areas:
            if area.type != "CLIP_EDITOR":
                continue
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            space = area.spaces.active if hasattr(area, "spaces") else None
            if region and space:
                return {"window": win, "area": area, "region": region, "space_data": space, "scene": bpy.context.scene}
    return {}

def _dist2(a: Vector, b: Vector, *, width: int, height: int) -> float:
    dx = (a.x - b.x) * width
    dy = (a.y - b.y) * height
    return dx * dx + dy * dy

def _auto_min_distance_px(context: bpy.types.Context) -> int:
    scn = context.scene
    base_px = int(scn.get("min_distance_base", 8))
    thr = float(scn.get(DETECT_LAST_THRESHOLD_KEY, 0.75))
    # einfache, numerisch stabile Skalierung – ident zu detect.py-Heuristik
    import math
    factor = math.log10(max(thr * 1e8, 1e-8)) / 8.0
    return max(1, int(base_px * factor))

def run_distance_cleanup(
    context: bpy.types.Context,
    *,
    pre_ptrs: Iterable[int] | Set[int],
    frame: int,
    min_distance: Optional[float] = None,   # Pixel
    distance_unit: str = "pixel",           # nur "pixel" unterstützt
    require_selected_new: bool = True,
    include_muted_old: bool = False,
    select_remaining_new: bool = True,
) -> Dict[str, Any]:
    clip = _resolve_clip(context)
    if not clip:
        return {"status": "FAILED", "reason": "no_clip"}

    try:
        width, height = int(clip.size[0]), int(clip.size[1])
    except Exception:
        width, height = 0, 0
    if width <= 0 or height <= 0:
        return {"status": "FAILED", "reason": "no_size"}

    if min_distance is None or float(min_distance) <= 0.0:
        min_distance = float(_auto_min_distance_px(context))
    min_d2 = float(min_distance) * float(min_distance)

    pre_ptrs_set: Set[int] = set(int(p) for p in (pre_ptrs or []))

    # Referenzpositionen (ALT) einsammeln – keine muted/estimated Marker
    old_positions: list[Vector] = []
    for tr in clip.tracking.tracks:
        if int(tr.as_pointer()) in pre_ptrs_set:
            try:
                m = tr.markers.find_frame(int(frame), exact=True)
            except TypeError:
                m = tr.markers.find_frame(int(frame))
            if not m:
                continue
            if not include_muted_old and getattr(m, "mute", False):
                continue
            if getattr(m, "is_estimated", False):
                continue
            co = getattr(m, "co", None)
            if co is not None:
                old_positions.append(co.copy())

    new_tracks = [tr for tr in clip.tracking.tracks if int(tr.as_pointer()) not in pre_ptrs_set]

    removed = 0
    kept = 0
    checked = 0
    skipped_no_marker = 0
    skipped_unselected = 0

    override = _ensure_clip_context()
    with bpy.context.temp_override(**override) if override else bpy.context.temp_override():
        for tr in new_tracks:
            try:
                m = tr.markers.find_frame(int(frame), exact=True)
            except TypeError:
                m = tr.markers.find_frame(int(frame))
            if not m:
                skipped_no_marker += 1
                continue
            if getattr(m, "is_estimated", False):
                skipped_no_marker += 1
                continue
            if require_selected_new and not (getattr(m, "select", False) or getattr(tr, "select", False)):
                skipped_unselected += 1
                continue
            pos = getattr(m, "co", None)
            if pos is None:
                skipped_no_marker += 1
                continue

            checked += 1
            # Nähe prüfen
            near = False
            nearest_d2 = float("inf")
            for op in old_positions:
                d2 = _dist2(pos, op, width=width, height=height)
                if d2 < nearest_d2:
                    nearest_d2 = d2
            if old_positions and nearest_d2 < min_d2:
                near = True

            if near:
                # 1) Konflikt-Log
                try:
                    print(f"[{LOG_PREFIX}] TooClose track={getattr(tr,'name','')} frame={int(frame)} d2={nearest_d2:.4f}")
                except Exception:
                    pass
                # 2) Löschen – bevorzugt framegenau, Fallback Marker-Objekt
                try:
                    tr.markers.delete_frame(int(frame))
                    removed += 1
                    try:
                        print(f"[{LOG_PREFIX}] Deleted track={getattr(tr,'name','')} frame={int(frame)} method=delete_frame")
                    except Exception:
                        pass
                    continue
                except Exception:
                    try:
                        tr.markers.delete(m)
                        removed += 1
                        try:
                            print(f"[{LOG_PREFIX}] Deleted track={getattr(tr,'name','')} frame={int(frame)} method=delete(marker)")
                        except Exception:
                            pass
                        continue
                    except Exception:
                        # Stumm: nur die zwei gewünschten Logtypen
                        continue

            # Kein Konflikt → optional selektieren, damit Folgephasen sie sehen
            if select_remaining_new:
                try:
                    m.select = True
                    tr.select = True
                except Exception:
                    pass
            kept += 1

    return {
        "status": "OK",
        "frame": int(frame),
        "removed": int(removed),
        "kept": int(kept),
        "checked_new": int(checked),
        "skipped_no_marker": int(skipped_no_marker),
        "skipped_unselected": int(skipped_unselected),
        "min_distance": float(min_distance),
        "distance_unit": "pixel",
        "old_count": len(old_positions),
        "new_total": len(new_tracks),
    }
