"""Add-on Extension: Cooperative Triplet Per-Frame Tracking

Dieses Snippet ist **ergänzend** zu eurem bestehenden `bidirectional_track.py` zu verstehen
(keine Änderungen am vorhandenen Code nötig). Es fügt einen separaten Operator
hinzu, der die vom Nutzer gewünschte Triplet-Kooperation pro Frame umsetzt:

- Es wird **immer nur 1 Frame** vorwärts getrackt; der Operator läuft modal in einer Schleife.
- Pro Triplet (3 Marker/Tracks) gilt: Ist in einem Frame **einer inaktiv**, werden **alle inaktiv** gesetzt.
- Sind **alle aktiv**, werden die **zwei nächst beieinander liegenden** Marker bestimmt und der **dritte** Marker
  exakt **auf den Mittelpunkt** dieses Paares gesetzt (nur für diesen Frame).
- Danach **einen Frame tracken** (`sequence=False`) und wiederholen, bis `max_steps` erreicht sind.

Triplet-Gruppierung:
- Standard: automatische Gruppierung nach **räumlicher Nähe** auf dem Start-Frame (Pixelradius `group_radius_px`).
- Optional: Wenn in der Selektion eine Anzahl von Tracks vorliegt, die durch `name_prefix` in Dreiergruppen
  zusammengehören, können die Gruppen namentlich gebildet werden (z. B. `BASE_small`, `BASE_mid`, `BASE_large`).
  Das ist tolerant implementiert: Der gemeinsame **Prefix vor dem letzten Unterstrich** wird als Basis verwendet.

Einbindung: Den gesamten Block unten **ans Ende** eures bestehenden `bidirectional_track.py` kopieren.

"""
from __future__ import annotations

import math
import time
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import bpy
from bpy.types import Operator

Vec2 = Tuple[float, float]

# -----------------------------------------------------------------------------
# Utility: Marker-IO pro Frame (defensiv für unterschiedliche Blender-Versionen)
# -----------------------------------------------------------------------------

def _find_marker_at_frame(track: bpy.types.MovieTrackingTrack, frame: int):
    markers = track.markers
    try:
        return markers.find_frame(frame, exact=True)
    except TypeError:
        return markers.find_frame(frame)


def _ensure_marker_at_frame(track: bpy.types.MovieTrackingTrack, frame: int):
    mk = _find_marker_at_frame(track, frame)
    if mk is None:
        # Fallback: wenn es keinen Marker gibt, nimm letzte bekannte Pos oder Mittelpunkt
        if len(track.markers) > 0:
            ref = track.markers[0]
            mk = track.markers.insert_frame(frame, ref.co)
        else:
            mk = track.markers.insert_frame(frame, (0.5, 0.5))
    return mk


def _marker_active(mk) -> bool:
    # Einige Blender-Versionen führen `mute` am Marker, andere nur am Track.
    muted = bool(getattr(mk, "mute", False))
    tr_muted = bool(getattr(getattr(mk, "track", None) or object(), "mute", False))
    return not (muted or tr_muted)


def _set_marker_active_for_frame(track: bpy.types.MovieTrackingTrack, frame: int, active: bool) -> None:
    mk = _ensure_marker_at_frame(track, frame)
    # Bevorzugt per-Frame: Marker.mute, wenn vorhanden.
    if hasattr(mk, "mute"):
        mk.mute = (not active)
    else:
        # Fallback: Track.mute (wirkt global), deshalb NUR wenn Inaktivität gewünscht.
        if not active and hasattr(track, "mute"):
            track.mute = True
    # Hinweis: Aktivierung eines global gemuteten Tracks (track.mute=False) unterlassen,
    # damit bestehende Pipeline-Entscheidungen nicht überschrieben werden.


def _get_marker_pos(track: bpy.types.MovieTrackingTrack, frame: int) -> Vec2:
    mk = _find_marker_at_frame(track, frame)
    if mk is None:
        if len(track.markers) > 0:
            mk = track.markers[0]
        else:
            return (0.5, 0.5)
    return float(mk.co[0]), float(mk.co[1])


def _set_marker_pos(track: bpy.types.MovieTrackingTrack, frame: int, pos: Vec2) -> None:
    mk = _ensure_marker_at_frame(track, frame)
    mk.co[0], mk.co[1] = float(pos[0]), float(pos[1])


# -----------------------------------------------------------------------------
# Triplet-Gruppierung
# -----------------------------------------------------------------------------

def _common_prefix_before_last_underscore(name: str) -> str:
    if "_" not in name:
        return name
    return name.rsplit("_", 1)[0]


def _group_triplets_by_name(tracks: Sequence[bpy.types.MovieTrackingTrack]) -> List[Tuple[bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingTrack]]:
    buckets: Dict[str, List[bpy.types.MovieTrackingTrack]] = {}
    for t in tracks:
        key = _common_prefix_before_last_underscore(t.name)
        buckets.setdefault(key, []).append(t)
    out = []
    for key, lst in buckets.items():
        if len(lst) >= 3:
            # Nimm jeweils Dreierpakete in stabiler Reihenfolge
            lst_sorted = sorted(lst, key=lambda tr: tr.name)
            for i in range(0, len(lst_sorted) - 2, 3):
                out.append((lst_sorted[i], lst_sorted[i + 1], lst_sorted[i + 2]))
    return out


def _group_triplets_by_proximity(
    tracks: Sequence[bpy.types.MovieTrackingTrack], frame: int, width: int, height: int, radius_px: int
) -> List[Tuple[bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingTrack]]:
    # Einfache räumliche Gruppierung: solange möglich, bilde Triplets aus jeweils 3 nächstgelegenen Tracks.
    remaining = list(tracks)
    used: set[int] = set()
    out: List[Tuple[bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingTrack]] = []

    # Hilfsfunktion: Distanz in Pixeln
    def px_dist(a: bpy.types.MovieTrackingTrack, b: bpy.types.MovieTrackingTrack) -> float:
        ax, ay = _get_marker_pos(a, frame)
        bx, by = _get_marker_pos(b, frame)
        ax, ay, bx, by = ax * width, ay * height, bx * width, by * height
        dx, dy = ax - bx, ay - by
        return math.hypot(dx, dy)

    for i, t in enumerate(remaining):
        if i in used:
            continue
        # Nächste 2 Nachbarn innerhalb Radius suchen
        dists: List[Tuple[float, int]] = []
        for j, u in enumerate(remaining):
            if j == i or j in used:
                continue
            d = px_dist(t, u)
            if d <= float(radius_px):
                dists.append((d, j))
        dists.sort(key=lambda x: x[0])
        if len(dists) >= 2:
            j1 = dists[0][1]
            j2 = dists[1][1]
            used.update({i, j1, j2})
            out.append((remaining[i], remaining[j1], remaining[j2]))
    return out


# -----------------------------------------------------------------------------
# Kernlogik: nächstliegendes Paar und Mittelpunkt setzen
# -----------------------------------------------------------------------------

def _distance(p: Vec2, q: Vec2) -> float:
    return math.hypot(float(p[0]) - float(q[0]), float(p[1]) - float(q[1]))


def _nearest_pair_midpoint(p1: Vec2, p2: Vec2, p3: Vec2) -> Tuple[int, Vec2]:
    d12 = _distance(p1, p2)
    d13 = _distance(p1, p3)
    d23 = _distance(p2, p3)
    if d12 <= d13 and d12 <= d23:
        return 2, ((p1[0] + p2[0]) * 0.5, (p1[1] + p2[1]) * 0.5)
    if d13 <= d12 and d13 <= d23:
        return 1, ((p1[0] + p3[0]) * 0.5, (p1[1] + p3[1]) * 0.5)
    return 0, ((p2[0] + p3[0]) * 0.5, (p2[1] + p3[1]) * 0.5)


def _cooperate_triplet_on_frame(tracks: Tuple[bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingTrack], frame: int) -> None:
    t0, t1, t2 = tracks
    m0 = _find_marker_at_frame(t0, frame)
    m1 = _find_marker_at_frame(t1, frame)
    m2 = _find_marker_at_frame(t2, frame)
    a0 = _marker_active(m0) if m0 else False
    a1 = _marker_active(m1) if m1 else False
    a2 = _marker_active(m2) if m2 else False

    if not (a0 and a1 and a2):
        # Einer inaktiv → alle inaktiv für diesen Frame
        for tr in (t0, t1, t2):
            _set_marker_active_for_frame(tr, frame, False)
        return

    # Alle aktiv → dritten auf Mittelpunkt der zwei nähesten setzen
    p0 = _get_marker_pos(t0, frame)
    p1 = _get_marker_pos(t1, frame)
    p2 = _get_marker_pos(t2, frame)
    idx_third, mid = _nearest_pair_midpoint(p0, p1, p2)
    target = (t0, t1, t2)[idx_third]
    _set_marker_pos(target, frame, mid)


# -----------------------------------------------------------------------------
# Operator: Cooperative Triplet Track (per-frame, modal)
# -----------------------------------------------------------------------------

class CLIP_OT_cooperative_triplet_track(Operator):
    bl_idname = "clip.cooperative_triplet_track"
    bl_label = "Cooperative Triplet Track (per-frame)"
    bl_description = (
        "Triplet-Kooperation: pro Frame drittes Element mittig setzen bzw. alle drei inaktivieren; "
        "danach genau einen Frame tracken und wiederholen."
    )

    max_steps: bpy.props.IntProperty(
        name="Max Steps", default=50, min=1, description="Maximalzahl Einzelschritte (Frames)"
    )
    group_radius_px: bpy.props.IntProperty(
        name="Group Radius (px)", default=40, min=1, description="Räumliche Gruppierungsschwelle in Pixeln"
    )
    prefer_name_grouping: bpy.props.BoolProperty(
        name="Prefer Name Grouping", default=True,
        description="Zuerst Dreiergruppen anhand gemeinsamen Namenspräfix bilden, sonst über räumliche Nähe"
    )

    _timer = None
    _step = 0
    _start_frame = 0
    _triplets: List[Tuple[bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingTrack]] = []

    def execute(self, context):
        space = getattr(context, "space_data", None)
        clip = getattr(space, "clip", None) if space else None
        if not clip:
            self.report({'ERROR'}, "Kein aktiver Clip im Tracking-Editor gefunden.")
            return {'CANCELLED'}

        scn = context.scene
        self._start_frame = int(scn.frame_current)

        # Gruppen bilden
        tracks = list(clip.tracking.tracks)
        selected_tracks = [t for t in tracks if getattr(t, "select", False)]
        basis = selected_tracks if selected_tracks else tracks

        triplets: List[Tuple[bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingTrack]] = []
        if self.prefer_name_grouping:
            triplets = _group_triplets_by_name(basis)

        if not triplets:
            w, h = int(clip.size[0]), int(clip.size[1])
            triplets = _group_triplets_by_proximity(basis, self._start_frame, w, h, int(self.group_radius_px))

        if not triplets:
            self.report({'ERROR'}, "Keine Triplets gefunden (Name/Proximity). Auswahl oder Radius prüfen.")
            return {'CANCELLED'}

        self._triplets = triplets
        self._step = 0

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.25, window=context.window)
        wm.modal_handler_add(self)
        print(f"[TripletTrack] START | groups={len(self._triplets)} | start_frame={self._start_frame}")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}
        if self._step >= int(self.max_steps):
            return self._finish(context)

        space = getattr(context, "space_data", None)
        clip = getattr(space, "clip", None) if space else None
        if not clip:
            return self._finish(context)

        scn = context.scene
        frame = int(scn.frame_current)

        # 1) Kooperation auf aktuellem Frame
        for tri in self._triplets:
            _cooperate_triplet_on_frame(tri, frame)

        # 2) Auswahl auf alle Triplet-Tracks setzen und EINEN Frame tracken
        for t in clip.tracking.tracks:
            t.select = False
        for a, b, c in self._triplets:
            a.select = True
            b.select = True
            c.select = True
        try:
            bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=False)
        except Exception as ex:
            print(f"[TripletTrack] track_markers failed: {ex}")

        # 3) +1 Frame vorwärts
        try:
            scn.frame_set(frame + 1)
        except Exception:
            scn.frame_current = frame + 1

        self._step += 1
        try:
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        except Exception:
            pass
        return {'PASS_THROUGH'}

    def _finish(self, context):
        print(f"[TripletTrack] FINISH | steps={self._step} | start={self._start_frame} -> end={context.scene.frame_current}")
        wm = context.window_manager
        if self._timer is not None:
            try:
                wm.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None
        return {'FINISHED'}


# ---- Helper Aufrufer ----

def run_cooperative_triplet_track(context):
    return bpy.ops.clip.cooperative_triplet_track('INVOKE_DEFAULT')


# ---- Registrierung (zusätzlich zu eurer bestehenden) ----

def register():  # noqa: F811 – absichtlich gleiche Signatur wie im Hauptmodul
    try:
        bpy.utils.register_class(CLIP_OT_cooperative_triplet_track)
    except ValueError:
        # bereits registriert
        pass


def unregister():  # noqa: F811
    try:
        bpy.utils.unregister_class(CLIP_OT_cooperative_triplet_track)
    except Exception:
        pass
