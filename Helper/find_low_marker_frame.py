import bpy
from typing import Optional, Dict, Any, Tuple

__all__ = ("find_low_marker_frame_core", "run_find_low_marker_frame")

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _resolve_clip_and_scene(context, clip=None, scene=None) -> Tuple[Optional[bpy.types.MovieClip], Optional[bpy.types.Scene]]:
    scn = scene or getattr(context, "scene", None)

    if clip is not None:
        return clip, scn

    # 1) Aktiver CLIP_EDITOR
    space = getattr(context, "space_data", None)
    if space and getattr(space, "type", None) == 'CLIP_EDITOR':
        c = getattr(space, "clip", None)
        if c:
            return c, scn

    # 2) Fallback: erster existierender MovieClip
    try:
        for c in bpy.data.movieclips:
            return c, scn
    except Exception:
        pass

    return None, scn


def _clip_frame_end(clip: bpy.types.MovieClip, scn: Optional[bpy.types.Scene]) -> int:
    # Harte Clip-Grenze: start + duration - 1
    try:
        c_end = int(clip.frame_start) + int(getattr(clip, "frame_duration", 0)) - 1
        if c_end < int(clip.frame_start):
            c_end = int(clip.frame_start)
    except Exception:
        c_end = int(clip.frame_start)
    # Szene darf enger sein, aber nie weiter als der Clip
    if scn:
        return min(int(scn.frame_end), c_end)
    return c_end

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def find_low_marker_frame_core(
    clip: bpy.types.MovieClip,
    *,
    marker_min: int,
    frame_start: Optional[int] = None,
    frame_end: Optional[int] = None,
    exact: bool = True,
    ignore_muted_marker: bool = True,
    ignore_muted_track: bool = True,
) -> Optional[int]:
    """
    Liefert den ersten Frame im Bereich [frame_start, frame_end],
    dessen aktive Markeranzahl < marker_min ist; sonst None.
    'Aktiv' bedeutet: Marker existiert auf exakt diesem Frame und ist nicht stumm.
    """
    tracking = clip.tracking
    tracks = tracking.tracks

    fs = int(frame_start) if frame_start is not None else int(clip.frame_start)
    fe_clip = _clip_frame_end(clip, bpy.context.scene if hasattr(bpy.context, "scene") else None)
    fe = int(frame_end) if frame_end is not None else fe_clip
    fe = min(fe, fe_clip)  # Clamp an Clipende

    print(f"[MarkerCheck] Erwartete Mindestmarker pro Frame: {int(marker_min)}")

    # Scan
    for frame in range(fs, fe + 1):
        count = 0
        for tr in tracks:
            try:
                if ignore_muted_track and getattr(tr, "mute", False):
                    continue
                # Blender API: find_frame(frame, exact=True) ist verfügbar; Fallback ohne exact
                try:
                    m = tr.markers.find_frame(frame, exact=exact)  # type: ignore
                except TypeError:
                    m = tr.markers.find_frame(frame)
                if not m:
                    continue
                if ignore_muted_marker and getattr(m, "mute", False):
                    continue
                count += 1
            except Exception:
                # Einzelner Track defekt → ignorieren, robust weiterzählen
                pass

        print(f"[MarkerCheck] Frame {frame}: {count} aktive Marker")
        if count < int(marker_min):
            print(f"[MarkerCheck] → Zu wenige Marker in Frame {frame}")
            return frame

    print("[MarkerCheck] Kein Frame mit zu wenigen Markern gefunden.")
    return None

# ---------------------------------------------------------------------------
# Wrapper für den Orchestrator
# ---------------------------------------------------------------------------

def run_find_low_marker_frame(
    context,
    *,
    prefer_adapt: bool = True,
    use_scene_basis: bool = True,
    frame_start: Optional[int] = None,
    frame_end: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Orchestrator-kompatibel:
      - Liefert {"status": "FOUND", "frame": F} | {"status": "NONE"} | {"status":"FAILED","reason":...}
      - Schwellwertauflösung: marker_min > marker_adapt > marker_basis > 20
      - Beachtet Clipgrenzen
    """
    try:
        clip, scn = _resolve_clip_and_scene(context)
        if not clip:
            return {"status": "FAILED", "reason": "Kein MovieClip im Kontext."}

        # Threshold-Auflösung (Priorität: marker_min > marker_adapt > marker_basis > 20)
        marker_min = None
        if prefer_adapt and scn and ("marker_min" in scn):
            marker_min = int(scn["marker_min"])
        elif prefer_adapt and scn and ("marker_adapt" in scn):
            marker_min = int(scn["marker_adapt"])
        elif use_scene_basis and scn:
            marker_min = int(scn.get("marker_basis", 20))
        else:
            marker_min = 20

        # Frames clampen
        fs = int(frame_start) if frame_start is not None else int(clip.frame_start)
        fe = int(frame_end) if frame_end is not None else _clip_frame_end(clip, scn)

        frame = find_low_marker_frame_core(
            clip,
            marker_min=int(marker_min),
            frame_start=fs,
            frame_end=fe,
            exact=True,
            ignore_muted_marker=True,
            ignore_muted_track=True,
        )

        if frame is None:
            return {"status": "NONE"}
        return {"status": "FOUND", "frame": int(frame)}

    except Exception as ex:
        return {"status": "FAILED", "reason": str(ex)}
