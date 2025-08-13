# Helper/projection_cleanup_builtin.py
import bpy

__all__ = ["builtin_projection_cleanup", "find_clip_window"]

def find_clip_window(context):
    """Finde einen aktiven CLIP_EDITOR (Area/Region/Space) für Overrides."""
    win = context.window
    if not win:
        return (None, None, None)
    screen = getattr(win, "screen", None)
    if not screen:
        return (None, None, None)
    for area in screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return (area, region, area.spaces.active)
    return (None, None, None)


def _count_tracks(clip):
    """Anzahl aller Tracks im Clip."""
    if not clip:
        return 0
    return len(clip.tracking.tracks)


def _selected_tracks(clip):
    if not clip:
        return []
    tracks = clip.tracking.tracks
    return [t for t in tracks if getattr(t, "select", False)]


def _deselect_all(clip):
    if not clip:
        return
    for t in clip.tracking.tracks:
        if t.select:
            t.select = False


def builtin_projection_cleanup(
    context,
    error_key: str = "error_track",  # z. B. 2.0 px
    factor: float = 1.0,
    frames: int = 0,
    action: str = "DELETE_TRACK",    # 'SELECT' | 'DELETE_TRACK' | 'DELETE_SEGMENTS'
    dry_run: bool = False,
):
    """
    Führt Cleanup mit Blender Built-in Operator aus:
      bpy.ops.clip.clean_tracks(frames=..., error=..., action=...)

    Rückgabe:
      dict( threshold=float, affected=int, action=str, log=[...])
    """
    log = []
    scene = context.scene
    sd = getattr(context, "space_data", None)
    clip = getattr(sd, "clip", None)

    if clip is None:
        # Versuche Clip via Context (falls im Override kein space_data hängt)
        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                clip = area.spaces.active.clip
                break

    if clip is None:
        raise RuntimeError("Kein aktiver Movie Clip verfügbar.")

    base = float(scene.get(error_key, 0.0))
    threshold = float(base) * float(max(0.0, factor))
    if threshold <= 0.0:
        # Fallback auf konservativen Default
        threshold = 2.0
        log.append(f"[ProjectionCleanup] WARN: scene['{error_key}'] fehlte/0.0 – fallback threshold={threshold:.3f}")

    if dry_run:
        # Für Dry-Run wechseln wir auf 'SELECT', zählen, reinigen Selektion wieder
        op_action = 'SELECT'
    else:
        op_action = action

    area, region, space = find_clip_window(context)
    if not area:
        raise RuntimeError("Kein CLIP_EDITOR-Fenster für Cleanup-Override gefunden.")

    tracks_before = _count_tracks(clip)
    selected_before = len(_selected_tracks(clip))

    with context.temp_override(area=area, region=region, space_data=space):
        # Safety: Selektion leeren, damit SELECT nur unsere Kandidaten markiert
        _deselect_all(clip)

        # Built-in aufrufen
        res = bpy.ops.clip.clean_tracks(
            frames=int(max(0, frames)),
            error=float(max(0.0, threshold)),
            action=op_action
        )
        log.append(f"[ProjectionCleanup] bpy.ops.clip.clean_tracks(frames={frames}, error={threshold:.6f}, action={op_action}) -> {res}")

        if dry_run:
            # Anzahl „betroffener“ Tracks = Anzahl selektierter nach SELECT
            affected = len(_selected_tracks(clip))
            # Selektion zurücksetzen, damit Dry-Run keine Zustände hinterlässt
            _deselect_all(clip)
        else:
            if op_action == 'DELETE_TRACK':
                tracks_after = _count_tracks(clip)
                affected = max(0, tracks_before - tracks_after)
            elif op_action == 'DELETE_SEGMENTS':
                # Keine direkte Zahl vom Operator → approximieren via erneuter SELECT
                # (leicht teuer, aber erträglich)
                _deselect_all(clip)
                bpy.ops.clip.clean_tracks(frames=int(max(0, frames)),
                                          error=float(max(0.0, threshold)),
                                          action='SELECT')
                affected = len(_selected_tracks(clip))
                _deselect_all(clip)
            else:
                # Nur Selektion – betroffene Anzahl == aktuelle Selektion
                affected = len(_selected_tracks(clip))
                # Optional Selektion stehenlassen – hier zurücksetzen, um Nebenwirkungen zu minimieren
                _deselect_all(clip)

    log.append(f"[ProjectionCleanup] affected={affected}, threshold={threshold:.6f}, mode={'DRY' if dry_run else action}")
    return {"threshold": threshold, "affected": affected, "action": (op_action if not dry_run else 'SELECT'), "log": log}
