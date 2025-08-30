# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/distanze.py
- Löscht NEUE Tracks (nach detect angelegt), die zu nah an ALTEN (Baseline) liegen.
- Baseline = Tracks aus pre_ptrs; deren Marker werden am Ziel-Frame ODER in ±baseline_window gesucht.
- Distanzmetrik: Pixel (aus marker.co normalisiert → Breite/Höhe).
- Regeln:
    1) Exact-Overlap: dist <= equal_eps_px  → neuer Track wird gelöscht.
    2) Nahe Umgebung: dist < close_dist_rel * width → neuer Track wird gelöscht.
- Selektion wird für NEUE Tracks gesnapshottet und nach dem Löschen je nach Flags wiederhergestellt.
"""

from __future__ import annotations
from typing import Dict, Iterable, Optional, Set, Tuple, List, Any

import bpy
from mathutils.kdtree import KDTree

__all__ = ["run_distance_cleanup"]


# ---------------------------------------------------------------------------
# Lightweight Logging (abschaltbar) -----------------------------------------
# ---------------------------------------------------------------------------

def _log(enabled: bool, msg: str) -> None:
    if enabled:
        try:
            print(msg)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Utility: Clip/Marker Helpers ----------------------------------------------
# ---------------------------------------------------------------------------

def _resolve_clip(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    """Finde den aktiven Movie Clip robust (Edit-Clip, Space-Clip, erster vorhandener)."""
    clip = getattr(context, "edit_movieclip", None)
    if clip:
        return clip
    space = getattr(context, "space_data", None)
    if space and getattr(space, "clip", None):
        return space.clip
    if bpy.data.movieclips:
        for c in bpy.data.movieclips:
            return c
    return None


def _find_marker_at_or_near_frame(
    track: bpy.types.MovieTrackingTrack,
    frame: int,
    *,
    window: int = 3
) -> Optional[bpy.types.MovieTrackingMarker]:
    """
    Suche exakten Marker; falls keiner vorhanden, nimm den zeitlich nächstgelegenen innerhalb ±window Frames.
    Verwendet für die BASELINE, damit KD-Tree nicht leer bleibt, wenn alte Marker nicht genau am Ziel-Frame liegen.
    """
    try:
        m = track.markers.find_frame(int(frame), exact=True)
    except TypeError:
        m = track.markers.find_frame(int(frame))
    if m:
        return m

    nearest = None
    best_dist = 10 ** 9
    for mk in track.markers:
        d = abs(int(mk.frame) - int(frame))
        if d <= window and d < best_dist:
            nearest = mk
            best_dist = d
    return nearest


def _collect_positions_at_frame(
    tracks: Iterable[bpy.types.MovieTrackingTrack],
    frame: int,
    w: int,
    h: int,
    *,
    baseline_window: int = 3
) -> List[Tuple[float, float]]:
    """
    Sammle Marker-Positionen der BASELINE-Tracks am Frame (oder nahe am Frame, ±baseline_window).
    Rückgabe in Pixel-Koordinaten.
    """
    out: List[Tuple[float, float]] = []
    for t in tracks:
        m = _find_marker_at_or_near_frame(t, int(frame), window=baseline_window)
        if not m or getattr(m, "mute", False):
            continue
        # m.co: normalized -> robust auf Pixel umrechnen
        x = float(m.co[0]) * float(w)
        y = float(m.co[1]) * float(h)
        out.append((x, y))
    return out


def _marker_set_select(m: bpy.types.MovieTrackingMarker, t: bpy.types.MovieTrackingTrack, state: bool) -> None:
    """Setzt Marker-Selektionsstatus robust (API-Versionen können leicht variieren)."""
    try:
        m.select = bool(state)
    except Exception:
        # Fallback: einige Blender-Versionen setzen Marker-Select über Track
        try:
            t.select = bool(state)
        except Exception:
            pass


def _delete_selected_tracks(*, confirm: bool = True) -> None:
    """Klein wrapper für den Operator – hält eine Stelle für künftige Varianten offen."""
    bpy.ops.clip.delete_track(confirm=bool(confirm))


# ---------------------------------------------------------------------------
# Hauptfunktion --------------------------------------------------------------
# ---------------------------------------------------------------------------

def run_distance_cleanup(
    context: bpy.types.Context,
    *,
    pre_ptrs: Set[int],
    frame: int,
    close_dist_rel: float = 0.01,          # 1% der Breite
    reselect_only_remaining: bool = True,  # ursprüngliche Selektion der verbleibenden NEUEN Tracks wiederherstellen
    select_remaining_new: bool = True,     # verbleibende NEUE Tracks aktiv selektieren
    verbose: bool = True,                  # Debug-Logs ein/aus
    baseline_window: int = 3,              # Baseline-Marker innerhalb ±baseline_window akzeptieren
    equal_eps_px: float = 0.5,             # "Exact Overlap" – ≤ eps → Delete unabhängig vom Threshold
) -> Dict[str, Any]:
    """
    Entfernt NEUE Tracks, die (pixelbasiert) zu nah an alten Tracks liegen.
    Rückgabe: {"status": "...", "removed": int, "remaining": int}
    """
    scn = context.scene
    _log(verbose, f"[DISTANZE] Start @frame={int(frame)} close_dist_rel={close_dist_rel} baseline_window=±{baseline_window} equal_eps_px={equal_eps_px}")

    clip = _resolve_clip(context)
    if not clip:
        _log(verbose, "[DISTANZE] Abbruch: kein Movie Clip im Kontext")
        return {"status": "FAILED", "reason": "no_movieclip"}

    tracking = clip.tracking
    width, height = int(clip.size[0]), int(clip.size[1])

    # Pointer-Mengen robust ermitteln (int)
    all_ptrs: Set[int] = {int(t.as_pointer()) for t in tracking.tracks}
    base_ptrs: Set[int] = all_ptrs & {int(p) for p in pre_ptrs}
    base_tracks = [t for t in tracking.tracks if int(t.as_pointer()) in base_ptrs]

    # Baseline-Positionen sammeln (in Pixel), KD-Tree bauen
    base_px = _collect_positions_at_frame(base_tracks, int(frame), width, height, baseline_window=baseline_window)
    kd: Optional[KDTree] = None
    if base_px:
        kd = KDTree(len(base_px))
        for i, (x, y) in enumerate(base_px):
            kd.insert((x, y, 0.0), i)
        kd.balance()

    _log(verbose, f"[DISTANZE] Clip={width}x{height} baseline_tracks={len(base_tracks)} baseline_markers_used={len(base_px)}")

    # Neue Tracks = Set-Differenz
    new_ptrs: Set[int] = all_ptrs - base_ptrs
    new_tracks = [t for t in tracking.tracks if int(t.as_pointer()) in new_ptrs]
    _log(verbose, f"[DISTANZE] new_tracks={len(new_tracks)} (all={len(all_ptrs)} | base={len(base_ptrs)})")

    # Selektion-Snapshot NUR für neue Tracks (minimal-invasiv)
    sel_snapshot_tracks = {t.as_pointer(): bool(getattr(t, "select", False)) for t in new_tracks}
    sel_snapshot_marker_at_f: Dict[int, bool] = {}
    for t in new_tracks:
        try:
            m = t.markers.find_frame(int(frame), exact=True)
        except TypeError:
            m = t.markers.find_frame(int(frame))
        if m is not None:
            try:
                sel_snapshot_marker_at_f[t.as_pointer()] = bool(getattr(m, "select", False))
            except Exception:
                pass

    # Kein KD-Tree oder keine neuen Tracks → nur Selektionspflege/Consistent State, keine Deletes
    if not kd or not new_tracks:
        _log(verbose, f"[DISTANZE] Skip: kd={'yes' if kd else 'no'} new={len(new_tracks)} → nur Selektionspflege")
        if select_remaining_new:
            for t in new_tracks:
                try:
                    t.select = True
                    try:
                        m = t.markers.find_frame(int(frame), exact=True)
                    except TypeError:
                        m = t.markers.find_frame(int(frame))
                    if m:
                        _marker_set_select(m, t, True)
                except Exception:
                    pass
        elif reselect_only_remaining:
            for t in new_tracks:
                try:
                    t.select = sel_snapshot_tracks.get(t.as_pointer(), False)
                    try:
                        m = t.markers.find_frame(int(frame), exact=True)
                    except TypeError:
                        m = t.markers.find_frame(int(frame))
                    if m is not None and t.as_pointer() in sel_snapshot_marker_at_f:
                        _marker_set_select(m, t, sel_snapshot_marker_at_f[t.as_pointer()])
                except Exception:
                    pass
        return {"status": "OK", "removed": 0, "remaining": len(new_tracks)}

    # Thresholds (Pixel)
    thr_px = max(1, int(width * (close_dist_rel if close_dist_rel > 0 else 0.01)))
    thr2 = float(thr_px) * float(thr_px)
    eps2 = float(equal_eps_px) * float(equal_eps_px)
    _log(verbose, f"[DISTANZE] threshold={thr_px}px  equal_eps={equal_eps_px}px  (rules: dist<=eps → delete; dist<thr → delete)")

    # Entscheidung: neue Tracks prüfen (nur Marker EXAKT am Ziel-Frame)
    reject_ptrs: Set[int] = set()
    for tr in new_tracks:
        try:
            m = tr.markers.find_frame(int(frame), exact=True)
        except TypeError:
            m = tr.markers.find_frame(int(frame))
        if not m or getattr(m, "mute", False):
            continue

        # Koordinaten: normalized → Pixel
        x = float(m.co[0]) * float(width)
        y = float(m.co[1]) * float(height)

        # Nächster Baseline-Punkt
        try:
            (loc, _idx, _dist) = kd.find((x, y, 0.0))
        except Exception:
            # Kein valider Nachbar → wie "weit weg" behandeln
            continue

        dx = x - loc[0]
        dy = y - loc[1]
        dist2 = (dx * dx + dy * dy)

        # Regel 1: Exact-Overlap (≤ eps) → löschen
        if dist2 <= eps2:
            reject_ptrs.add(tr.as_pointer())
            _log(verbose, f"[DISTANZE] REJECT {tr.name} dist={dist2 ** 0.5:.2f}px (≤ eps {equal_eps_px})")
        # Regel 2: Nahe Umgebung (< thr) → löschen
        elif dist2 < thr2:
            reject_ptrs.add(tr.as_pointer())
            _log(verbose, f"[DISTANZE] REJECT {tr.name} dist={dist2 ** 0.5:.2f}px (< thr {thr_px})")
        else:
            _log(verbose, f"[DISTANZE] KEEP   {tr.name} dist={dist2 ** 0.5:.2f}px")

    # Löschen – selektiv genau diese neuen Tracks
    removed = 0
    if reject_ptrs:
        _log(verbose, f"[DISTANZE] Lösche {len(reject_ptrs)} Track(s)")

        # 1) Alle neuen Tracks temporär deselektieren
        for t in new_tracks:
            try:
                t.select = False
            except Exception:
                pass

        # 2) Nur die abzulehnenden selektieren → delete_track löscht exakt diese
        for t in new_tracks:
            try:
                if t.as_pointer() in reject_ptrs:
                    t.select = True
            except Exception:
                pass

        # 3) Delete via Operator, ggf. Fallback .remove()
        hard_removed: Set[int] = set()
        try:
            _delete_selected_tracks(confirm=True)
            hard_removed = set(reject_ptrs)
            removed = len(hard_removed)
            _log(verbose, f"[DISTANZE] delete_track(): removed={removed} via Operator")
        except Exception as e:
            _log(verbose, f"[DISTANZE] Operator-Delete failed ({e}) → Fallback remove()")
            # Fallback: harte Entfernung per API
            for t in list(tracking.tracks):
                try:
                    if t.as_pointer() in reject_ptrs:
                        tracking.tracks.remove(t)
                        hard_removed.add(t.as_pointer())
                except Exception:
                    pass
            removed = len(hard_removed)

        # 4) Ursprungs-Selektion für verbleibende NEUE wiederherstellen (optional)
        if reselect_only_remaining:
            _log(verbose, "[DISTANZE] Restore: reselect_only_remaining")
            for t in tracking.tracks:
                try:
                    tptr = t.as_pointer()
                    if tptr in base_ptrs:
                        continue            # Baseline nicht anfassen
                    if tptr in hard_removed:
                        continue            # gibt's nicht mehr
                    # Track-Selektionsstatus zurücksetzen
                    if tptr in sel_snapshot_tracks:
                        t.select = sel_snapshot_tracks[tptr]
                    # Marker-Selektion am Frame zurücksetzen
                    try:
                        mm = t.markers.find_frame(int(frame), exact=True)
                    except TypeError:
                        mm = t.markers.find_frame(int(frame))
                    if mm is not None and tptr in sel_snapshot_marker_at_f:
                        _marker_set_select(mm, t, sel_snapshot_marker_at_f[tptr])
                except Exception:
                    pass

    # Verbleibende NEUE bestimmen (nach Löschung)
    remaining_new = [t for t in tracking.tracks if int(t.as_pointer()) not in base_ptrs]

    if select_remaining_new:
        _log(verbose, f"[DISTANZE] Select remaining new: {len(remaining_new)}")
        for t in remaining_new:
            try:
                t.select = True
                try:
                    m = t.markers.find_frame(int(frame), exact=True)
                except TypeError:
                    m = t.markers.find_frame(int(frame))
                if m:
                    _marker_set_select(m, t, True)
            except Exception:
                pass
    elif reselect_only_remaining:
        _log(verbose, "[DISTANZE] Restore snapshot for remaining new")
        for t in remaining_new:
            try:
                tptr = t.as_pointer()
                t.select = sel_snapshot_tracks.get(tptr, getattr(t, "select", False))
                try:
                    m = t.markers.find_frame(int(frame), exact=True)
                except TypeError:
                    m = t.markers.find_frame(int(frame))
                if m is not None and tptr in sel_snapshot_marker_at_f:
                    _marker_set_select(m, t, sel_snapshot_marker_at_f[tptr])
            except Exception:
                pass

    try:
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
    except Exception:
        pass

    _log(verbose, f"[DISTANZE] Cleanup fertig, removed={removed}, remaining_new={len(remaining_new)}")
    return {"status": "OK", "removed": int(removed), "remaining": int(len(remaining_new))}
