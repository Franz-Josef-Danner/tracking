from __future__ import annotations
"""
Spike-Filter-Cycle Helper (finder- & clean-frei im Loop)
-------------------------------------------------------

Strikte Verantwortlichkeit:
- **Dieses Modul** führt ausschließlich den Spike-Filter-Zyklus aus: Filter anwenden,
  selektierte Tracks entfernen, Threshold senken, wiederholen.
- **Kein** `clean_short_tracks` mehr im Loop (wird **einmalig** extern vom Coordinator
  im State `CYCLE_CLEAN` ausgeführt).
- **Keine** Finder-Logik hier (die läuft separat, z. B. `run_find_max_marker_frame`).

Rückgabe (dict):
* status: "NONE" | "FAILED"
* loops: Anzahl durchlaufener Zyklen
* reason: Fehler-/Abbruchgrund (optional)
"""

from typing import Optional, Dict, Any
import bpy

__all__ = ["run_spike_filter_cycle"]


# ---------------------------------------------------------------------------
# Interna
# ---------------------------------------------------------------------------


def _get_active_clip(context) -> Optional[bpy.types.MovieClip]:
    """Versucht, den aktiven MovieClip zu ermitteln."""
    space = getattr(context, "space_data", None)
    if getattr(space, "type", None) == "CLIP_EDITOR" and getattr(space, "clip", None):
        return space.clip
    try:
        return bpy.data.movieclips[0] if bpy.data.movieclips else None
    except Exception:
        return None


def _get_tracks_collection(clip) -> Optional[bpy.types.bpy_prop_collection]:
    """Bevorzuge Tracks des aktiven Tracking-Objekts; Fallback: globale Tracks."""
    try:
        obj = clip.tracking.objects.active
        if obj and getattr(obj, "tracks", None):
            return obj.tracks
    except Exception:
        pass
    try:
        return clip.tracking.tracks
    except Exception:
        return None


def _remove_selected_tracks(context) -> int:
    """Löscht selektierte Tracks. Erst per Operator, dann Fallback via API.
    Zählt die Anzahl effektiv entfernter Tracks.
    """
    clip = _get_active_clip(context)
    if not clip:
        return 0

    tracks = _get_tracks_collection(clip)
    if tracks is None:
        return 0

    # ------- Versuch A: Operator (löscht auch, wenn nur Marker selektiert) -------
    before = len(tracks)
    op_ok = False
    try:
        if bpy.ops.clip.delete_track.poll():
            bpy.ops.clip.delete_track()
            op_ok = True
        else:
            win = context.window
            if win is not None:
                area = next((a for a in win.screen.areas if a.type == "CLIP_EDITOR"), None)
                if area is not None:
                    region = next((r for r in area.regions if r.type == "WINDOW"), None)
                    space = next((s for s in area.spaces if s.type == "CLIP_EDITOR"), None)
                    if region and space:
                        with bpy.context.temp_override(window=win, area=area, region=region, space_data=space):
                            if bpy.ops.clip.delete_track.poll():
                                bpy.ops.clip.delete_track()
                                op_ok = True
    except Exception:
        op_ok = False

    if op_ok:
        clip_after = _get_active_clip(context)
        tracks_after = _get_tracks_collection(clip_after) or []
        removed = max(0, before - len(tracks_after))
        return removed

    # ------- Versuch B: Direktes Entfernen in Python-API (Track/Marker-Select) ---
    try:
        to_delete = []
        for tr in list(tracks):
            sel_track = bool(getattr(tr, "select", False))
            sel_marker = False
            try:
                sel_marker = any(bool(getattr(m, "select", False)) for m in tr.markers)
            except Exception:
                pass
            if sel_track or sel_marker:
                to_delete.append(tr)

        deleted = 0
        for tr in to_delete:
            try:
                tracks.remove(tr)
                deleted += 1
            except Exception:
                pass
        return deleted
    except Exception:
        return 0


def _lower_threshold(thr: float) -> float:
    """Senkt den Threshold progressiv ab.
    - Multiplikation × 0.975 sorgt für sanfte Absenkung.
    - Falls dies numerisch keine Änderung bewirkt, dekrementiere um 1.0.
    - Nicht unter 0.0 fallen lassen.
    """
    next_thr = float(thr) * 0.975
    if abs(next_thr - float(thr)) < 1e-6 and thr > 0.0:
        next_thr = float(thr) - 1.0
    if next_thr < 0.0:
        next_thr = 0.0
    return next_thr


# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------

def run_spike_filter_cycle(
    context: bpy.types.Context,
    *,
    marker_baseline: Optional[int] = None,
    track_threshold: float = 100.0,
    max_loops: int = 90,
) -> Dict[str, Any]:
    """Führt den Spike-Filter-Zyklus **ohne Clean & ohne Finder** aus.

    Ablauf je Loop:
      1) `bpy.ops.clip.filter_tracks(track_threshold=thr)` ausführen.
      2) selektierte Tracks löschen.
      3) Threshold für den nächsten Loop absenken.

    Abbruch nach `max_loops`. Erfolg/Misserfolg bewertet ausschließlich die
    übergeordnete Orchestrierung (Coordinator-FSM) anhand nachgelagerter Finder.
    """

    # Baseline wird ggf. noch für externe Logs/Abbruchkriterien verwendet.
    _ = int(
        marker_baseline
        if marker_baseline is not None
        else int(getattr(context.scene, "marker_frame", context.scene.frame_current) or context.scene.frame_current)
    )

    if not _get_active_clip(context):
        return {"status": "FAILED", "reason": "no active MovieClip"}

    loops = 0
    thr = float(track_threshold)

    while loops < int(max_loops):
        loops += 1

        # 1) Spike-Filter anwenden und selektierte Tracks löschen
        try:
            bpy.ops.clip.filter_tracks(track_threshold=float(thr))
            print(f"[SpikeCycle] filter_tracks(track_threshold={thr})")
            removed = _remove_selected_tracks(context)
            print(f"[SpikeCycle] removed {removed} track(s) selected by filter")
        except Exception as ex_ops:
            print(f"[SpikeCycle] spike-filter step failed: {ex_ops!r}")

        # 2) Threshold anpassen
        thr = _lower_threshold(thr)
        print(f"[SpikeCycle] next track_threshold → {thr}")

        print(f"[SpikeCycle] loop {loops}/{max_loops} completed → retry")

    print(f"[SpikeCycle] max_loops ({max_loops}) reached")
    return {"status": "NONE", "reason": "max_loops_exceeded", "loops": loops}
