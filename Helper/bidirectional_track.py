import bpy
import math
import time
import re
from bpy.types import Operator
from typing import List, Tuple, Dict
from mathutils.kdtree import KDTree

# -----------------------------------------------------------------------------
# Triplet‑Kooperation (NON‑INSERT) + positionsbasierte Gruppierung
# -----------------------------------------------------------------------------
# Regeln pro Frame:
#  - Triplets werden einmalig zu Beginn per POSITIONS‑Clustering (KD‑Tree) am
#    Start‑Frame gebildet und per Clip‑Property gespeichert → stabil über Namen.
#  - Ist einer der drei Marker inaktiv/fehlend → alle (existierenden) Marker im
#    Frame stummschalten (mute). KEIN Insert neuer Marker.
#  - Sind alle aktiv → zwei nächst beieinander liegende finden; den dritten
#    Marker auf deren Mittelpunkt setzen. KEIN Insert, nur wenn Marker existiert.
#  - Tracking erfolgt frameweise vorwärts (sequence=False), bis keine Marker
#    mehr aktiv sind.
# -----------------------------------------------------------------------------

_TRIPLET_KEY = "__coop_triplets"        # persistierte Namen der Triplets
_FORWARD_DONE_KEY = "__bidi_forward_done"  # Gate für Coordinator

Vec2 = Tuple[float, float]

# -----------------------------------------------------------------------------
# Marker‑Utilities (NON‑INSERT)
# -----------------------------------------------------------------------------

def _find_marker_at_frame(track: bpy.types.MovieTrackingTrack, frame: int):
    markers = track.markers
    try:
        return markers.find_frame(frame, exact=True)
    except TypeError:
        return markers.find_frame(frame)


def _marker_active(mk) -> bool:
    if mk is None:
        return False
    muted_marker = bool(getattr(mk, "mute", False))
    tr = getattr(mk, "track", None)
    muted_track = bool(getattr(tr, "mute", False)) if tr else False
    return not (muted_marker or muted_track)


def _get_pos(track: bpy.types.MovieTrackingTrack, frame: int) -> Vec2:
    mk = _find_marker_at_frame(track, frame)
    if mk is None:
        return 0.5, 0.5
    return float(mk.co[0]), float(mk.co[1])


def _set_pos_if_exists(track: bpy.types.MovieTrackingTrack, frame: int, pos: Tuple[float, float]) -> bool:
    """Nur setzen, wenn im Frame bereits ein Marker existiert. Kein Insert!"""
    mk = _find_marker_at_frame(track, frame)
    if mk is None:
        return False
    mk.co[0], mk.co[1] = float(pos[0]), float(pos[1])
    return True


def _mute_if_exists(track: bpy.types.MovieTrackingTrack, frame: int) -> None:
    """Marker im Frame stummschalten, wenn vorhanden. Kein Insert!"""
    mk = _find_marker_at_frame(track, frame)
    if mk is not None and hasattr(mk, "mute"):
        mk.mute = True


def _dist(a: Vec2, b: Vec2) -> float:
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def _nearest_pair_midpoint(p1: Vec2, p2: Vec2, p3: Vec2) -> Tuple[int, Vec2]:
    d12 = _dist(p1, p2)
    d13 = _dist(p1, p3)
    d23 = _dist(p2, p3)
    if d12 <= d13 and d12 <= d23:
        return 2, ((p1[0] + p2[0]) * 0.5, (p1[1] + p2[1]) * 0.5)
    if d13 <= d12 and d13 <= d23:
        return 1, ((p1[0] + p3[0]) * 0.5, (p1[1] + p3[1]) * 0.5)
    return 0, ((p2[0] + p3[0]) * 0.5, (p2[1] + p3[1]) * 0.5)


# -----------------------------------------------------------------------------
# Triplet‑Gruppierung
# -----------------------------------------------------------------------------

def _collect_active_markers_on_frame(tracks, frame):
    items = []
    for t in tracks:
        try:
            mk = t.markers.find_frame(frame, exact=True)
        except TypeError:
            mk = t.markers.find_frame(frame)
        if mk and not getattr(mk, "mute", False):
            items.append((t, float(mk.co[0]), float(mk.co[1])))
    return items


def _group_triplets_by_position_at_frame(clip: bpy.types.MovieClip, frame: int, tol_px: float = 3.0) -> List[Tuple[bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingTrack]]:
    """Bilde Triplets rein über räumliche Nähe im gegebenen Frame.
    - tol_px: Toleranz in Pixeln (auf norm. Koords skaliert).
    Speichert die Gruppierung als Namens‑Triplets im Clip.
    """
    w = int(getattr(clip, "size", [1, 1])[0] or 1)
    h = int(getattr(clip, "size", [1, 1])[1] or 1)
    tracks = list(clip.tracking.tracks)

    items = _collect_active_markers_on_frame(tracks, frame)
    if not items:
        clip[_TRIPLET_KEY] = []
        return []

    kd = KDTree(len(items))
    for i, (_, x, y) in enumerate(items):
        kd.insert((x * w, y * h, 0.0), i)
    kd.balance()

    used = set()
    triplets: List[Tuple[bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingTrack]] = []
    for i, (ti, xi, yi) in enumerate(items):
        if i in used:
            continue
        nearest = kd.find_n((xi * w, yi * h, 0.0), 3)
        cand = [j for (_, j, _) in nearest if j not in used]
        if len(cand) < 3:
            continue
        pts_px = [(items[j][1] * w, items[j][2] * h) for j in cand[:3]]
        dists = [
            math.hypot(pts_px[0][0] - pts_px[1][0], pts_px[0][1] - pts_px[1][1]),
            math.hypot(pts_px[0][0] - pts_px[2][0], pts_px[0][1] - pts_px[2][1]),
            math.hypot(pts_px[1][0] - pts_px[2][0], pts_px[1][1] - pts_px[2][1]),
        ]
        if max(dists) <= float(tol_px):
            trip = (items[cand[0]][0], items[cand[1]][0], items[cand[2]][0])
            triplets.append(trip)
            used.update(cand[:3])

    # Persistiere als Namen (stabil, undo‑freundlich)
    clip[_TRIPLET_KEY] = [[t0.name, t1.name, t2.name] for (t0, t1, t2) in triplets]
    return triplets


def _get_bound_triplets(clip: bpy.types.MovieClip, *, only_selected: bool = True) -> List[Tuple[bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingTrack]]:
    names_groups = clip.get(_TRIPLET_KEY)
    if not names_groups:
        return []
    name2track = {t.name: t for t in clip.tracking.tracks}
    groups: List[Tuple[bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingTrack]] = []
    for g in names_groups:
        if all(n in name2track for n in g):
            trip = (name2track[g[0]], name2track[g[1]], name2track[g[2]])
            groups.append(trip)
    if only_selected:
        groups = [g for g in groups if all(getattr(t, "select", False) for t in g)]
    return groups


# -----------------------------------------------------------------------------
# Triplet‑Kooperation anwenden (NON‑INSERT)
# -----------------------------------------------------------------------------

def _apply_triplet_cooperation_on_frame(clip: bpy.types.MovieClip, frame: int, *, only_selected: bool = True) -> int:
    triplets = _get_bound_triplets(clip, only_selected=only_selected)
    if not triplets:
        return 0

    processed = 0
    for a, b, c in triplets:
        ma, mb, mc = _find_marker_at_frame(a, frame), _find_marker_at_frame(b, frame), _find_marker_at_frame(c, frame)
        aa, ab, ac = _marker_active(ma), _marker_active(mb), _marker_active(mc)
        # 1) Ein Marker inaktiv/fehlend → alle muten (falls vorhanden)
        if not (aa and ab and ac):
            for tr in (a, b, c):
                _mute_if_exists(tr, frame)
            processed += 1
            continue
        # 2) Alle aktiv → dritten auf Mittelpunkt der nähesten beiden setzen (ohne Insert)
        p1, p2, p3 = _get_pos(a, frame), _get_pos(b, frame), _get_pos(c, frame)
        idx_third, mid = _nearest_pair_midpoint(p1, p2, p3)
        target = (a, b, c)[idx_third]
        if not _set_pos_if_exists(target, frame, mid):
            # Falls Zielmarker im Frame fehlt, konservativ: Triplet muten
            for tr in (a, b, c):
                _mute_if_exists(tr, frame)
        processed += 1
    return processed


# -----------------------------------------------------------------------------
# Zähl‑Utilities
# -----------------------------------------------------------------------------

def _count_total_markers(clip) -> int:
    try:
        return sum(len(t.markers) for t in clip.tracking.tracks)
    except Exception:
        return 0


def _count_tracks_with_marker_on_frame(clip, frame: int) -> int:
    cnt = 0
    try:
        for tr in clip.tracking.tracks:
            try:
                mk = tr.markers.find_frame(frame, exact=True)
            except TypeError:
                mk = tr.markers.find_frame(frame)
            if mk and not getattr(mk, "mute", False):
                cnt += 1
    except Exception:
        pass
    return cnt


# -----------------------------------------------------------------------------
# Operator
# -----------------------------------------------------------------------------

class CLIP_OT_bidirectional_track(Operator):
    bl_idname = "clip.bidirectional_track"
    bl_label = "Bidirectional Track"
    bl_description = "Vorwärts tracking (frameweise) mit Triplet-Kooperation (non-insert)."

    use_cooperative_triplets: bpy.props.BoolProperty(  # type: ignore
        name="Cooperative Triplets (pre-step)",
        default=False,
        description=(
            "Vor dem Vorwärts-Tracking auf dem aktuellen Frame Triplet-Kooperation anwenden. "
            "Wirkt auf zuvor positionsbasiert gebundene Triplets."
        ),
    )
    auto_enable_from_selection: bpy.props.BoolProperty(  # type: ignore
        name="Auto from Selection",
        default=True,
        description=(
            "Falls Anzahl selektierter Tracks ein Vielfaches von 3 ist, wird die Kooperations-Vorstufe aktiviert."
        ),
    )

    _timer = None
    _step = 0
    _start_frame = 0

    _prev_marker_count = -1
    _prev_frame = -1
    _stable_count = 0

    _t0 = 0.0
    _tick = 0

    def _dbg_header(self, context, clip):
        curf = context.scene.frame_current
        total = _count_total_markers(clip) if clip else -1
        on_cur = _count_tracks_with_marker_on_frame(clip, curf) if clip else -1
        print(
            "[BidiTrack] tick=%d | step=%d | t=%.3fs | frame=%d | markers_total=%d | tracks@frame=%d"
            % (self._tick, self._step, time.perf_counter() - self._t0, int(curf), int(total), int(on_cur))
        )

    def execute(self, context):
        context.scene["bidi_active"] = True
        context.scene["bidi_result"] = ""

        self._step = 0
        self._stable_count = 0
        self._prev_marker_count = -1
        self._prev_frame = -1
        self._start_frame = int(context.scene.frame_current)

        self._t0 = time.perf_counter()
        self._tick = 0

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)

        # Auto‑Enable, wenn 3n selektiert
        try:
            space = getattr(context, "space_data", None)
            clip = getattr(space, "clip", None) if space else None
            if self.auto_enable_from_selection and clip is not None:
                sel = [t for t in clip.tracking.tracks if getattr(t, "select", False)]
                if sel and len(sel) % 3 == 0:
                    self.use_cooperative_triplets = True
                    print("[BidiTrack] Auto‑enable cooperative triplets based on selection.")
        except Exception:
            pass

        # Einmalige positionsbasierte Gruppierung am Start‑Frame
        space = getattr(context, "space_data", None)
        clip = getattr(space, "clip", None) if space else None
        if clip is not None:
            try:
                formed = _group_triplets_by_position_at_frame(clip, self._start_frame, tol_px=3.0)
                print(f"[BidiTrack] Triplets (positional) bound @frame {self._start_frame} → groups={len(formed)}")
            except Exception as ex:
                print(f"[BidiTrack] Triplet binding failed: {ex!r}")

        total = _count_total_markers(clip) if clip else -1
        on_start = _count_tracks_with_marker_on_frame(clip, self._start_frame) if clip else -1
        print("[Tracking] Schritt: 0 (Start Forward‑Only Track‑Loop)")
        print("[BidiTrack] INIT | start_frame=%d | markers_total=%d | tracks@start=%d | coop=%s"
              % (int(self._start_frame), int(total), int(on_start), str(self.use_cooperative_triplets)))
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'TIMER':
            self._tick += 1
            print("[BidiTrack] TIMER tick=%d (dt=%.3fs seit Start)" % (self._tick, time.perf_counter() - self._t0))
            return self.run_tracking_step(context)
        return {'PASS_THROUGH'}

    def run_tracking_step(self, context):
        # Clip‑Ende
        self._frame_end = getattr(context.space_data.clip, "frame_duration", 0) or context.scene.frame_end

        space = getattr(context, "space_data", None)
        clip = getattr(space, "clip", None) if space else None
        if clip is None:
            self.report({'ERROR'}, "Kein aktiver Clip im Tracking-Editor gefunden.")
            print("[BidiTrack] ABORT: Kein aktiver Clip im Tracking-Editor.")
            return self._finish(context, result="FAILED")

        # Frame klemmen
        cf = int(max(1, context.scene.frame_current))
        if self._frame_end and cf > int(self._frame_end):
            cf = int(self._frame_end)
        if cf != context.scene.frame_current:
            context.scene.frame_current = cf

        self._dbg_header(context, clip)

        # Abbruch: keine aktiven Marker oder Clipende
        curf = int(context.scene.frame_current)
        if _count_tracks_with_marker_on_frame(clip, curf) == 0 or (self._frame_end and curf >= int(self._frame_end)):
            print("✓ Keine aktiven Marker mehr (oder Clipende) → FINISH")
            try:
                bpy.context.scene[_FORWARD_DONE_KEY] = True
            except Exception:
                pass
            return self._finish(context, result="FINISHED")

        # Triplet‑Kooperation (optional) am aktuellen Frame
        if self.use_cooperative_triplets:
            processed = _apply_triplet_cooperation_on_frame(clip, curf, only_selected=True)
            if processed > 0:
                print(f"[BidiTrack] Cooperative triplets applied on frame {curf} → groups={processed}")

        # Einen Frame vorwärts tracken (sequence=False)
        print("→ Vorwärts‑Tracking (ein Schritt)…")
        try:
            bpy.ops.clip.track_markers('EXEC_DEFAULT', backwards=False, sequence=False)
        except Exception as ex:
            print(f"[BidiTrack] Vorwärts‑Tracking Exception: {ex!r}")
            return self._finish(context, result="FAILED")

        # nach EXEC_DEFAULT-Call, noch auf curf bleiben:
        for _ in range(3):  # kleine Sicherheitswarteschleife
            try:
                bpy.context.view_layer.update()
                bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
            except Exception:
                pass
        
        nxt = curf + 1
        # sanity check: existieren Marker im nächsten Frame?
        if _count_tracks_with_marker_on_frame(clip, nxt) == 0:
            # ein zweites Mal kurz warten (Render/Depsgraph Nachlauf)
            for _ in range(5):
                try:
                    bpy.context.view_layer.update()
                    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
                except Exception:
                    pass
                if _count_tracks_with_marker_on_frame(clip, nxt) > 0:
                    break
        
        context.scene.frame_current = nxt


        # Nächster Frame
        nxt = curf + 1
        if self._frame_end and nxt > int(self._frame_end):
            print("→ Clipende erreicht.")
            return self._finish(context, result="FINISHED")
        context.scene.frame_current = nxt
        return {'PASS_THROUGH'}

    def _finish(self, context, result="FINISHED"):
        context.scene["bidi_active"] = False
        context.scene["bidi_result"] = str(result)

        total_time = time.perf_counter() - self._t0
        print(f"[BidiTrack] FINISH result={result} | total_time={total_time:.3f}s | ticks={self._tick}")

        self._cleanup_timer(context)
        return {'FINISHED'}

    def _cleanup_timer(self, context):
        wm = context.window_manager
        if self._timer is not None:
            try:
                wm.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None


def run_bidirectional_track(context):
    return bpy.ops.clip.bidirectional_track('INVOKE_DEFAULT')


def register():
    bpy.utils.register_class(CLIP_OT_bidirectional_track)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_bidirectional_track)
