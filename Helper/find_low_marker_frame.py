# Helper/find_low_marker_frame.py
import bpy
from typing import Optional, Dict, Any, Tuple

__all__ = ("find_low_marker_frame_core", "run_find_low_marker_frame")

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _resolve_clip_and_scene(
    context,
    clip: Optional[bpy.types.MovieClip] = None,
    scene: Optional[bpy.types.Scene] = None,
) -> Tuple[Optional[bpy.types.MovieClip], Optional[bpy.types.Scene]]:
    """Finde aktiven MovieClip und Scene, bevorzugt aktiven CLIP_EDITOR."""
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
    """Ermittle harte Clip-Grenze: start + duration - 1 (durch Szene ggf. enger)."""
    try:
        c_end = int(clip.frame_start) + int(getattr(clip, "frame_duration", 0)) - 1
        if c_end < int(clip.frame_start):
            c_end = int(clip.frame_start)
    except Exception:
        c_end = int(getattr(clip, "frame_start", 1))
    if scn:
        return min(int(scn.frame_end), c_end)
    return c_end


def _scene_scan_range(
    clip: bpy.types.MovieClip,
    scn: Optional[bpy.types.Scene],
    frame_start: Optional[int],
    frame_end: Optional[int],
) -> Tuple[int, int]:
    """
    Liefert (fs, fe) für den SCAN-Bereich:
      - bevorzugt Szene (scene.frame_start .. scene.frame_end)
      - respektiert optionale Parameter frame_start / frame_end
      - clamp auf Clip-Ende, damit find_frame nicht in leeren Bereich läuft
    """
    # bevorzugt Szene
    if scn:
        fs = int(frame_start) if frame_start is not None else int(getattr(scn, "frame_start", 1))
        fe_scene = int(frame_end) if frame_end is not None else int(getattr(scn, "frame_end", fs))
    else:
        # Fallback ohne Szene
        fs = int(frame_start) if frame_start is not None else int(getattr(clip, "frame_start", 1))
        fe_scene = int(frame_end) if frame_end is not None else _clip_frame_end(clip, scn)

    # auf Clip-Grenzen clampen (Ende sicher, Start min. Clip-Start)
    try:
        c_start = int(getattr(clip, "frame_start", fs))
        c_end = _clip_frame_end(clip, scn)
        fs_clamped = max(fs, c_start)
        fe_clamped = min(fe_scene, c_end)
        if fe_clamped < fs_clamped:
            fe_clamped = fs_clamped
        return fs_clamped, fe_clamped
    except Exception:
        return fs, fe_scene


def _count_markers_on_frame(
    clip: bpy.types.MovieClip,
    frame: int,
    *,
    exact: bool = True,
    ignore_muted_marker: bool = True,
    ignore_muted_track: bool = True,
) -> int:
    """
    Zählt, wie viele Tracks im gegebenen Frame einen Marker besitzen,
    optional stummgeschaltete Marker/Tracks ignorierend.
    """
    tracking = clip.tracking
    cnt = 0
    for tr in getattr(tracking, "tracks", []):
        try:
            if ignore_muted_track and getattr(tr, "mute", False):
                continue
            try:
                m = tr.markers.find_frame(frame, exact=exact)
            except TypeError:
                # ältere Blender: kein exact-Argument
                m = tr.markers.find_frame(frame)
            if not m:
                continue
            if ignore_muted_marker and getattr(m, "mute", False):
                continue
            cnt += 1
        except Exception:
            # robust gegen vereinzelte Dateninkonsistenzen
            continue
    return cnt


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def find_low_marker_frame_core(
    clip: bpy.types.MovieClip,
    *,
    marker_basis: int,
    frame_start: int,
    frame_end: int,
    exact: bool = True,
    ignore_muted_marker: bool = True,
    ignore_muted_track: bool = True,
) -> Optional[int]:
    """
    Scannt von frame_start bis frame_end und gibt den Frame mit den
    WENIGSTEN Markern zurück, ABER nur wenn seine Markerzahl < marker_basis liegt.
    Keiner unter Threshold → None (Orchestrator startet dann den CYCLE).
    """
    marker_basis = max(1, int(marker_basis))
    fs = int(frame_start)
    fe = int(frame_end)
    if fe < fs:
        fe = fs

    lowest_frame: Optional[int] = None
    lowest_count: Optional[int] = None

    for f in range(fs, fe + 1):
        n = _count_markers_on_frame(
            clip,
            f,
            exact=exact,
            ignore_muted_marker=ignore_muted_marker,
            ignore_muted_track=ignore_muted_track,
        )

        # nur Frames berücksichtigen, die unterhalb des Basiswerts liegen
        if n < marker_basis:
            if lowest_count is None or n < lowest_count:
                lowest_count = n
                lowest_frame = f
                if n == 0:  # absoluter Early-Exit
                    break

    return lowest_frame  # None, wenn kein Frame < marker_basis


def _resolve_threshold_from_scene(
    scn: Optional[bpy.types.Scene],
    *,
    prefer_adapt: bool,
    use_scene_basis: bool,
    default_basis: int = 20,
) -> int:
    """
    Ermittelt den Schwellenwert (marker_basis) mit Priorität:
        prefer_adapt → scene["marker_basis"] oder scene["marker_adapt"]
        use_scene_basis → scene["marker_basis"]
        sonst default_basis
    """
    if scn is None:
        return int(default_basis)

    if prefer_adapt and ("marker_basis" in scn):
        return int(scn["marker_basis"])
    if prefer_adapt and ("marker_adapt" in scn):
        return int(scn["marker_adapt"])
    if use_scene_basis:
        return int(scn.get("marker_basis", default_basis))
    return int(default_basis)


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
      - **Scannt IMMER im Szenenbereich** (scene.frame_start .. scene.frame_end) – optional übersteuerbar per frame_start/frame_end
      - Threshold-Auflösung: marker_basis / marker_adapt (Scene) oder Default
    """
    try:
        clip, scn = _resolve_clip_and_scene(context)
        if not clip:
            return {"status": "FAILED", "reason": "Kein MovieClip im Kontext."}

        marker_basis = _resolve_threshold_from_scene(
            scn,
            prefer_adapt=prefer_adapt,
            use_scene_basis=use_scene_basis,
            default_basis=20,
        )
        marker_basis = max(1, int(marker_basis))

        # --- Szenenbereich bestimmen (mit Clamp auf Clip) ---
        fs, fe = _scene_scan_range(clip, scn, frame_start, frame_end)

        # --- Suchen: Minimum unterhalb Schwelle ---
        frame = find_low_marker_frame_core(
            clip,
            marker_basis=marker_basis,
            frame_start=fs,
            frame_end=fe,
            exact=True,
            ignore_muted_marker=True,
            ignore_muted_track=True,
        )

        if frame is None:
            return {"status": "NONE"}  # ← unverändert: triggert CYCLE_START im Orchestrator
        return {"status": "FOUND", "frame": int(frame)}

    except Exception as ex:
        return {"status": "FAILED", "reason": str(ex)}
