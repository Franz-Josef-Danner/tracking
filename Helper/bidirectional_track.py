import bpy
import math
import time
import re   # <<< NEU
from bpy.types import Operator
from typing import List, Tuple, Dict
from mathutils.kdtree import KDTree

# -----------------------------------------------------------------------------
# NEU: Triplet‑Kooperation (nicht-invasiv)
# -----------------------------------------------------------------------------
# Ziel: Vor dem bestehenden Vorwärts/Rückwärts‑Tracking optional pro Frame
# Triplets kooperieren lassen:
#  - Ist einer der drei Marker auf dem Frame inaktiv → alle drei inaktiv.
#  - Sind alle aktiv → zwei nächst beieinander liegende finden, dritten
#    Marker auf deren Mittelpunkt setzen.
#  - *Nur* Vorbereitung auf dem aktuellen Frame; das eigentliche Tracking
#    bleibt unverändert (sequence=False), damit bestehender Ablauf unberührt.
_TRIPLET_KEY = "__coop_triplets"   # Clip-Property
_FORWARD_DONE_KEY = "__bidi_forward_done"  # Cleanup-Gate

Vec2 = Tuple[float, float]

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

def _group_triplets_by_position_at_frame(clip, frame: int, tol_px: float = 3.0) -> list[tuple]:
    """Bilde Triplets rein über räumliche Nähe im gegebenen Frame.
    - tol_px: Toleranz in Pixeln (auf norm. Koords skaliert).
    """
    w = int(getattr(clip, "size", [1, 1])[0] or 1)
    h = int(getattr(clip, "size", [1, 1])[1] or 1)
    tracks = list(clip.tracking.tracks)

    items = _collect_active_markers_on_frame(tracks, frame)
    if not items:
        return []

    # KDTree auf Pixelkoordinaten
    kd = KDTree(len(items))
    for i, (_, x, y) in enumerate(items):
        kd.insert((x * w, y * h, 0.0), i)
    kd.balance()

    used = set()
    triplets = []
    for i, (ti, xi, yi) in enumerate(items):
        if i in used:
            continue
        # Nächste 3 Nachbarn (einschl. self)
        nearest = kd.find_n((xi * w, yi * h, 0.0), 3)
        cand = [j for (_, j, _) in nearest if j not in used]
        if len(cand) < 3:
            continue
        # Abstands-Check (alle drei unter tol)
        pts_px = [(items[j][1] * w, items[j][2] * h) for j in cand[:3]]
        dists = [
            math.hypot(pts_px[0][0]-pts_px[1][0], pts_px[0][1]-pts_px[1][1]),
            math.hypot(pts_px[0][0]-pts_px[2][0], pts_px[0][1]-pts_px[2][1]),
            math.hypot(pts_px[1][0]-pts_px[2][0], pts_px[1][1]-pts_px[2][1]),
        ]
        if max(dists) <= float(tol_px):
            trip = (items[cand[0]][0], items[cand[1]][0], items[cand[2]][0])
            triplets.append(trip)
            used.update(cand[:3])

    # Persistiere als Namen (stabil, undo-freundlich)
    clip[_TRIPLET_KEY] = [[t0.name, t1.name, t2.name] for (t0, t1, t2) in triplets]
    return triplets

def _get_bound_triplets(clip, only_selected=True) -> list[tuple]:
    """Liest persistierte Triplets; fällt auf Name‑Grouping zurück, wenn leer."""
    names_groups = clip.get(_TRIPLET_KEY)
    if names_groups:
        name2track = {t.name: t for t in clip.tracking.tracks}
        groups = []
        for g in names_groups:
            if all(n in name2track for n in g):
                trip = (name2track[g[0]], name2track[g[1]], name2track[g[2]])
                groups.append(trip)
        if groups:
            if only_selected:
                groups = [g for g in groups if all(getattr(t, "select", False) for t in g)]
            return groups
    # Fallback (alt): Name‑Präfix (nur wenn nix gebunden wurde)
    return _group_triplets_by_name([t for t in clip.tracking.tracks if (t.select if only_selected else True)])
    
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

def _set_pos_if_exists(track: bpy.types.MovieTrackingTrack, frame: int, pos: tuple[float, float]) -> bool:
    """Setzt die Position nur, wenn im Frame bereits ein Marker existiert.
    Gibt True zurück, wenn gesetzt wurde; sonst False (kein Insert!)."""
    mk = _find_marker_at_frame(track, frame)
    if mk is None:
        return False
    mk.co[0], mk.co[1] = float(pos[0]), float(pos[1])
    return True

def _mute_if_exists(track: bpy.types.MovieTrackingTrack, frame: int) -> None:
    """Setzt den Marker im Frame auf mute, falls er existiert. Kein Insert."""
    mk = _find_marker_at_frame(track, frame)
    if mk is not None and hasattr(mk, "mute"):
        mk.mute = True
    # Kein globales track.mute setzen (würde alle Frames betreffen)

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


def _prefix_before_last_us(name: str) -> str:
    # Akzeptiere Endungen wie "_001" ODER ".001"
    return re.sub(r'([_.])\d+$', '', name)


def _group_triplets_by_name(tracks: List[bpy.types.MovieTrackingTrack]) -> List[Tuple[bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingTrack]]:
    buckets: Dict[str, List[bpy.types.MovieTrackingTrack]] = {}
    for t in tracks:
        buckets.setdefault(_prefix_before_last_us(t.name), []).append(t)
    groups = []
    for _, lst in buckets.items():
        if len(lst) >= 3:
            lst = sorted(lst, key=lambda x: x.name)
            for i in range(0, len(lst) - 2, 3):
                groups.append((lst[i], lst[i + 1], lst[i + 2]))
    return groups


def _apply_triplet_cooperation_on_frame(clip: bpy.types.MovieClip, frame: int,
                                         only_selected: bool = True,
                                         prefer_name_grouping: bool = True) -> int:
    """Wendet die Regel auf alle erkannten Triplets an (nur aktueller Frame).
    Rückgabe: Anzahl verarbeiteter Triplets.
    """
    tracks_all = list(clip.tracking.tracks)
    tracks = [t for t in tracks_all if (t.select if only_selected else True)]
    if not tracks:
        return 0

    triplets = _group_triplets_by_name(tracks) if prefer_name_grouping else []
    if not triplets and not prefer_name_grouping:
        return 0
    if not triplets:
        # Fallback: keine Gruppen → nichts tun (konservativ, um Verhalten nicht zu ändern)
        return 0

    processed = 0
    for a, b, c in triplets:
        ma, mb, mc = _find_marker_at_frame(a, frame), _find_marker_at_frame(b, frame), _find_marker_at_frame(c, frame)
        aa, ab, ac = _marker_active(ma), _marker_active(mb), _marker_active(mc)
        # Regel 1: sobald einer inaktiv/fehlend ⇒ alle (existierenden) Marker im Frame muten
        if not (aa and ab and ac):
            for tr in (a, b, c):
                _mute_if_exists(tr, frame)
            processed += 1
            continue
        # Regel 2: alle aktiv ⇒ „dritten“ auf Mittelpunkt der beiden nächsten setzen (ohne Insert)
        p1, p2, p3 = _get_pos(a, frame), _get_pos(b, frame), _get_pos(c, frame)
        idx_third, mid = _nearest_pair_midpoint(p1, p2, p3)
        target = (a, b, c)[idx_third]
        if not _set_pos_if_exists(target, frame, mid):
            # Falls der Ziel‑Marker im Frame fehlt, behandeln wir das Triplet als inaktiv
            for tr in (a, b, c):
                _mute_if_exists(tr, frame)
        processed += 1
    return processed


# -----------------------------------------------------------------------------
# Bestehende Zähl‑Utilities
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


class CLIP_OT_bidirectional_track(Operator):
    bl_idname = "clip.bidirectional_track"
    bl_label = "Bidirectional Track"
    bl_description = "Trackt Marker vorwärts und rückwärts (sichtbar im UI) und signalisiert Fertig an Orchestrator"

    # NEU: Option, Triplet‑Kooperation vor dem Tracking pro aktuellem Frame anzuwenden
    use_cooperative_triplets: bpy.props.BoolProperty(  # type: ignore
        name="Cooperative Triplets (pre-step)",
        default=False,
        description=(
            "Vor dem Vorwärts/Rückwärts‑Tracking auf dem aktuellen Frame Triplet‑Kooperation anwenden. "
            "Wirkt nur, wenn die Auswahl in Dreiergruppen per Namenspräfix erkannt wird."
        ),
    )
    auto_enable_from_selection: bpy.props.BoolProperty(  # type: ignore
        name="Auto from Selection",
        default=True,
        description=(
            "Falls genau 3, 6, 9, … Tracks selektiert sind und Namensgruppen erkannt werden, "
            "aktiviert sich die Kooperations‑Vorstufe automatisch."
        ),
    )

    _timer = None
    _step = 0
    _start_frame = 0

    _prev_marker_count = -1
    _prev_frame = -1
    _stable_count = 0

    # Debug/Tracing
    _t0 = 0.0
    _tick = 0
    _t_last_action = 0.0

    def _dbg_header(self, context, clip):
        curf = context.scene.frame_current
        total = _count_total_markers(clip) if clip else -1
        on_cur = _count_tracks_with_marker_on_frame(clip, curf) if clip else -1
        print(
            "[BidiTrack] tick=%d | step=%d | t=%.3fs | frame=%d | "
            "markers_total=%d | tracks@frame=%d"
            % (self._tick, self._step, time.perf_counter() - self._t0, int(curf), int(total), int(on_cur))
        )

    def execute(self, context):
        # Flags für Orchestrator setzen
        context.scene["bidi_active"] = True
        context.scene["bidi_result"] = ""

        self._step = 0
        self._stable_count = 0
        self._prev_marker_count = -1
        self._prev_frame = -1
        self._start_frame = context.scene.frame_current

        self._t0 = time.perf_counter()
        self._t_last_action = self._t0
        self._tick = 0

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)

        # AUTO‑Erkennung: wenn Auswahl plausibel Triplets beinhaltet, auto‑enable
        try:
            space = getattr(context, "space_data", None)
            clip = getattr(space, "clip", None) if space else None
            if self.auto_enable_from_selection and clip is not None:
                sel = [t for t in clip.tracking.tracks if getattr(t, "select", False)]
                if sel and len(sel) % 3 == 0:
                    # Prüfe, ob Namens‑Triplets gefunden werden können
                    if _group_triplets_by_name(sel):
                        self.use_cooperative_triplets = True
                        print("[BidiTrack] Auto‑enable cooperative triplets based on selection.")
        except Exception:
            pass

        # Erste Umgebungsausgabe
        space = getattr(context, "space_data", None)
        clip = getattr(space, "clip", None) if space else None
        total = _count_total_markers(clip) if clip else -1
        on_start = _count_tracks_with_marker_on_frame(clip, self._start_frame) if clip else -1
        print("[Tracking] Schritt: 0 (Start Forward‑Only Track‑Loop)")
        print("[BidiTrack] INIT | start_frame=%d | markers_total=%d | tracks@start=%d | coop=%s"
              % (int(self._start_frame), int(total), int(on_start), str(self.use_cooperative_triplets)))
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'TIMER':
            self._tick += 1
            print("[BidiTrack] TIMER tick=%d (dt=%.3fs seit Start)"
                  % (self._tick, time.perf_counter() - self._t0))
            return self.run_tracking_step(context)
        return {'PASS_THROUGH'}

    def run_tracking_step(self, context):
        # Clip‑Ende ermitteln
        self._frame_end = getattr(context.space_data.clip, "frame_duration", 0) or context.scene.frame_end
    
        space = getattr(context, "space_data", None)
        clip = getattr(space, "clip", None) if space else None
        if clip is None:
            self.report({'ERROR'}, "Kein aktiver Clip im Tracking-Editor gefunden.")
            print("[BidiTrack] ABORT: Kein aktiver Clip im Tracking-Editor.")
            return self._finish(context, result="FAILED")
    
        # Aktuellen Frame sicherheitshalber einklemmen
        cf = int(context.scene.frame_current)
        if cf < 1:
            cf = 1
        if self._frame_end and cf > int(self._frame_end):
            cf = int(self._frame_end)
        if cf != context.scene.frame_current:
            context.scene.frame_current = cf
    
        self._dbg_header(context, clip)
    
        # ---- Forward‑Only Loop ----
        curf = int(context.scene.frame_current)
        # Abbruchkriterien: kein aktiver Marker im aktuellen Frame oder Clipende erreicht
        if _count_tracks_with_marker_on_frame(clip, curf) == 0 or (self._frame_end and curf >= int(self._frame_end)):
            print("✓ Keine aktiven Marker mehr (oder Clipende) → FINISH")
            try:
                bpy.context.scene[_FORWARD_DONE_KEY] = True
            except Exception:
                pass
            return self._finish(context, result="FINISHED")

        # 1) Triplet‑Kooperation (optional) auf dem *aktuellen* Frame
        if self.use_cooperative_triplets:
            processed = _apply_triplet_cooperation_on_frame(
                clip, curf, only_selected=True, prefer_name_grouping=True
            )
            if processed > 0:
                print(f"[BidiTrack] Cooperative triplets applied on frame {curf} → groups={processed}")

        # 2) Einen Frame vorwärts tracken (sequence=False)
        print("→ Vorwärts‑Tracking (ein Schritt)…")
        try:
            bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=False)
        except Exception as ex:
            print(f"[BidiTrack] Vorwärts‑Tracking Exception: {ex!r}")
            return self._finish(context, result="FAILED")

        # 3) Zum *nächsten* Frame gehen
        nxt = curf + 1
        if self._frame_end and nxt > int(self._frame_end):
            print("→ Clipende erreicht.")
            return self._finish(context, result="FINISHED")
        context.scene.frame_current = nxt
        return {'PASS_THROUGH'}

    def run_tracking_stability_check(self, context, clip):
        current_frame = context.scene.frame_current
        current_marker_count = _count_total_markers(clip)
        tracks_on_cur = _count_tracks_with_marker_on_frame(clip, current_frame)

        if (self._prev_marker_count == current_marker_count and
                self._prev_frame == current_frame):
            self._stable_count += 1
        else:
            if self._prev_marker_count != -1:
                print(
                    "[BidiTrack] Änderung erkannt | "
                    f"prev_markers={self._prev_marker_count} -> now={current_marker_count} | "
                    f"prev_frame={self._prev_frame} -> now={current_frame}"
                )
            self._stable_count = 0

        self._prev_marker_count = current_marker_count
        self._prev_frame = current_frame

        print(
            f"[Tracking-Stabilität] Frame: {current_frame}, "
            f"Marker_total: {current_marker_count}, tracks@frame: {tracks_on_cur}, "
            f"Stabil: {self._stable_count}/2"
        )

        try:
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        except Exception:
            pass

        if self._stable_count >= 2:
            print("✓ Tracking stabil erkannt – gebe Fertig-Signal an Orchestrator.")
            return self._finish(context, result="FINISHED")

        if self._stable_count == 0:
            dt = time.perf_counter() - self._t_last_action
            if dt > 1.5:
                print(f"[BidiTrack] Hinweis: Seit {dt:.2f}s keine Stabilität. "
                      "Operatoren evtl. noch busy oder keine Markerbewegung messbar.")

        return {'PASS_THROUGH'}

    def _finish(self, context, result="FINISHED"):
        context.scene["bidi_active"] = False
        context.scene["bidi_result"] = str(result)

        total_time = time.perf_counter() - self._t0
        print(f"[BidiTrack] FINISH result={result} | total_time={total_time:.3f}s | ticks={self._tick}")

        self._cleanup_timer(context)

        # Kopf der Datei, bei den anderen Keys:
        _FORWARD_DONE_KEY = "__bidi_forward_done"  # vom Helper gesetzt
        
        # ... in deinem Ablauf nach BIDI (Beispiel: in der Methode/State-Transition,
        # wo aktuell nach dem Bidirectional-Track stets CLEAN_SHORT gestartet wird):
        scene = context.scene
        if not bool(scene.get(_FORWARD_DONE_KEY, False)):
            print("[Coord] CLEAN_SHORT gated: warte auf Vorwärts-Track-Signal …")
            # → nochmal BIDI starten ODER einfach im selben State bleiben,
            #    je nachdem, wie du deine Loop baust (RUNNING_MODAL / Timer-Tick etc.).
            return {'RUNNING_MODAL'}  # oder State nicht wechseln
        # Signal konsumieren und Cleanup starten
        scene[_FORWARD_DONE_KEY] = False
        print("[Coord] Signal erhalten → starte CLEAN_SHORT …")

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
    """Startet den Operator aus Skript-Kontext."""
    return bpy.ops.clip.bidirectional_track('INVOKE_DEFAULT')


# ---- Registrierung für Haupt-__init__.py ----

def register():
    bpy.utils.register_class(CLIP_OT_bidirectional_track)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_bidirectional_track)
