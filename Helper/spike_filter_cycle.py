# File: Helper/spike_filter_cycle.py
from __future__ import annotations
"""
Spike-Filter-Cycle Helper
-------------------------
Dieser Helper wird an die Funktionskette angehängt, wenn Helper/find_low_marker_frame.py
keinen passenden Frame findet. Er wechselt zyklisch zwischen:
    1) Helper/clean_short_tracks.clean_short_tracks()
    2) Spike-Filter-Schritt (bpy.ops.clip.filter_tracks + Löschen selektierter Tracks)
    3) Helper/find_low_marker_frame.run_find_low_marker_frame()

… bis find_low_marker_frame einen Frame liefert, der < (marker_baseline * 2) ist.

Parameter:
- marker_baseline: int|None – Basisframe für die Prüfung. Fällt zurück auf
  scene.marker_frame oder scene.frame_current.
- track_threshold: float – Start-Threshold für bpy.ops.clip.filter_tracks. Beginnt z.B. bei 100.0
  und wird pro Zyklus abgesenkt (aggressiver).
- max_loops: int – Schutz gegen Endlosschleifen.

Rückgabe (dict):
- status: "FINISHED" | "NONE" | "FAILED"
- frame: gefundener Frame (falls FINISHED)
- loops: Anzahl durchlaufener Zyklen
- reason: Fehler-/Abbruchgrund (optional)
"""

from typing import Optional, Dict, Any
import bpy

from .find_low_marker_frame import run_find_low_marker_frame
from .clean_short_tracks import clean_short_tracks  # verwendet vorhandene Funktionalität


# ---------------------------------------------------------------------------
# Interna
# ---------------------------------------------------------------------------

def _get_active_clip(context) -> Optional[bpy.types.MovieClip]:
    """Versucht, den aktiven MovieClip zu ermitteln."""
    space = getattr(context, "space_data", None)
    if getattr(space, "type", None) == 'CLIP_EDITOR' and getattr(space, "clip", None):
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
        # Direkter Operator-Versuch
        if bpy.ops.clip.delete_track.poll():
            bpy.ops.clip.delete_track()
            op_ok = True
        else:
            # Context-Override für CLIP_EDITOR
            win = context.window
            # win kann in seltenen Fällen None sein (Unit-Tests/Headless)
            if win is not None:
                area = next((a for a in win.screen.areas if a.type == 'CLIP_EDITOR'), None)
                if area is not None:
                    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                    space = next((s for s in area.spaces if s.type == 'CLIP_EDITOR'), None)
                    if region and space:
                        with bpy.context.temp_override(window=win, area=area, region=region, space_data=space):
                            if bpy.ops.clip.delete_track.poll():
                                bpy.ops.clip.delete_track()
                                op_ok = True
    except Exception:
        op_ok = False

    if op_ok:
        # Nach Operator: erneut aktuelle Collection ermitteln (kann sich ändern)
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
    - Multiplikation × 0.9 sorgt für sanfte Absenkung.
    - Falls dies numerisch keine Änderung bewirkt, dekrementiere um 1.0.
    - Nicht unter 0.0 fallen lassen.
    """
    next_thr = float(thr) * 0.9
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
    max_loops: int = 10,
) -> Dict[str, Any]:
    """Wechselt zwischen clean_short_tracks → Spike-Filter (selektierte Tracks löschen) → find_low_marker_frame,
    bis find_low einen Frame findet, der < (marker_baseline * 2) ist.
    """

    # Baseline bestimmen
    baseline = int(
        marker_baseline
        if marker_baseline is not None
        else int(getattr(context.scene, "marker_frame", context.scene.frame_current) or context.scene.frame_current)
    )
    target_limit = baseline * 2

    # Sanity: Clip vorhanden?
    if not _get_active_clip(context):
        return {"status": "FAILED", "reason": "no active MovieClip"}

    loops = 0
    thr = float(track_threshold)

    while loops < int(max_loops):
        loops += 1

        # Schritt 1: find_low versuchen
        try:
            low_res = run_find_low_marker_frame(context)
        except Exception as ex:
            print(f"[SpikeCycle] find_low failed: {ex!r}")
            low_res = {"status": "FAILED", "reason": repr(ex)}

        status = str(low_res.get("status", "FAILED")).upper()
        if status == "FOUND":
            frame = int(low_res.get("frame", baseline))
            if frame < int(target_limit):
                print(f"[SpikeCycle] FOUND suitable frame={frame} (< {target_limit}) after {loops} loop(s)")
                return {"status": "FINISHED", "frame": frame, "loops": loops}
            else:
                print(f"[SpikeCycle] FOUND frame={frame} but >= {target_limit} → weiter zyklieren")
        elif status not in {"NONE", "FAILED"}:
            # Unerwarteter Status → trotzdem weiter zyklieren
            print(f"[SpikeCycle] find_low status={status} → weiter")

        # Schritt 2: kurze Tracks bereinigen (bestehender Helper)
        try:
            frames_min = int(getattr(context.scene, "frames_track", 25) or 25)
            clean_short_tracks(context, min_len=frames_min, verbose=True)
            print(f"[SpikeCycle] clean_short_tracks done (min_len={frames_min})")
        except TypeError:
            try:
                clean_short_tracks(context)
                print("[SpikeCycle] clean_short_tracks done (fallback signature)")
            except Exception as ex_clean:
                print(f"[SpikeCycle] clean_short_tracks failed: {ex_clean!r}")
        except Exception as ex_clean:
            print(f"[SpikeCycle] clean_short_tracks failed: {ex_clean!r}")

        # Schritt 3: Spike-Filter anwenden und selektierte Tracks komplett löschen
        try:
            # a) Problematische Tracks anhand Bewegungs-Spikes selektieren
            bpy.ops.clip.filter_tracks(track_threshold=float(thr))
            print(f"[SpikeCycle] filter_tracks(track_threshold={thr})")

            # b) Alle dadurch selektierten Tracks komplett löschen (Operator + Fallback)
            removed = _remove_selected_tracks(context)
            print(f"[SpikeCycle] removed {removed} track(s) selected by filter")

            # c) Threshold für nächste Runde absenken (aggressiver werden)
            thr = _lower_threshold(thr)
            print(f"[SpikeCycle] next track_threshold → {thr}")

        except Exception as ex_ops:
            print(f"[SpikeCycle] spike-filter step failed: {ex_ops!r}")

        # Schleife fortsetzen
        print(f"[SpikeCycle] loop {loops}/{max_loops} completed → retry")

    # Abbruch nach max_loops
    print(f"[SpikeCycle] max_loops ({max_loops}) reached without suitable frame")
    return {"status": "NONE", "reason": "max_loops_exceeded", "loops": loops}
