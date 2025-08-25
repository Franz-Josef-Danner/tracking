# File: Helper/spike_filter_cycle.py
from __future__ import annotations
"""
Spike-Filter-Cycle Helper
-------------------------
Dieser Helper wird an die Funktionskette angehängt, wenn Helper/find_low_marker_frame.py
keinen passenden Frame findet. Er wechselt zyklisch zwischen:
    1) Helper/clean_short_tracks.clean_short_tracks()
    2) (NEU) Spike-Filter-Schritt (bpy.ops.clip.filter_tracks + frame_jump + delete_frame)
    3) Helper/find_low_marker_frame.run_find_low_marker_frame()

… bis find_low_marker_frame einen Frame liefert, der < (marker_baseline * 2) ist.

Parameter:
- marker_baseline: int|None – Basisframe für die Prüfung. Fällt zurück auf
  scene.marker_frame oder scene.frame_current.
- track_threshold: float – Threshold für bpy.ops.clip.filter_tracks.
- delete_frame_num: int – Frame, an dem Marker via Track.markers.delete_frame() gelöscht werden.
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


def _get_active_clip(context) -> Optional[bpy.types.MovieClip]:
    space = getattr(context, "space_data", None)
    if getattr(space, "type", None) == 'CLIP_EDITOR' and getattr(space, "clip", None):
        return space.clip
    try:
        return bpy.data.movieclips[0] if bpy.data.movieclips else None
    except Exception:
        return None


def _delete_marker_at_frame_for_all_tracks(context, frame: int) -> int:
    """Löscht Marker an 'frame' für alle Tracks des aktiven Clips.
    Rückgabe: Anzahl der betroffenen Tracks (best effort).
    """
    clip = _get_active_clip(context)
    if not clip:
        return 0
    count = 0
    try:
        tracks = clip.tracking.tracks
    except Exception:
        return 0

    for tr in tracks:
        try:
            # MovieTrackingMarkers.delete_frame(int frame)
            tr.markers.delete_frame(int(frame))
            count += 1
        except Exception:
            # Marker evtl. nicht vorhanden → ignorieren
            pass
    return count


def run_spike_filter_cycle(
    context: bpy.types.Context,
    *,
    marker_baseline: Optional[int] = None,
    track_threshold: float = 5.0,
    delete_frame_num: int = 100,
    max_loops: int = 10,
) -> Dict[str, Any]:
    """Wechselt zwischen clean_short_tracks → Spike-Filter → find_low_marker_frame,
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
            # Aktion ist in dieser Pipeline extern definiert; falls clean_short_tracks
            # eine 'action' erfordert, bitte innerhalb der Helper-Implementierung behandeln.
            clean_short_tracks(
                context,
                min_len=frames_min,
                verbose=True,
            )
            print(f"[SpikeCycle] clean_short_tracks done (min_len={frames_min})")
        except TypeError:
            # Fallback, falls ältere Signaturen existieren
            try:
                clean_short_tracks(context)
                print("[SpikeCycle] clean_short_tracks done (fallback signature)")
            except Exception as ex_clean:
                print(f"[SpikeCycle] clean_short_tracks failed: {ex_clean!r}")
        except Exception as ex_clean:
            print(f"[SpikeCycle] clean_short_tracks failed: {ex_clean!r}")

        # Schritt 3: NEU – Spike-Filter + Jump + Marker-Delete an bestimmtem Frame
        try:
            # a) Problematische Tracks anhand Bewegungs-Spikes filtern/selektieren
            bpy.ops.clip.filter_tracks(track_threshold=float(track_threshold))
            print(f"[SpikeCycle] filter_tracks(track_threshold={track_threshold})")

            # b) Zum Pfadstart springen
            bpy.ops.clip.frame_jump(position='PATHSTART')
            print("[SpikeCycle] frame_jump(PATHSTART)")

            # c) Marker an delete_frame_num löschen (für alle Tracks)
            deleted_on_tracks = _delete_marker_at_frame_for_all_tracks(context, int(delete_frame_num))
            print(f"[SpikeCycle] delete_frame(frame={int(delete_frame_num)}) on {deleted_on_tracks} track(s)")

            # d) „Wert -1 setzen“ → hier als internes Flag genutzt: einmalige Ausführung
            delete_frame_num = -1
        except Exception as ex_ops:
            print(f"[SpikeCycle] spike-filter step failed: {ex_ops!r}")

        # Schleife fortsetzen
        print(f"[SpikeCycle] loop {loops}/{max_loops} completed → retry")

    # Abbruch nach max_loops
    print(f"[SpikeCycle] max_loops ({max_loops}) reached without suitable frame")
    return {"status": "NONE", "reason": "max_loops_exceeded", "loops": loops}
