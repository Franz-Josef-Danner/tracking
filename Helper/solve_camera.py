from __future__ import annotations

import math
from typing import Any, Dict, Optional

import bpy

__all__ = ("solve_camera_only",)


# -- sichere Imports für Fehler-/Reduce-Logik -------------------------------
try:
    # Primäre Quelle in Helper
    from .reduce_error_tracks import (  # type: ignore
        get_avg_reprojection_error,
        run_reduce_error_tracks,
    )
except Exception:
    # Fallback auf relatives Paket
    try:
        from ..Helper.reduce_error_tracks import (  # type: ignore
            get_avg_reprojection_error,
            run_reduce_error_tracks,
        )
    except Exception:
        get_avg_reprojection_error = None  # type: ignore
        run_reduce_error_tracks = None  # type: ignore


# ---------------------------------------------------------------------------
# Hilfsfunktion: Refine-Flag sicher setzen (Blender 4.4+; robust bei fehlendem
# Attribut)
def _apply_refine_focal_flag(context: bpy.types.Context, flag: bool) -> None:
    try:
        clip = getattr(context, "edit_movieclip", None)
        if not clip:
            space = getattr(context, "space_data", None)
            clip = getattr(space, "clip", None) if space else None
        if not clip and bpy.data.movieclips:
            clip = next(iter(bpy.data.movieclips), None)
        tr = getattr(clip, "tracking", None) if clip else None
        settings = getattr(tr, "settings", None) if tr else None
        if settings and hasattr(settings, "refine_intrinsics_focal_length"):
            settings.refine_intrinsics_focal_length = bool(flag)
            print(f"[Solve] refine_intrinsics_focal_length → {bool(flag)}")
        else:
            print("[Solve] WARN: refine_intrinsics_focal_length nicht verfügbar")
    except Exception as exc:  # noqa: BLE001 - robust gegen alle Fehler
        print(f"[Solve] WARN: refine-Flag konnte nicht gesetzt werden: {exc}")


# ---------------------------------------------------------------------------
# Bestehende Einmal-Solve-Funktion sichern (wird unten als _solve_camera_once
# aufgerufen)
# HINWEIS: Wir gehen davon aus, dass solve_camera_only bislang EINEN Solve
# ausführt. Wir preserven diese Logik und wrappen sie.
_ORIG_SOLVE_FN = None
try:
    # Merke Referenz auf die in dieser Datei definierte ursprüngliche Funktion,
    # bevor wir sie unten überschreiben. Beim ersten Import ist dies None;
    # weiter unten haken wir das nach der Definition um.
    pass
except Exception:  # noqa: BLE001
    pass


def solve_camera_only(
    context: bpy.types.Context,
    *,
    max_no_refine_attempts: int = 10,
    refine_attempts: int = 1,
    force_min_delete_if_nan: int = 1,
) -> Dict[str, Any]:
    """Orchestrierter Kamera-Solve.

    Ablauflogik:
        1) Bis zu ``max_no_refine_attempts`` Versuche **ohne** Focal-Refine.
        2) Danach bis zu ``refine_attempts`` Versuche **mit** Focal-Refine.
        3) Nach jedem Versuch: Durchschnittsfehler messen und
           ``run_reduce_error_tracks`` aufrufen.
        4) Abbruch, sobald der Durchschnittsfehler ``target`` unterschreitet.

    Rückgabe:
        ``{"status": "OK"|"FAILED", "reason"?: str, "avg": float|None,
        "phase": "NO_REFINE"|"REFINE", "attempt": int}``
    """

    # Lazy-Bind der ursprünglichen Einmal-Solve Implementierung
    global _ORIG_SOLVE_FN
    if _ORIG_SOLVE_FN is None:
        # Beim ersten Aufruf kopieren wir die vorher definierte Funktion
        try:
            _ORIG_SOLVE_FN = _solve_camera_once  # type: ignore[name-defined]
        except Exception:  # noqa: BLE001 - Fallback sichern
            def _fallback_once(ctx: bpy.types.Context) -> Dict[str, Any]:
                try:
                    bpy.ops.clip.solve_camera()
                    return {"status": "OK"}
                except Exception as _exc:  # noqa: BLE001
                    return {"status": "FAILED", "reason": str(_exc)}

            _ORIG_SOLVE_FN = _fallback_once

    # Ziel-Error aus Scene, Default 2.0
    scn = context.scene
    try:
        target_err = float(scn.get("error_track", 2.0))
        if not (target_err == target_err) or target_err <= 0.0:
            target_err = 2.0
    except Exception:  # noqa: BLE001
        target_err = 2.0

    def _measure_avg() -> Optional[float]:
        if callable(get_avg_reprojection_error):
            try:
                return get_avg_reprojection_error(context)  # type: ignore[misc]
            except Exception:  # noqa: BLE001
                return None
        return None

    def _reduce_after(avg: Optional[float]) -> None:
        if not callable(run_reduce_error_tracks):
            return
        try:
            if avg is None:
                # Keine Messung → minimal 1 Track löschen, um Fortschritt zu
                # erzwingen
                run_reduce_error_tracks(
                    context,
                    max_to_delete=int(force_min_delete_if_nan),
                )  # type: ignore[misc]
                return

            # Dynamische Löschmenge: ceil(avg/target), clamp 1..20
            t = target_err if (target_err == target_err and target_err > 1e-8) else 0.6
            deletions = max(1, min(20, int(math.ceil(float(avg) / t))))
            run_reduce_error_tracks(
                context,
                max_to_delete=deletions,
            )  # type: ignore[misc]
        except Exception as _exc:  # noqa: BLE001
            print(f"[Solve] ReduceErrorTracks nach Solve fehlgeschlagen: {_exc}")

    # Phase 1: ohne Refine
    _apply_refine_focal_flag(context, False)
    for attempt in range(1, int(max_no_refine_attempts) + 1):
        res = _ORIG_SOLVE_FN(context)  # Einmal-Solve
        avg = _measure_avg()
        print(f"[Solve] NO_REFINE attempt={attempt}: avg={avg}")
        _reduce_after(avg)
        if isinstance(avg, (int, float)) and avg == avg and avg <= target_err:
            return {
                "status": "OK",
                "avg": float(avg),
                "phase": "NO_REFINE",
                "attempt": attempt,
            }
        # Wenn Solve selbst "FAILED" meldet, fahren wir trotzdem mit Reduktion
        # fort und loopen weiter
        if res.get("status") == "FAILED":
            # Weiter versuchen – Reduce ist bereits gelaufen
            pass

    # Phase 2: mit Refine
    _apply_refine_focal_flag(context, True)
    for attempt in range(1, int(refine_attempts) + 1):
        res = _ORIG_SOLVE_FN(context)  # Einmal-Solve
        avg = _measure_avg()
        print(f"[Solve] REFINE attempt={attempt}: avg={avg}")
        _reduce_after(avg)
        if isinstance(avg, (int, float)) and avg == avg and avg <= target_err:
            return {
                "status": "OK",
                "avg": float(avg),
                "phase": "REFINE",
                "attempt": attempt,
            }
        if res.get("status") == "FAILED":
            pass

    # Nichts erreicht → FAILED mit letzter Messung
    last_avg = _measure_avg()
    return {
        "status": "FAILED",
        "reason": "target not reached",
        "avg": (
            float(last_avg) if isinstance(last_avg, (int, float)) else None
        ),
        "phase": "REFINE",
        "attempt": int(refine_attempts),
    }


# ---------------------------------------------------------------------------
# Ursprüngliche Einmal-Solve Funktion unter internem Namen bereitstellen.
# !!! WICHTIG !!!
# Ersetze den folgenden Block durch den REALEN Einmal-Solve-Code deiner Datei.
# Der Coordinator ruft weiterhin solve_camera_only(..) auf – jetzt mit
# Orchestrierung. Dieser Block stellt sicher, dass dein bisheriger Solve-Kern
# unverändert genutzt wird.
def _solve_camera_once(context: bpy.types.Context) -> Dict[str, Any]:
    """EINMALIGER Kamera-Solve (bestehende Logik)."""
    try:
        # Wenn du bisher mit temp_override arbeitest, bitte hier deinen
        # vorhandenen Override-Kontext einsetzen.
        bpy.ops.clip.solve_camera()
        return {"status": "OK"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "FAILED", "reason": str(exc)}

