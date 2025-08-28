from __future__ import annotations
"""
Marker-basiertes Spike-Filtering in Pixeln (analog zu filter_tracks, aber granular)
-----------------------------------------------------------------------

- Bewertet Marker per Frame im Geschwindigkeitsraum (Pixel/Frame).
- Pro Frame: v_avg = Durchschnitt über alle Track-Geschwindigkeiten.
- Abweichung = |v_track - v_avg|; wenn > threshold_px → Marker wird behandelt.
- Standard-Aktion: Marker muten (statt Track löschen).
- Gibt Anzahl betroffener Marker und next_threshold zurück.

Rückgabe (dict):
* status: "OK" | "FAILED"
* muted / deleted / selected: Anzahl betroffener Marker (abhängig von action)
* next_threshold: empfohlener Schwellenwert für nächsten Pass
"""

from typing import Optional, Dict, Any, List, Tuple, Callable, Optional
import bpy
import math

_clean_short_tracks: Optional[Callable] = None
_IMPORT_ERR: Optional[Exception] = None

try:
    # wenn dieses Modul innerhalb des Pakets "Helper" liegt:
    from .clean_short_segments import clean_short_segments  # neu
except Exception:
    clean_short_segments = None  # wird später geprüft

__all__ = [
    "run_marker_spike_filter_cycle",
]

# ---------------------------------------------------------------------------
# Interna
# ---------------------------------------------------------------------------

def _resolve_clean_short_tracks():
    """Versucht lazy, clean_short_tracks zu importieren und cached das Ergebnis."""
    global _clean_short_tracks, _IMPORT_ERR
    if _clean_short_tracks is not None:
        return _clean_short_tracks
    try:
        # relativer Import, wenn dieses Modul als Teil des Add-ons läuft
        from .clean_short_tracks import clean_short_tracks as _cst  # type: ignore
        _clean_short_tracks = _cst
        return _clean_short_tracks
    except Exception as ex1:
        # optionaler Fallback, falls Modulpfade anders sind
        try:
            from Helper.clean_short_tracks import clean_short_tracks as _cst  # type: ignore
            _clean_short_tracks = _cst
            return _clean_short_tracks
        except Exception as ex2:
            _IMPORT_ERR = ex2 or ex1
            return None

def _get_active_clip(context) -> Optional[bpy.types.MovieClip]:
    space = getattr(context, "space_data", None)
    if getattr(space, "type", None) == "CLIP_EDITOR" and getattr(space, "clip", None):
        return space.clip
    try:
        return bpy.data.movieclips[0] if bpy.data.movieclips else None
    except Exception:
        return None


def _get_tracks_collection(clip) -> Optional[bpy.types.bpy_prop_collection]:
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


def _lower_threshold(thr: float) -> float:
    next_thr = float(thr) * 0.95
    if abs(next_thr - float(thr)) < 1e-6 and thr > 0.0:
        next_thr = float(thr) - 1.0
    return max(0.0, next_thr)


def _to_pixel(vec01, size_xy) -> Tuple[float, float]:
    """Koordinate von [0..1] in Pixel umrechnen."""
    return float(vec01[0]) * float(size_xy[0]), float(vec01[1]) * float(size_xy[1])


def _collect_frame_velocities(clip: bpy.types.MovieClip) -> Dict[int, List[Tuple[bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingMarker, bpy.types.MovieTrackingMarker, Tuple[float, float]]]]:
    """
    Liefert für jeden Frame eine Liste von (track, m_prev, m_curr, v_px)
    wobei v_px = (dx, dy) in Pixel/Frame ist.
    Erlaubt Lücken: nutzt jeweils den vorherigen Marker im selben Track,
    normiert die Delta-Pixel auf die Frame-Distanz dt.
    """
    result: Dict[int, List[Tuple[bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingMarker, bpy.types.MovieTrackingMarker, Tuple[float, float]]]] = {}
    size = getattr(clip, "size", (1.0, 1.0))

    tracks = _get_tracks_collection(clip) or []
    for tr in tracks:
        # Marker nach Frame sortiert (API ist i. d. R. schon sortiert)
        markers: List[bpy.types.MovieTrackingMarker] = list(tr.markers)
        if len(markers) < 2:
            continue

        # Gehe über aufeinanderfolgende Markerpaare (mit beliebigem dt >= 1)
        prev = markers[0]
        for i in range(1, len(markers)):
            curr = markers[i]
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

            bucket = result.setdefault(f1, [])
            bucket.append((tr, prev, curr, (vx, vy)))
            prev = curr

    return result


def _apply_marker_outlier_filter(context: bpy.types.Context, *, threshold_px: float, action: str = "MUTE") -> int:
    """
    Analoge Logik zu filter_tracks, aber auf Marker-Ebene:
    Für jeden Frame f:
      - bilde v_avg (Durchschnitt der Track-Geschwindigkeiten in Pixel/Frame)
      - markiere Marker, deren |v - v_avg| > threshold_px
      - Aktion: "MUTE" (default), "DELETE", "SELECT"
    Gibt die Anzahl der betroffenen Marker zurück.
    """
    clip = _get_active_clip(context)
    if not clip:
        return 0

    frame_map = _collect_frame_velocities(clip)
    affected = 0

    # Schnelles Lookup für Aktion
    do_mute = action.upper() == "MUTE"
    do_delete = action.upper() == "DELETE"
    do_select = action.upper() == "SELECT"

    for frame, entries in frame_map.items():
        if not entries:
            continue

        # Durchschnitts-Geschwindigkeit v_avg
        sum_vx = 0.0
        sum_vy = 0.0
        for _, _, _, v in entries:
            sum_vx += v[0]
            sum_vy += v[1]
        inv_n = 1.0 / float(len(entries))
        v_avg = (sum_vx * inv_n, sum_vy * inv_n)

        # Ausreißer pro Track/Marker bestimmen
        for tr, m_prev, m_curr, v in entries:
            dvx = v[0] - v_avg[0]
            dvy = v[1] - v_avg[1]
            dev = math.hypot(dvx, dvy)  # Abstand im Geschwindigkeitsraum [px/frame]

            if dev > threshold_px:
                try:
                    if do_mute:
                        m_curr.mute = True
                        affected += 1
                        print(f"[MarkerSpike] MUTE '{tr.name}' @ f{frame} |dev|={dev:.3f} > thr={threshold_px:.3f}")
                    elif do_delete:
                        tr.markers.remove(m_curr)
                        affected += 1
                        print(f"[MarkerSpike] DELETE '{tr.name}' @ f{frame} |dev|={dev:.3f} > thr={threshold_px:.3f}")
                    elif do_select:
                        # Marker-Select setzen; Track-Select optional
                        m_curr.select = True
                        try:
                            tr.select = True
                        except Exception:
                            pass
                        affected += 1
                        print(f"[MarkerSpike] SELECT '{tr.name}' @ f{frame} |dev|={dev:.3f} > thr={threshold_px:.3f}")
                except Exception as ex:
                    print(f"[MarkerSpike] action failed: {ex!r}")

    return affected

def _run_clean_short_tracks(context: bpy.types.Context, *, min_len: int, verbose: bool = True) -> int:
    """
    Ruft Helper/clean_short_tracks.py auf (falls vorhanden).
    Gibt die Anzahl bereinigter/entfernter Short-Tracks zurück, falls ermittelbar,
    ansonsten 0. Der Helper selbst kann 'None' zurückgeben – wir handeln defensiv.
    """
    if clean_short_tracks is None:
        print("[MarkerSpike] clean_short_tracks not available (import failed)")
        return 0
    try:
        res = clean_short_tracks(context, min_len=int(min_len), verbose=bool(verbose))  # type: ignore[arg-type]
        # Der Helper kann alles Mögliche zurückgeben; wir normalisieren konservativ:
        if isinstance(res, dict):
            # häufige Keys absichern, falls dein Helper so etwas liefert
            for k in ("removed", "deleted", "cleaned", "count"):
                if k in res:
                    return int(res.get(k, 0) or 0)
        if isinstance(res, (int, float)):
            return int(res)
        return 0
    except Exception as ex:
        print(f"[MarkerSpike] clean_short_tracks failed: {ex!r}")
        return 0

# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------

def run_marker_spike_filter_cycle(
    context: bpy.types.Context,
    *,
    track_threshold: float = 3.0,   # Pixel/Frame
    action: str = "DELETE",           # "MUTE" | "DELETE" | "SELECT"
) -> Dict[str, Any]:
    """
    Führt einen Marker-basierten Spike-Filter-Durchlauf aus (Pixel/Frame)
    und ruft **immer** anschließend clean_short_tracks() auf.
    """
    if not _get_active_clip(context):
        return {"status": "FAILED", "reason": "no active MovieClip"}

    thr = float(track_threshold)
    act = str(action or "DELETE").upper()

    # 1) Marker-Filter
    affected = _apply_marker_outlier_filter(context, threshold_px=thr, action=act)
    print(f"[MarkerSpike] affected {affected} marker(s) with action={act}")

    # 2) Clean Short (immer) – lazy import + defensive handling
    cleaned = 0
    cst = _resolve_clean_short_tracks()
    if cst is None:
        reason = f"clean_short_tracks not available ({_IMPORT_ERR!r})"
        print(f"[MarkerSpike] WARN: {reason}")
    else:
        frames_min = int(getattr(context.scene, "frames_track", 25) or 25)
        try:
            res = cst(context, min_len=frames_min, verbose=True)  # type: ignore[call-arg]
            if isinstance(res, dict):
                cleaned = int(
                    res.get("removed", 0)
                    or res.get("deleted", 0)
                    or res.get("cleaned", 0)
                    or res.get("count", 0)
                    or 0
                )
            elif isinstance(res, (int, float)):
                cleaned = int(res)
            print(f"[MarkerSpike] clean_short_tracks(min_len={frames_min}) → cleaned={cleaned}")
        except Exception as ex:
            print(f"[MarkerSpike] clean_short_tracks failed: {ex!r}")
            
    # 3) Next Threshold
    next_thr = _lower_threshold(thr)
    print(f"[MarkerSpike] next threshold → {next_thr}")

    key = "muted" if act == "MUTE" else ("deleted" if act == "DELETE" else "selected")
    return {
        "status": "OK",
        key: int(affected),
        "cleaned": int(cleaned),
        "next_threshold": float(next_thr),
        "suggest_split_cleanup": True,  # <— NEU (optional)
    }

