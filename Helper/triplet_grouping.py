# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations
"""
Helper/triplet_grouping.py

Zweck
-----
- Selektierte Tracks am aktuellen Frame auslesen
- Positionsbasiert in 3er-Gruppen clustern (ε-Pixel-Bucket)
- Gruppen (Namen & Pointer) robust in Scene-Props persistieren

Kompatible Scene-Keys (werden von bidirectional_track.py gelesen):
  - "pattern_triplet_groups_json"      → [[name1,name2,name3], ...]
  - "pattern_triplet_groups_ptr_json"  → [[ptr1,ptr2,ptr3], ...]
  - "pattern_triplet_groups_count"     → int
"""

import json
from typing import Any, Dict, List, Optional, Tuple

import bpy

__all__ = ("run_triplet_grouping", "CLIP_OT_triplet_grouping", "register", "unregister")

# Scene Keys
_TRIPLET_NAMES_KEY = "pattern_triplet_groups_json"
_TRIPLET_PTRS_KEY = "pattern_triplet_groups_ptr_json"
_TRIPLET_COUNT_KEY = "pattern_triplet_groups_count"


# ---------- UI/Context ----------

def _active_clip(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    space = getattr(context, "space_data", None)
    if getattr(space, "type", None) == 'CLIP_EDITOR' and getattr(space, "clip", None):
        return space.clip
    try:
        return bpy.data.movieclips[0] if bpy.data.movieclips else None
    except Exception:
        return None


# ---------- Core: Lesen, Gruppieren, Persistieren ----------

def _selected_tracks_with_pos(
    tracking: bpy.types.MovieTracking, frame: int, width: int, height: int
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for t in tracking.tracks:
        if not getattr(t, "select", False):
            continue
        try:
            m = t.markers.find_frame(frame, exact=True)
        except TypeError:
            m = t.markers.find_frame(frame)
        if not m or getattr(m, "mute", False):
            continue
        out.append({
            "name": t.name,
            "ptr": int(t.as_pointer()),
            "x": float(m.co[0]) * float(width),
            "y": float(m.co[1]) * float(height),
        })
    return out


def _group_into_triplets_by_position(
    items: List[Dict[str, Any]], *, eps_px: float
) -> List[List[Dict[str, Any]]]:
    """
    Disjunkte 3er-Gruppen per Positions-Bucketing (Rasterweite eps_px).
    Rest (<3 pro Bucket) wird bewusst ignoriert (mit Log).
    """
    if not items:
        return []

    def key(x: float, y: float) -> Tuple[int, int]:
        return (int(round(x / eps_px)), int(round(y / eps_px)))

    buckets: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
    for it in items:
        buckets.setdefault(key(float(it["x"]), float(it["y"])), []).append(it)

    # deterministische Reihenfolge pro Bucket
    for lst in buckets.values():
        lst.sort(key=lambda d: (int(d.get("ptr", 0)), str(d.get("name", ""))))

    groups: List[List[Dict[str, Any]]] = []
    for k, lst in buckets.items():
        full = len(lst) // 3
        for i in range(full):
            groups.append(lst[i*3:(i+1)*3])
        rest = len(lst) % 3
        if rest:
            print(f"[TripletGrouping] WARN: Bucket {k} Rest={rest} → nur volle 3er gespeichert.")
    return groups


def _persist_groups(scene: bpy.types.Scene, groups: List[List[Dict[str, Any]]]) -> int:
    names_payload = [[g[0]["name"], g[1]["name"], g[2]["name"]] for g in groups]
    ptrs_payload = [[g[0]["ptr"],  g[1]["ptr"],  g[2]["ptr"]]  for g in groups]
    try:
        scene[_TRIPLET_NAMES_KEY] = json.dumps(names_payload)
        scene[_TRIPLET_PTRS_KEY]  = json.dumps(ptrs_payload)
        scene[_TRIPLET_COUNT_KEY] = int(len(groups))
        return len(groups)
    except Exception as ex:
        print(f"[TripletGrouping] Persist failed: {ex}")
        return 0


# ---------- Public API ----------

def run_triplet_grouping(
    context: bpy.types.Context,
    *,
    frame: Optional[int] = None,
    eps_px: Optional[float] = None,
    source: str = "selected",  # zukünftig: "selected" | "names"
) -> Dict[str, Any]:
    """
    Bildet 3er-Gruppen **vor** dem Tracking und persistiert sie in der Szene.

    Params
    ------
    frame  : Frame, auf dem die Positionen ausgewertet werden (Default: current).
    eps_px : Pixel-Toleranz fürs Bucketing. Default: dynamisch width*0.00025, geclamped [0.5..2.0].
    source : Aktuell nur "selected" (selektierte Tracks werden verarbeitet).

    Returns
    -------
    dict(status="OK", selected=n, groups=G, eps=..., frame=...)
    """
    clip = _active_clip(context)
    if not clip:
        return {"status": "FAILED", "reason": "no_movieclip"}

    tracking = clip.tracking
    scene = context.scene
    frame_now = int(frame if frame is not None else scene.frame_current)
    width, height = int(clip.size[0]), int(clip.size[1])

    # Eingangsmenge bestimmen
    if source != "selected":
        print(f"[TripletGrouping] WARN: source='{source}' nicht unterstützt → fallback 'selected'")
    items = _selected_tracks_with_pos(tracking, frame_now, width, height)

    # Epsilon-Heuristik (robust über Auflösung)
    eps = float(eps_px) if eps_px is not None else max(0.5, min(2.0, width * 0.00025))

    groups = _group_into_triplets_by_position(items, eps_px=eps)
    stored = _persist_groups(scene, groups)

    # Quick-Sanity
    if stored * 3 != len(items):
        delta = len(items) - stored * 3
        print(f"[TripletGrouping] INFO: selected={len(items)}, groups*3={stored*3}, Δ={delta}")

    print(f"[TripletGrouping] STORED {stored} triplets @frame={frame_now} (eps={eps:.3f}px)")
    return {
        "status": "OK",
        "selected": int(len(items)),
        "groups": int(stored),
        "eps": float(eps),
        "frame": int(frame_now),
    }


# ---------- Optionaler Operator (UI/Debug) ----------

class CLIP_OT_triplet_grouping(bpy.types.Operator):
    bl_idname = "clip.triplet_grouping"
    bl_label = "Triplet Grouping (Pre-Track)"
    bl_description = "Gruppiert selektierte Tracks in 3er-Sets und speichert diese in der Szene"

    eps_px: bpy.props.FloatProperty(  # type: ignore
        name="Epsilon (px)",
        default=0.0,
        min=0.0,
        description="0 = Auto (width*0.00025, clamp 0.5..2.0)",
    )
    frame: bpy.props.IntProperty(  # type: ignore
        name="Frame",
        default=-1,
        description="-1 = aktueller Frame",
    )

    def execute(self, context):
        eps = None if self.eps_px <= 0.0 else float(self.eps_px)
        frm = None if self.frame < 0 else int(self.frame)
        res = run_triplet_grouping(context, frame=frm, eps_px=eps, source="selected")
        if res.get("status") != "OK":
            self.report({'ERROR'}, str(res))
            return {'CANCELLED'}
        self.report({'INFO'}, f"Triplets: {res['groups']} (eps={res['eps']:.3f}px)")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(CLIP_OT_triplet_grouping)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_triplet_grouping)
