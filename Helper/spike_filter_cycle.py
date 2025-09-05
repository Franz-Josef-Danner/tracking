# Helper/spike_filter_cycle.py
# SPDX-License-Identifier: MIT
from __future__ import annotations

from typing import Optional, Dict, Any, List, Tuple
import bpy
import math

# Zwingend: segmentweises Cleanup (vom Nutzer gefordert)
try:
    from .clean_short_segments import clean_short_segments  # type: ignore
except Exception as _ex:
    clean_short_segments = None
    _CSS_IMPORT_ERR = _ex
else:
    _CSS_IMPORT_ERR = None

__all__ = ["run_marker_spike_filter_cycle"]


# ---------------------------------------------------------------------------
# Interna / Utilities
# ---------------------------------------------------------------------------

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

def _to_pixel(vec01, size_xy) -> Tuple[float, float]:
    """Koordinate [0..1] → Pixel."""
    return float(vec01[0]) * float(size_xy[0]), float(vec01[1]) * float(size_xy[1])


def _collect_frame_velocities(
    clip: bpy.types.MovieClip,
) -> Dict[int, List[Tuple[bpy.types.MovieTrackingTrack,
                          bpy.types.MovieTrackingMarker,
                          bpy.types.MovieTrackingMarker,
                          Tuple[float, float]]]]:
    """
    Pro Ziel-Frame f1: Liste (track, prev_marker, curr_marker, v=(dx/dt, dy/dt)).
    - Gemutete Marker werden ignoriert.
    - Lücken (dt>1) sind erlaubt; Geschwindigkeit wird auf dt normiert.
    """
    result: Dict[int, List[Tuple[bpy.types.MovieTrackingTrack,
                                 bpy.types.MovieTrackingMarker,
                                 bpy.types.MovieTrackingMarker,
                                 Tuple[float, float]]]] = {}
    size = getattr(clip, "size", (1.0, 1.0))
    tracks = _get_tracks_collection(clip) or []

    for tr in tracks:
        markers: List[bpy.types.MovieTrackingMarker] = list(tr.markers)
        if len(markers) < 2:
            continue

        prev = markers[0]
        for i in range(1, len(markers)):
            curr = markers[i]

            # gemutete Marker nicht verwerten
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


def _apply_marker_outlier_filter(
    context: bpy.types.Context,
    *,
    threshold_px: float,
    action: str = "DELETE",
) -> int:
    """
    Marker-Filter pro Frame:
      - v_avg = Durchschnitt der Geschwindigkeiten
      - Kandidaten: Distanz zu v_avg > threshold_px
    action: "DELETE" (Default) | "MUTE" | "SELECT"
    Rückgabe: Anzahl betroffener Marker.
    """
    clip = _get_active_clip(context)
    if not clip:
        return 0

    frame_map = _collect_frame_velocities(clip)
    affected = 0

    act = action.upper().strip()
    do_delete = act == "DELETE"
    do_mute   = act == "MUTE"
    do_select = act == "SELECT"

    # Pro Frame erst Kandidaten sammeln, dann **in Reverse** löschen → stabile Indizes.
    for frame, entries in frame_map.items():
        if not entries:
            continue

        # v_avg
        sum_vx = 0.0
        sum_vy = 0.0
        for _, _, _, v in entries:
            sum_vx += v[0]
            sum_vy += v[1]
        inv_n = 1.0 / float(len(entries))
        v_avg = (sum_vx * inv_n, sum_vy * inv_n)

        # Kandidaten bestimmen
        to_handle: List[Tuple[bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingMarker, float]] = []
        for tr, m_prev, m_curr, v in entries:
            dvx = v[0] - v_avg[0]
            dvy = v[1] - v_avg[1]
            dev = math.hypot(dvx, dvy)
            if dev > threshold_px:
                to_handle.append((tr, m_curr, dev))

        if not to_handle:
            continue

        if do_delete:
            for tr, m_curr, dev in reversed(to_handle):
                try:
                    # Sicherer Pfad: über Frame löschen (robuster als remove(marker))
                    f = int(getattr(m_curr, "frame", -10))
                    tr.markers.delete_frame(f)
                    affected += 1
                except Exception as ex:
                    pass
        elif do_mute:
            for tr, m_curr, dev in to_handle:
                try:
                    m_curr.mute = True
                    affected += 1
                except Exception as ex:
                    pass
        elif do_select:
            for tr, m_curr, dev in to_handle:
                try:
                    m_curr.select = True
                    try:
                        tr.select = True
                    except Exception:
                        pass
                    affected += 1
                except Exception as ex:
                    pass

    return affected


# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------

def run_marker_spike_filter_cycle(
    context: bpy.types.Context,
    *,
    track_threshold: float = 2.0,   # Pixel/Frame
    action: str = "DELETE",         # "DELETE" | "MUTE" | "SELECT"
    # Clean-Policy
    min_segment_len: Optional[int] = None,  # Default aus Scene
    treat_muted_as_gap: bool = True,
    run_segment_cleanup: bool = True,
    **kwargs,
) -> Dict[str, Any]:
    """
    Führt einen Marker-basierten Spike-Filter-Durchlauf aus (Pixel/Frame).

    Dieses Verfahren wurde erweitert, um iterativ zu arbeiten. Nach jedem
    Ausreißer‑Löschvorgang wird geprüft, ob es Frames gibt, die noch deutlich
    über dem zulässigen Marker‑Limit liegen. Das Limit berechnet sich aus
    der Szenenvariable ``marker_frame`` multipliziert mit ``1.5``. Solange
    mindestens ein Frame mehr aktive Marker hat als ``marker_frame * 1.5``,
    wird der Marker‑Filter erneut ausgeführt. Dies verhindert, dass das
    Spike‑Filter bei einem zu niedrigen Schwellwert stoppt und sorgt dafür,
    dass weitere Ausreißer entfernt werden können.

    Parameter:
        context: Der Blender-Kontext mit aktivem Clip.
        track_threshold: Geschwindigkeitsschwelle in Pixel pro Frame.
        action: Wie Marker behandelt werden ("DELETE", "MUTE" oder "SELECT").
        min_segment_len: Minimale Segmentlänge für das anschließende Cleanup.
        treat_muted_as_gap: Ob gemutete Marker als Lücke behandelt werden.
        run_segment_cleanup: Optionales segmentweises Cleanup ausführen.
        **kwargs: Zusätzliche Parameter; ``error_threshold_px`` wird als Alias
            für ``track_threshold`` unterstützt.

    Rückgabe:
        Dictionary mit Status, Anzahl betroffener Marker und Cleanup‑Informationen.
    """
    # Sicherstellen, dass ein aktiver Clip vorhanden ist
    if not _get_active_clip(context):
        return {"status": "FAILED", "reason": "no active MovieClip"}

    # Alias-Unterstützung (Backward-Compat): error_threshold_px → track_threshold
    if "error_threshold_px" in kwargs and (kwargs.get("error_threshold_px") is not None):
        try:
            track_threshold = float(kwargs["error_threshold_px"])
        except Exception:
            pass

    # **Untergrenze erzwingen**: auch wenn der Aufrufer < 2.0 übergibt
    thr = max(2.0, float(track_threshold))
    act = str(action or "DELETE").upper().strip()
    key = "deleted" if act == "DELETE" else ("muted" if act == "MUTE" else "selected")

    # Gesamtsumme der betroffenen Marker über alle Durchläufe
    total_affected = 0

    # Iterativer Filter: wiederhole, solange es Frames mit zu vielen aktiven Markern gibt
    iteration = 0
    while True:
        iteration += 1
        # 1) Marker-Filter auf Basis der Geschwindigkeit anwenden
        affected = _apply_marker_outlier_filter(context, threshold_px=thr, action=act)
        try:
            total_affected += int(affected)
        except Exception:
            # Fallback, falls affected keine Zahl ist
            try:
                total_affected += int(getattr(affected, "__int__", lambda: 0)())
            except Exception:
                pass

        # Wenn keine Marker entfernt wurden, gibt es keinen Grund weiterzumachen
        if not affected or int(affected) <= 0:
            break

        # 2) Prüfen, ob es noch Frames mit übermäßig vielen aktiven Markern gibt
        clip = _get_active_clip(context)
        scene = getattr(context, "scene", None)
        # Basiswert für das erlaubte Marker‑Limit: Szene.marker_frame
        marker_frame_value: float = 0.0
        if scene is not None:
            # Versuche sowohl Attribut- als auch Dictionary‑Zugriff
            try:
                # Zunächst Attributzugriff
                val = getattr(scene, "marker_frame", None)
                if val is not None:
                    marker_frame_value = float(val)
            except Exception:
                pass
            # Wenn kein Attribut verfügbar, versuche Dictionary‑Eintrag
            if marker_frame_value <= 0.0:
                try:
                    val = scene.get("marker_frame", None)  # type: ignore[call-arg]
                    if val is not None:
                        marker_frame_value = float(val)
                except Exception:
                    pass

        # Wenn kein valider Marker‑Frame gesetzt ist, abbrechen
        if marker_frame_value <= 0.0 or clip is None:
            # Es gibt keine zuverlässige Grenze → Schleife beenden
            break

        # Zähle aktive Marker pro Frame
        frame_counts: Dict[int, int] = {}
        try:
            tracks = _get_tracks_collection(clip) or []
            for tr in tracks:
                try:
                    markers = getattr(tr, "markers", [])
                except Exception:
                    markers = []
                for m in markers:
                    try:
                        # ignoriere gemutete Marker
                        if getattr(m, "mute", False):
                            continue
                        f = int(getattr(m, "frame", -10))
                        frame_counts[f] = frame_counts.get(f, 0) + 1
                    except Exception:
                        pass
        except Exception:
            frame_counts = {}

        # Erlaubte Höchstgrenze
        threshold_limit = marker_frame_value * 1.5

        # Prüfen, ob mindestens ein Frame die Höchstgrenze überschreitet
        too_many = False
        for cnt in frame_counts.values():
            try:
                if float(cnt) > threshold_limit:
                    too_many = True
                    break
            except Exception:
                # Bei Fehlern lieber abbrechen
                break

        # Wenn keine Frames die Grenze überschreiten → Schleife beenden
        if not too_many:
            break

        # Ansonsten wird die Schleife fortgesetzt und der Marker‑Filter erneut angewendet
        # Dadurch können weitere Ausreißer entfernt werden

    # 3) Segment-Cleanup (optional via Flag) – wird einmal nach allen Durchläufen ausgeführt
    cleaned_segments = 0
    cleaned_markers = 0
    if run_segment_cleanup and clean_short_segments is not None:
        scene = getattr(context, "scene", None)
        # Falls min_segment_len nicht übergeben wurde, aus der Szene ableiten
        if min_segment_len is None:
            if scene is not None:
                try:
                    # Priorität: tco_min_seg_len → frames_track → 25
                    min_segment_len = int(scene.get("tco_min_seg_len", 0)) or int(getattr(scene, "frames_track", 0)) or 25
                except Exception:
                    min_segment_len = 25
            else:
                min_segment_len = 25
        try:
            res = clean_short_segments(
                context,
                min_len=int(min_segment_len),
                treat_muted_as_gap=bool(treat_muted_as_gap),
                verbose=True,
            )
            if isinstance(res, dict):
                cleaned_segments = int(res.get("segments_removed", 0) or 0)
                cleaned_markers  = int(res.get("markers_removed", 0) or 0)
        except Exception:
            pass

    return {
        "status": "OK",
        key: int(total_affected),
        "cleaned_segments": int(cleaned_segments),
        "cleaned_markers": int(cleaned_markers),
        "suggest_split_cleanup": True,  # Hinweis an den Coordinator
    }

