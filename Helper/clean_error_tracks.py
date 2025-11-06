# Helper/clean_error_tracks.py
# Zweck: Sichere Hülle um bpy.ops.clip.clean_error mit zuverlässigem Fallback:
#        Wenn kein gültiger Schwellenwert ermittelt werden kann -> threshold = 20.0

import math
import bpy

DEFAULT_CLEAN_ERROR = 20.0  # Harte Vorgabe laut Anforderung

def _coerce_threshold(value) -> float:
    """Konvertiert beliebige Eingaben in einen nutzbaren float-Threshold.
    Fallback: DEFAULT_CLEAN_ERROR (20.0), wenn None/NaN/inf/<=0.
    """
    try:
        thr = float(value)
    except (TypeError, ValueError):
        return DEFAULT_CLEAN_ERROR

    if not math.isfinite(thr) or thr <= 0.0:
        return DEFAULT_CLEAN_ERROR
    return thr


def clean_error_tracks(
    context: bpy.types.Context,
    threshold: float | None = None,
    action: str = 'DELETE_TRACK'
) -> None:
    """
    Führt bpy.ops.clip.clean_error kontext-sicher aus.
    Fallback-Policy: threshold -> 20.0, wenn value ungültig.

    Args:
        context: beliebiger Blender-Kontext (Operator/Modal/UI)
        threshold: gewünschter Grenzwert; None/NaN/inf/≤0 -> 20.0
        action: 'DELETE_TRACK' | 'DELETE_SEGMENTS' | 'SELECT'
    """
    thr = _coerce_threshold(threshold)

    # --- CLIP_EDITOR suchen ---
    area = None
    region = None
    space = None

    # a) aktueller Kontext bereits CLIP_EDITOR?
    if getattr(context, "area", None) and getattr(context.area, "type", "") == "CLIP_EDITOR":
        area = context.area
        region = next((r for r in area.regions if r.type == "WINDOW"), None)
        space  = area.spaces.active if area.spaces else None

    # b) sonst ersten CLIP_EDITOR im aktiven Screen nehmen
    if area is None:
        for a in bpy.context.screen.areas:
            if a.type == "CLIP_EDITOR":
                area = a
                region = next((r for r in a.regions if r.type == "WINDOW"), None)
                space  = a.spaces.active if a.spaces else None
                break

    if not all([area, region, space]):
        print("[CleanErrorTracks] ❌ Kein CLIP_EDITOR-Kontext gefunden.")
        return

    clip = getattr(space, "clip", None)
    if clip is None:
        print("[CleanErrorTracks] ❌ Kein aktiver MovieClip im Space vorhanden.")
        return

    # --- Operator sicher ausführen ---
    try:
        override = bpy.context.copy()
        override["window"] = bpy.context.window
        override["screen"] = bpy.context.window.screen
        override["area"] = area
        override["region"] = region
        override["space_data"] = space

        print(f"[CleanErrorTracks] 🧹 clean_error(threshold={thr:.4f}, action={action}) …")
        bpy.ops.clip.clean_error(override, clean_error=thr, action=action)
        print(f"[CleanErrorTracks] ✅ abgeschlossen (Clip={clip.name}).")

    except Exception as e:
        print(f"[CleanErrorTracks] ❌ Fehler bei clean_error: {e}")
        if hasattr(clip, "tracking"):
            tracks = clip.tracking.tracks
            for t in tracks:
                if t.average_error > thr:
                    clip.tracking.tracks.remove(t)
            print(f"[CleanErrorTracks] ⚙️ Fallback: Manuelles Löschen mit Threshold={thr:.2f} abgeschlossen.")


