# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

"""
Helper/triplet_joiner.py

Zweck
-----
- Persistierte 3er-Gruppen (Namen & Pointer) aus Szene lesen
- Je Gruppe exakt drei Tracks selektieren, aktiven Track setzen
- join_tracks() robust im CLIP-Context ausführen
- Zusammenfassung zurückgeben

Kompatibel mit:
  - Helper/triplet_grouping.py (persistiert Gruppen)
  - Helper/bidirectional_track.py (ruft Join nach dem Tracking)
"""

import json
from typing import Any, Dict, List, Optional, Tuple

import bpy

__all__ = ("run_triplet_join", "CLIP_OT_triplet_join", "register", "unregister")

# Scene Keys
_TRIPLET_NAMES_KEY = "pattern_triplet_groups_json"
_TRIPLET_PTRS_KEY  = "pattern_triplet_groups_ptr_json"
_TRIPLET_COUNT_KEY = "pattern_triplet_groups_count"


# ---------- UI/Context ----------

def _find_clip_context() -> Tuple[Optional[bpy.types.Window],
                                  Optional[bpy.types.Area],
                                  Optional[bpy.types.Region],
                                  Optional[bpy.types.Space]]:
    wm = bpy.context.window_manager
    if not wm:
        return None, None, None, None
    for win in wm.windows:
        scr = win.screen
        if not scr:
            continue
        for area in scr.areas:
            if area.type == 'CLIP_EDITOR':
                region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                space = area.spaces.active if hasattr(area, "spaces") else None
                if region and space:
                    return win, area, region, space
    return None, None, None, None


def _run_in_clip_context(op_callable, **kwargs):
    win, area, region, space = _find_clip_context()
    if not (win and area and region and space):
        # Fallback: ohne Override ausführen (funktioniert oft trotzdem)
        return op_callable(**kwargs)
    override = {
        "window": win,
        "area": area,
        "region": region,
        "space_data": space,
        "scene": bpy.context.scene,
    }
    with bpy.context.temp_override(**override):
        return op_callable(**kwargs)


def _active_clip() -> Optional[bpy.types.MovieClip]:
    # 1) Aus aktivem CLIP_EDITOR
    _, _, _, space = _find_clip_context()
    if space:
        clip = getattr(space, "clip", None)
        if clip:
            return clip
    # 2) Erstbesten Clip aus Datenbank
    try:
        for c in bpy.data.movieclips:
            return c
    except Exception:
        pass
    return None


# ---------- Track-Utilities ----------

def _deselect_all(clip: bpy.types.MovieClip) -> None:
    try:
        for t in clip.tracking.tracks:
            t.select = False
    except Exception:
        pass


def _set_active(clip: bpy.types.MovieClip, track: bpy.types.MovieTrackingTrack) -> None:
    """Setzt den aktiven Track (kritisch für join_tracks)."""
    try:
        clip.tracking.tracks.active = track
    except Exception:
        # Fallback über Operator
        try:
            # Blender hat keinen offiziellen set_active op im Clip-Editor;
            # das Setzen über Property ist die robuste Variante.
            pass
        except Exception:
            pass


def _track_by_ptr_or_name(clip: bpy.types.MovieClip, ptr: Optional[int], name: Optional[str]):
    tracks = getattr(getattr(clip, "tracking", None), "tracks", [])
    if ptr is not None:
        for t in tracks:
            try:
                if int(t.as_pointer()) == int(ptr):
                    return t
            except Exception:
                pass
    if name:
        for t in tracks:
            try:
                if t.name == name:
                    return t
            except Exception:
                pass
    return None


# ---------- Gruppen laden ----------

def _load_triplet_groups_from_scene(scene: bpy.types.Scene) -> List[List[Dict[str, Any]]]:
    """
    Rückgabeformat je Gruppe: [{"ptr": int|None, "name": str|None}, x3]
    """
    groups: List[List[Dict[str, Any]]] = []
    try:
        ptr_json = scene.get(_TRIPLET_PTRS_KEY)
        name_json = scene.get(_TRIPLET_NAMES_KEY)
        ptr_groups = json.loads(ptr_json) if isinstance(ptr_json, str) else []
        name_groups = json.loads(name_json) if isinstance(name_json, str) else []

        L = max(len(ptr_groups), len(name_groups))
        for idx in range(L):
            ptr_trip = list(ptr_groups[idx]) if idx < len(ptr_groups) else []
            name_trip = list(name_groups[idx]) if idx < len(name_groups) else []
            while len(ptr_trip) < 3:  ptr_trip.append(None)
            while len(name_trip) < 3: name_trip.append(None)
            groups.append([
                {"ptr": ptr_trip[0], "name": name_trip[0]},
                {"ptr": ptr_trip[1], "name": name_trip[1]},
                {"ptr": ptr_trip[2], "name": name_trip[2]},
            ])
    except Exception as ex:
        print(f"[TripletJoin] WARN: Gruppen konnten nicht geladen werden: {ex}")
    return groups


# ---------- Join-Kern ----------

def run_triplet_join(
    context: bpy.types.Context,
    *,
    active_policy: str = "first",   # "first" | "last" | "middle"
    stop_on_error: bool = False,
) -> Dict[str, Any]:
    """
    Führt den Join pro gespeicherter 3er-Gruppe aus.

    Returns:
      dict(status="OK", joined=J, skipped=S, total=T, errors=[...])
    """
    clip = _active_clip()
    if not clip:
        return {"status": "FAILED", "reason": "no_movieclip"}

    groups = _load_triplet_groups_from_scene(context.scene)
    if not groups:
        print("[TripletJoin] Info: Keine Triplet-Gruppen in Szene – kein Join.")
        return {"status": "OK", "joined": 0, "skipped": 0, "total": 0, "errors": []}

    joined_ops = 0
    skipped = 0
    errors: List[str] = []

    for g_idx, trip in enumerate(groups, start=1):
        # Tracks robust auflösen
        tr_objs: List[bpy.types.MovieTrackingTrack] = []
        used_ptrs = set()
        for item in trip:
            tr = _track_by_ptr_or_name(clip, item.get("ptr"), item.get("name"))
            if tr:
                pid = int(tr.as_pointer())
                if pid in used_ptrs:
                    # Doppeltauflösung vermeiden (falls Name==Pointer-Kollision)
                    continue
                used_ptrs.add(pid)
                tr_objs.append(tr)

        if len(tr_objs) < 3:
            print(f"[TripletJoin] Gruppe #{g_idx}: <3 gültige Tracks – skip.")
            skipped += 1
            continue

        # Selektion + aktiven Track setzen
        _deselect_all(clip)
        for t in tr_objs:
            try:
                t.select = True
            except Exception:
                pass

        # Active-Policy
        if active_policy == "last":
            active = tr_objs[-1]
        elif active_policy == "middle":
            active = tr_objs[1]
        else:
            active = tr_objs[0]

        _set_active(clip, active)

        # Operator ausführen (im CLIP-Kontext)
        def _op_join(**kw):
            return bpy.ops.clip.join_tracks(**kw)

        try:
            ret = _run_in_clip_context(_op_join)
            print(f"[TripletJoin] Gruppe #{g_idx}: join_tracks() -> {ret}")
            joined_ops += 1
        except Exception as ex:
            msg = f"Gruppe #{g_idx}: join_tracks() fehlgeschlagen: {ex}"
            print(f"[TripletJoin] ERROR: {msg}")
            errors.append(msg)
            if stop_on_error:
                break

        # UI-Refresh
        try:
            bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
        except Exception:
            pass

    # Cleanup: Selektion leeren
    _deselect_all(clip)

    print(f"[TripletJoin] Zusammenfassung: joined={joined_ops}/{len(groups)} | skipped={skipped}")
    return {
        "status": "OK",
        "joined": int(joined_ops),
        "skipped": int(skipped),
        "total": int(len(groups)),
        "errors": errors,
    }


# ---------- Optionaler Operator (UI/Debug) ----------

class CLIP_OT_triplet_join(bpy.types.Operator):
    bl_idname = "clip.triplet_join"
    bl_label = "Triplet Join (Post-Track)"
    bl_description = "Führt join_tracks() für in der Szene gespeicherte 3er-Gruppen aus"

    active_policy: bpy.props.EnumProperty(  # type: ignore
        name="Aktiver Track",
        items=[("first", "Erster", ""),
               ("middle", "Mittlerer", ""),
               ("last", "Letzter", "")],
        default="first",
    )
    stop_on_error: bpy.props.BoolProperty(  # type: ignore
        name="Stopp bei Fehler",
        default=False,
    )

    def execute(self, context):
        res = run_triplet_join(context, active_policy=self.active_policy, stop_on_error=self.stop_on_error)
        if res.get("status") != "OK":
            self.report({'ERROR'}, str(res))
            return {'CANCELLED'}
        self.report({'INFO'}, f"Joined {res['joined']}/{res['total']} Gruppen")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(CLIP_OT_triplet_join)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_triplet_join)
