# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/bidirectional_track.py

Frameweises Forward-Tracking der aktuell selektierten Marker in Dreier-Gruppen:
- Gruppierung NUR über Koordinaten (Annahme: Anzahl selektierter Tracks % 3 == 0).
- Nach jedem Track-Schritt wird in jeder Dreiergruppe das nächstliegende Paar
  bestimmt; der dritte Marker wird auf deren Mittelpunkt gesetzt.
- Danach werden alle Gruppen-Tracks (wieder) selektiert.
- ESC → sofortiger Abbruch (ohne Rückmeldung an den Coordinator).
- Beim Erreichen von scene.frame_end → scene['bidi_result']="FINISHED", scene['bidi_active']=False.

Kompatibilität:
- Operator-ID:  "clip.bidirectional_track"
- Klassenname:  CLIP_OT_bidirectional_track  (wie von Helper/__init__.py importiert)
- Scene-Keys:   'bidi_active' (bool), 'bidi_result' (str)
"""

from __future__ import annotations
import bpy
from mathutils import Vector
from typing import List, Tuple, Optional

__all__ = ("CLIP_OT_bidirectional_track", "register", "unregister")

# ---- interne Hilfen ---------------------------------------------------------

def _find_clip_override(context) -> Optional[dict]:
    """Sichert CLIP_EDITOR-Kontext für Operator-Aufrufe."""
    win = context.window
    if not win:
        return None
    scr = getattr(win, "screen", None)
    if not scr:
        return None
    for area in scr.areas:
        if getattr(area, "type", None) == 'CLIP_EDITOR':
            # aktive Space referenzieren/erzwingen
            space = area.spaces.active
            for region in area.regions:
                if getattr(region, "type", None) == 'WINDOW':
                    ov = {'window': win, 'screen': scr, 'area': area, 'region': region, 'space_data': space, 'scene': context.scene}
                    # Clip sicherstellen
                    if getattr(space, "clip", None) is None:
                        try:
                            space.clip = _get_active_clip(context)
                        except Exception:
                            pass
                    return ov
    return None

def _get_active_clip(context) -> Optional[bpy.types.MovieClip]:
    space = getattr(context, "space_data", None)
    if getattr(space, "type", None) == 'CLIP_EDITOR' and getattr(space, "clip", None):
        return space.clip
    try:
        return bpy.data.movieclips[0] if bpy.data.movieclips else None
    except Exception:
        return None

def _current_frame_in_clip(context) -> int:
    ov = _find_clip_override(context)
    if ov and ov.get('space_data') and getattr(ov['space_data'], "clip_user", None):
        return int(ov['space_data'].clip_user.frame_current)
    return int(context.scene.frame_current)

def _set_frame_in_clip(context, frame: int) -> None:
    ov = _find_clip_override(context)
    if ov and ov.get('space_data') and getattr(ov['space_data'], "clip_user", None):
        try:
            ov['space_data'].clip_user.frame_current = int(frame)
        except Exception:
            pass
    # Szene folgen lassen (optional, schadet nicht)
    try:
        context.scene.frame_set(int(frame))
    except Exception:
        pass

def _selected_tracks_with_marker_at_frame(clip: bpy.types.MovieClip, frame: int) -> List[Tuple[bpy.types.MovieTrackingTrack, Vector]]:
    out: List[Tuple[bpy.types.MovieTrackingTrack, Vector]] = []
    for t in clip.tracking.tracks:
        if not getattr(t, "select", False):
            continue
        m = None
        try:
            m = t.markers.find_frame(frame, exact=True)
        except TypeError:
            m = t.markers.find_frame(frame)
        if m and not getattr(m, "mute", False):
            out.append((t, Vector(m.co)))
    return out

def _greedy_triplets_by_min_sum(points: List[Tuple[bpy.types.MovieTrackingTrack, Vector]]) -> List[Tuple[bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingTrack]]:
    """Bildet Tripel, indem jeweils die Kombination mit minimaler Summe der drei Kanten gewählt wird."""
    triplets = []
    pts = points[:]  # copy
    while len(pts) >= 3:
        best = None
        best_sum = None
        n = len(pts)
        for i in range(n):
            for j in range(i+1, n):
                for k in range(j+1, n):
                    (t1, p1) = pts[i]; (t2, p2) = pts[j]; (t3, p3) = pts[k]
                    s = (p1 - p2).length + (p1 - p3).length + (p2 - p3).length
                    if best_sum is None or s < best_sum:
                        best_sum = s
                        best = (i, j, k)
        if best is None:
            break
        i, j, k = best
        triplets.append((pts[i][0], pts[j][0], pts[k][0]))
        # entferne in umgekehrter Reihenfolge
        for idx in sorted([i, j, k], reverse=True):
            pts.pop(idx)
    return triplets

def _select_tracks(tracks: List[bpy.types.MovieTrackingTrack], sel: bool = True) -> None:
    for t in tracks:
        try:
            t.select = bool(sel)
            t.select_anchor = bool(sel)
            t.select_pattern = bool(sel)
        except Exception:
            t.select = bool(sel)

def _pair_midpoint_correction(t1, t2, t3, frame: int) -> None:
    """Bestimme in der Dreiergruppe das nächstliegende Paar und setze den dritten auf dessen Mittelpunkt."""
    def _m_at(t, f):
        try:
            return t.markers.find_frame(f, exact=True)
        except TypeError:
            return t.markers.find_frame(f)

    m1 = _m_at(t1, frame); m2 = _m_at(t2, frame); m3 = _m_at(t3, frame)
    if not (m1 and m2 and m3):
        return
    p1, p2, p3 = Vector(m1.co), Vector(m2.co), Vector(m3.co)
    d12 = (p1 - p2).length
    d13 = (p1 - p3).length
    d23 = (p2 - p3).length
    if d12 <= d13 and d12 <= d23:
        mid = (p1 + p2) * 0.5
        m3.co = mid
    elif d13 <= d12 and d13 <= d23:
        mid = (p1 + p3) * 0.5
        m2.co = mid
    else:
        mid = (p2 + p3) * 0.5
        m1.co = mid

# ---- Operator ---------------------------------------------------------------

class CLIP_OT_bidirectional_track(bpy.types.Operator):
    """Frameweises Forward-Tracking + Triplet-Korrektur bis Szenenende oder ESC."""
    bl_idname = "clip.bidirectional_track"
    bl_label = "Bidirectional Track (Triplet-Coop)"
    bl_options = {"REGISTER"}

    # Kompatible Dummy-Properties (werden vom Coordinator evtl. übergeben)
    use_cooperative_triplets: bpy.props.BoolProperty(  # type: ignore
        name="Use Cooperative Triplets",
        default=True,
    )
    auto_enable_from_selection: bpy.props.BoolProperty(  # type: ignore
        name="Auto Enable From Selection",
        default=True,
    )

    _timer = None
    _triplets: List[Tuple[bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingTrack]] = []

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        scn = context.scene
        clip = _get_active_clip(context)
        if not clip:
            self.report({'WARNING'}, "Kein MovieClip verfügbar.")
            return {'CANCELLED'}

        # Startsignal für den Coordinator
        scn["bidi_active"] = True
        scn["bidi_result"] = ""

        # aktuelle Selektion + Frame lesen
        frame = _current_frame_in_clip(context)
        pts = _selected_tracks_with_marker_at_frame(clip, frame)
        if not pts:
            # Nichts zu tun → NOOP
            scn["bidi_active"] = False
            scn["bidi_result"] = "NOOP"
            return {'FINISHED'}
        if len(pts) % 3 != 0:
            self.report({'WARNING'}, "Markeranzahl ist kein Vielfaches von 3.")
            scn["bidi_active"] = False
            scn["bidi_result"] = "NOOP"
            return {'FINISHED'}

        # Triplets bilden
        self._triplets = _greedy_triplets_by_min_sum(pts)
        # Sicherheit: exakt selektieren (nur Gruppe)
        _select_tracks([t for tri in self._triplets for t in tri], True)

        # Timer starten
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.15, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context: bpy.types.Context, event: bpy.types.Event):
        scn = context.scene

        # Sofortiger ESC-Abbruch: ohne Ergebnis zurück
        if event.type == 'ESC':
            try:
                if self._timer:
                    context.window_manager.event_timer_remove(self._timer)
            finally:
                scn["bidi_active"] = False
            return {'CANCELLED'}

        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        # Szenenende checken
        cur = _current_frame_in_clip(context)
        if cur >= int(scn.frame_end):
            try:
                if self._timer:
                    context.window_manager.event_timer_remove(self._timer)
            finally:
                scn["bidi_result"] = "FINISHED"
                scn["bidi_active"] = False
            return {'FINISHED'}

        # 1) Einen Frame vorwärts tracken (nur selektierte)
        ov = _find_clip_override(context)
        try:
            bpy.ops.clip.track_markers(ov or {}, backwards=False, sequence=False)
        except Exception as ex:
            print(f"[Bidir] track_markers failed: {ex!r}")
            # Abbruch mit FINISHED, damit Coordinator weiterkommt
            try:
                if self._timer:
                    context.window_manager.event_timer_remove(self._timer)
            finally:
                scn["bidi_result"] = "FINISHED"
                scn["bidi_active"] = False
            return {'FINISHED'}

        next_frame = cur + 1

        # 2) Korrektur pro Triplet im neuen Frame
        for (t1, t2, t3) in self._triplets:
            _pair_midpoint_correction(t1, t2, t3, next_frame)

        # 3) Triplets wieder selektieren (sicherstellen)
        _select_tracks([t for tri in self._triplets for t in tri], True)

        # 4) Frame im Clip-Editor erhöhen
        _set_frame_in_clip(context, next_frame)

        return {'RUNNING_MODAL'}

# ---- Register ---------------------------------------------------------------

def register():
    bpy.utils.register_class(CLIP_OT_bidirectional_track)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_bidirectional_track)
