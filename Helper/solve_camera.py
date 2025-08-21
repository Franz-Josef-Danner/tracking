from __future__ import annotations
"""
Helper/projection_cleanup_builtin.py

Erweitertes, robustes Built‑in Projection Cleanup für den Solve‑Workflow.

✓ Sucht sicher den CLIP_EDITOR‑Kontext (Area/Region/Space)
✓ Stellt den MovieClipEditor auf TRACKING um (Operator‑Erwartung)
✓ Ermittelt den Threshold robust (scene[error_key] → resolve_error → error_track → solve_error → Fallback)
✓ Kapselt bpy.ops.clip.clean_tracks mit sauberem Logging und Seiteneffekt‑Kontrolle
✓ Liefert ein Report‑Dict: {threshold, affected, action, log}

Dieses Modul wird von Helper/solve_camera.py importiert:
    from .projection_cleanup_builtin import builtin_projection_cleanup, find_clip_window
"""

import bpy
from typing import Optional, Tuple, List

__all__ = ("builtin_projection_cleanup", "find_clip_window")


# ---------------------------------------------------------------------------
# Kontext‑Utilities
# ---------------------------------------------------------------------------

def find_clip_window(
    context,
) -> Tuple[Optional[bpy.types.Area], Optional[bpy.types.Region], Optional[bpy.types.Space]]:
    """Finde einen aktiven CLIP_EDITOR (Area/Region/Space) für temp_override.
    Gibt (None, None, None) zurück, wenn keiner verfügbar ist.
    """
    win = getattr(context, "window", None)
    screen = getattr(win, "screen", None) if win else None
    if not screen:
        return None, None, None
    for area in screen.areas:
        if area.type == "CLIP_EDITOR":
            for region in area.regions:
                if region.type == "WINDOW":
                    return area, region, area.spaces.active
    return None, None, None


def _active_clip_from_any_context(context) -> Optional[bpy.types.MovieClip]:
    """Robuste Clip‑Ermittlung: space_data → aktive CLIP‑Area → erster Clip.
    """
    sd = getattr(context, "space_data", None)
    clip = getattr(sd, "clip", None)
    if clip:
        return clip
    win = getattr(context, "window", None)
    screen = getattr(win, "screen", None) if win else None
    if screen:
        for area in screen.areas:
            if area.type == "CLIP_EDITOR":
                sp = area.spaces.active
                if getattr(sp, "clip", None):
                    return sp.clip
    return bpy.data.movieclips[0] if bpy.data.movieclips else None


# ---------------------------------------------------------------------------
# Kleine Helfer
# ---------------------------------------------------------------------------

def _count_tracks(clip: bpy.types.MovieClip) -> int:
    return len(clip.tracking.tracks) if clip else 0


def _selected_tracks(clip: bpy.types.MovieClip) -> List[bpy.types.MovieTrackingTrack]:
    if not clip:
        return []
    return [t for t in clip.tracking.tracks if getattr(t, "select", False)]


def _deselect_all(clip: bpy.types.MovieClip) -> None:
    if not clip:
        return
    for t in clip.tracking.tracks:
        if getattr(t, "select", False):
            t.select = False


# ---------------------------------------------------------------------------
# Kernfunktion
# ---------------------------------------------------------------------------

def builtin_projection_cleanup(
    context,
    *,
    error_key: str = "error_track",   # Threshold‑Quelle in scene
    factor: float = 1.0,               # Multiplikator auf den Basis‑Threshold
    frames: int = 0,                   # 0 = gesamte Sequenz (laut Operator‑Semantik)
    action: str = "DELETE_TRACK",      # 'SELECT' | 'DELETE_TRACK' | 'DELETE_SEGMENTS'
    dry_run: bool = False,             # true → erzwingt SELECT als Aktion
) -> dict:
    """Führt den Blender‑Builtin‑Cleanup über bpy.ops.clip.clean_tracks aus.

    Parameter
    ---------
    error_key : str
        Name des Scene‑Keys für den Basis‑Threshold (z. B. 'resolve_error').
    factor : float
        Schwelle = scene[error_key] * factor. (≤0 → Fallback.)
    frames : int
        Bereich in Frames relativ zum aktuellen Frame; 0 bedeutet gesamte Sequenz.
    action : str
        'SELECT' markiert nur; 'DELETE_TRACK' löscht Tracks; 'DELETE_SEGMENTS' löscht Segmente.
    dry_run : bool
        Wenn True, wird intern immer 'SELECT' verwendet und nichts gelöscht.

    Rückgabe
    --------
    dict(threshold: float, affected: int, action: str, log: list[str])
    """
    log: List[str] = []
    scene = context.scene

    # --- Clip & CLIP_EDITOR absichern ---
    clip = _active_clip_from_any_context(context)
    if clip is None:
        raise RuntimeError("[ProjectionCleanup] Kein aktiver Movie Clip verfügbar.")

    area, region, space = find_clip_window(context)
    if not area:
        raise RuntimeError("[ProjectionCleanup] Kein CLIP_EDITOR‑Fenster für Cleanup‑Override gefunden.")

    # Editor‑Modus auf TRACKING umstellen (Operator erwartet Tracking‑Kontext)
    try:
        if getattr(space, "mode", None) != 'TRACKING':
            space.mode = 'TRACKING'
            log.append("[ProjectionCleanup] INFO: MovieClipEditor mode → TRACKING")
    except Exception:
        pass

    # --- Threshold robust bestimmen ---
    base = float(scene.get(error_key, 0.0))
    if base <= 0.0:
        for alt in ("resolve_error", "error_track", "solve_error"):
            if alt == error_key:
                continue
            v = float(scene.get(alt, 0.0))
            if v > 0.0:
                base = v
                log.append(f"[ProjectionCleanup] INFO: fallback scene['{alt}']={v:.6f}")
                break
    threshold = float(base) * float(max(0.0, factor))
    if threshold <= 0.0:
        threshold = 2.0  # letzter Fallback
        log.append(
            f"[ProjectionCleanup] WARN: scene['{error_key}'] fehlte/≤0 → fallback threshold={threshold:.3f}"
        )

    # --- Aktion auflösen ---
    op_action = 'SELECT' if dry_run else action

    # --- Vorzustand erfassen ---
    tracks_before = _count_tracks(clip)

    # --- Operator ausführen ---
    try:
        with context.temp_override(area=area, region=region, space_data=space):
            # Selektion leeren, damit SELECT nur unsere Kandidaten markiert
            _deselect_all(clip)

            res = bpy.ops.clip.clean_tracks(
                frames=int(max(0, frames)),
                error=float(max(0.0, threshold)),
                action=op_action,
            )
            log.append(
                f"[ProjectionCleanup] bpy.ops.clip.clean_tracks(frames={int(max(0, frames))}, "
                f"error={float(max(0.0, threshold)):.6f}, action={op_action}) -> {res}"
            )

            # Ergebnis ermitteln (innerhalb des Overrides, damit Selektion lesbar ist)
            if op_action == 'DELETE_TRACK' and not dry_run:
                tracks_after = _count_tracks(clip)
                affected = max(0, tracks_before - tracks_after)
            elif op_action == 'DELETE_SEGMENTS' and not dry_run:
                # Approximation: einmal SELECT zum Zählen der betroffenen Tracks
                _deselect_all(clip)
                try:
                    sel_res = bpy.ops.clip.clean_tracks(
                        frames=int(max(0, frames)),
                        error=float(max(0.0, threshold)),
                        action='SELECT',
                    )
                    log.append(f"[ProjectionCleanup] recount SELECT -> {sel_res}")
                except Exception:
                    pass
                affected = len(_selected_tracks(clip))
            else:  # 'SELECT' oder dry_run
                affected = len(_selected_tracks(clip))

            # Aufräumen: Selektion zurücksetzen
            _deselect_all(clip)

    except Exception as ex:
        log.append(f"[ProjectionCleanup] ERROR: clean_tracks failed: {ex!r}")
        return {
            "threshold": float(threshold),
            "affected": 0,
            "action": op_action,
            "log": log,
        }

    log.append(
        f"[ProjectionCleanup] affected={affected}, threshold={float(threshold):.6f}, "
        f"mode={'DRY' if dry_run else op_action}"
    )

    return {
        "threshold": float(threshold),
        "affected": int(max(0, affected)),
        "action": (op_action if not dry_run else 'SELECT'),
        "log": log,
    }
