# Helper/projektion_spike_filter_cycle.py
# SPDX-License-Identifier: MIT
from __future__ import annotations
"""
Projection-guided Spike-Filter
------------------------------------------------------------
Zielbild:
- Erkennung (v̄/Abweichung) über **alle** Tracks/Marker.
- **Löschen** nur in den zuvor selektierten Tracks aus
  scene['tco_proj_spike_tracks'] (Whitelist).
- Optionales segmentweises Cleanup (standardmäßig AUS, um
  Nicht-Whitelist-Tracks nicht zu beeinflussen).
- Telemetrie: gefunden/gelöscht/ignoriert, Frames, Coverage.
"""

from typing import Optional, Dict, Any, List, Tuple, Iterable
import bpy
import math

__all__ = ["run_projection_spike_filter_cycle"]

_STORE_TRACKS_KEY  = "tco_proj_spike_tracks"
_STORE_DELETED_KEY = "tco_proj_spike_deleted_markers"
_VERBOSE_SCENE_KEY = "tco_verbose_projection_select"  # toggelt Logausgaben

# ------------------------------------------------------------
# Optionales Cleanup (nur nutzen, wenn gezielt benötigt)
# ------------------------------------------------------------
try:
    from .clean_short_segments import clean_short_segments  # type: ignore
except Exception:
    clean_short_segments = None  # wird unten defensiv behandelt


# ------------------------------------------------------------
# Utilities
# ------------------------------------------------------------
def _is_verbose(scene) -> bool:
    try:
        return bool(scene.get(_VERBOSE_SCENE_KEY, True))  # Default: an
    except Exception:
        return True

def _vprint(scene, msg: str) -> None:
    if _is_verbose(scene):
        pass

def _active_clip(context) -> Optional[bpy.types.MovieClip]:
    """Robuster Clip-Fallback (bevorzugt aktiven CLIP_EDITOR)."""
    space = getattr(context, "space_data", None)
    if getattr(space, "type", None) == "CLIP_EDITOR" and getattr(space, "clip", None):
        return space.clip
    try:
        return next(iter(bpy.data.movieclips), None)
    except Exception:
        return None

def _iter_tracks(clip: Optional[bpy.types.MovieClip]) -> Iterable[bpy.types.MovieTrackingTrack]:
    if not clip:
        return []
    try:
        for obj in clip.tracking.objects:
            for t in obj.tracks:
                yield t
    except Exception:
        return []

def _to_pixel(vec01, size_xy) -> Tuple[float, float]:
    return float(vec01[0]) * float(size_xy[0]), float(vec01[1]) * float(size_xy[1])

def _collect_frame_velocities_all(
    clip: bpy.types.MovieClip,
) -> Dict[int, List[Tuple[bpy.types.MovieTrackingTrack,
                          bpy.types.MovieTrackingMarker,
                          bpy.types.MovieTrackingMarker,
                          Tuple[float, float]]]]:
    """
    Globaler Geschwindigkeits-Sampler: Bucketiere alle Marker-Paare je Frame.
    Keine Whitelist-Beschränkung → saubere v̄-Basis über **alle** Tracks.
    """
    result: Dict[int, List[Tuple[bpy.types.MovieTrackingTrack,
                                 bpy.types.MovieTrackingMarker,
                                 bpy.types.MovieTrackingMarker,
                                 Tuple[float, float]]]] = {}
    size = getattr(clip, "size", (1.0, 1.0))

    for tr in _iter_tracks(clip):
        markers: List[bpy.types.MovieTrackingMarker] = list(tr.markers)
        if len(markers) < 2:
            continue

        prev = markers[0]
        for i in range(1, len(markers)):
            curr = markers[i]
            # gemutete Marker überspringen
            if getattr(curr, "mute", False) or getattr(prev, "mute", False):
                prev = curr
                continue

            f0 = int(getattr(prev, "frame", -10))
            f1 = int(getattr(curr, "frame", -10))
            dt = f1 - f0
            if dt <= 0:
                prev = curr
                continue

            x0, y0 = _to_pixel(prev.co, size)
            x1, y1 = _to_pixel(curr.co, size)
            vx = (x1 - x0) / float(dt)
            vy = (y1 - y0) / float(dt)

            result.setdefault(f1, []).append((tr, prev, curr, (vx, vy)))
            prev = curr

    return result


# ------------------------------------------------------------
# Öffentliche API
# ------------------------------------------------------------
def run_projection_spike_filter_cycle(
    context: bpy.types.Context,
    *,
    track_threshold: float = 2.0,     # Pixel/Frame (Abweichung vom v̄)
    run_segment_cleanup: bool = False,  # Default AUS → keine globalen Nebeneffekte
    min_segment_len: Optional[int] = None,
    treat_muted_as_gap: bool = True,
) -> Dict[str, Any]:
    """
    Führt einen projektion-geleiteten Spike-Filter aus.

    Erkennung:
      - Geschwindigkeiten (px/frame) für alle Marker-Paare (global).
      - Pro Frame: v̄ über alle Einträge; |v - v̄| > threshold ⇒ Spike.

    Aktion:
      - Marker-LÖSCHUNG nur, wenn der Track in der Whitelist steht:
        scene['tco_proj_spike_tracks'] (Liste von Tracknamen).

    Persistenz:
      - Gelöschte Marker als "TrackName@f<frame>" in
        scene['tco_proj_spike_deleted_markers'].

    Rückgabe:
      {
        status: "OK" | "FAILED" | "SKIPPED",
        deleted: int,
        spikes_found_total: int,
        spikes_deleted: int,
        spikes_ignored: int,
        frames_scanned: int,
        allowed_tracks: [str],
        deleted_markers_key: str,   # scene key
        next_threshold: float,      # leichte Absenkung (5 %)
      }
    """
    clip = _active_clip(context)
    if not clip:
        return {"status": "FAILED", "reason": "no_active_clip"}

    scene = getattr(context, "scene", None)

    # Whitelist laden (zuvor durch projection_cleanup_builtin persistiert)
    try:
        names = list(scene.get(_STORE_TRACKS_KEY, []) or [])
    except Exception:
        names = []
    allowed: set[str] = {str(n) for n in names if n}

    _vprint(scene, f"start: allowed_track_names={len(allowed)}")

    if not allowed:
        return {"status": "SKIPPED", "reason": "no_allowed_tracks"}

    # Globale Sammlung → faire v̄/Abweichungsbasis
    frame_map = _collect_frame_velocities_all(clip)
    thr = max(2.0, float(track_threshold))

    deleted = 0
    deleted_markers: List[str] = []
    frames_scanned = 0
    spikes_found_total = 0
    spikes_deleted = 0
    spikes_ignored = 0

    for frame, entries in frame_map.items():
        frames_scanned += 1
        if not entries:
            continue

        # v_avg
        inv_n = 1.0 / float(len(entries))
        sum_vx = sum(v[0] for _, _, _, v in entries)
        sum_vy = sum(v[1] for _, _, _, v in entries)
        v_avg = (sum_vx * inv_n, sum_vy * inv_n)

        for tr, _m_prev, m_curr, v in entries:
            dvx = v[0] - v_avg[0]
            dvy = v[1] - v_avg[1]
            dev = math.hypot(dvx, dvy)
            if dev > thr:
                spikes_found_total += 1
                if tr.name in allowed:
                    # Nur Whitelist-Tracks werden *bearbeitet* (DELETE)
                    try:
                        f = int(getattr(m_curr, "frame", -10))
                        tr.markers.delete_frame(f)
                        deleted += 1
                        spikes_deleted += 1
                        deleted_markers.append(f"{tr.name}@f{f}")
                        # optionales Log pro Löschung
                        # print(f"[ProjSpike] DELETE '{tr.name}' @ f{f} |dev|={dev:.3f} > thr={thr:.3f}")
                    except Exception as ex:
                        _vprint(scene, f"DELETE failed '{tr.name}'@f{getattr(m_curr,'frame','?')}: {ex!r}")
                else:
                    # Nicht-Whitelist-Track → nur erkennen, nicht löschen
                    spikes_ignored += 1

    # Persistiere gelöschte Marker
    try:
        scene[_STORE_DELETED_KEY] = deleted_markers
    except Exception:
        pass

    _vprint(scene, (
        f"done: frames_scanned={frames_scanned}, spikes_found_total={spikes_found_total}, "
        f"spikes_deleted={spikes_deleted}, spikes_ignored={spikes_ignored}, deleted={deleted}, "
        f"next_thr={thr*0.95:.2f}"
    ))

    # Optionales Segment-Cleanup – vorsichtig behandeln:
    # Standard AUS (run_segment_cleanup=False). Wenn EIN und die implementierte
    # Funktion unterstützt KEINE Whitelist, kann es Nicht-Whitelist-Tracks
    # beeinflussen. Daher hier nur ausführen, wenn der Caller das bewusst will.
    cleaned_segments = 0
    cleaned_markers = 0
    if run_segment_cleanup and clean_short_segments is not None:
        # Wenn clean_short_segments bereits einen Whitelist-Parameter unterstützt,
        # kannst du ihn hier (limit_to_names=allowed) ergänzen. Bis dahin: globaler Call
        # ist bewusst default AUS gelassen.
        if min_segment_len is None:
            try:
                # heuristische Defaults aus Szene
                min_segment_len = int(scene.get("tco_min_seg_len", 0)) or int(getattr(scene, "frames_track", 0)) or 25
            except Exception:
                min_segment_len = 25
        try:
            res = clean_short_segments(
                context,
                min_len=int(min_segment_len),
                treat_muted_as_gap=bool(treat_muted_as_gap),
                verbose=True,
                # TODO (wenn unterstützt): limit_to_names=allowed,
            )
            if isinstance(res, dict):
                cleaned_segments = int(res.get("segments_removed", 0) or 0)
                cleaned_markers  = int(res.get("markers_removed", 0) or 0)
        except Exception as ex:
            _vprint(scene, f"clean_short_segments failed: {ex!r}")

    return {
        "status": "OK",
        "deleted": int(deleted),
        "spikes_found_total": int(spikes_found_total),
        "spikes_deleted": int(spikes_deleted),
        "spikes_ignored": int(spikes_ignored),
        "frames_scanned": int(frames_scanned),
        "allowed_tracks": sorted(list(allowed)),
        "deleted_markers_key": _STORE_DELETED_KEY,
        "cleaned_segments": int(cleaned_segments),
        "cleaned_markers": int(cleaned_markers),
        "next_threshold": max(2.0, thr * 0.95),
    }
