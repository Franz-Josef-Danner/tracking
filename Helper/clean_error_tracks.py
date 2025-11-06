# Helper/clean_error_tracks.py
# Zweck: Sichere Hülle um bpy.ops.clip.clean_error mit zuverlässigem Fallback.
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

    # --- Operator sicher ausführen (wenn registriert) ---
    try:
        print(f"[CleanErrorTracks] 🔍 Vorbereitungen: area={area}, region={region}, space={space}")
        if hasattr(clip, "tracking") and hasattr(clip.tracking, "objects"):
            # Vorher-Status
            total_tracks = sum(len(obj.tracks) for obj in clip.tracking.objects)
            print(f"[CleanErrorTracks] 🎞️ Clip '{clip.name}' enthält {total_tracks} Tracks vor dem Clean.")

        # Versuch über Operator (falls verfügbar)
        with bpy.context.temp_override(area=area, region=region, space_data=space, edit_movieclip=clip):
            print(f"[CleanErrorTracks] 🧹 clean_error(threshold={thr:.4f}, action={action}) …")
            result = bpy.ops.clip.clean_error(clean_error=thr, action=action)  # kann „could not be found“ werfen
            print(f"[CleanErrorTracks] ✅ Operator ausgeführt (Result={result}, Clip={clip.name}).")

        # Nachher-Status
        if hasattr(clip, "tracking") and hasattr(clip.tracking, "objects"):
            total_tracks_after = sum(len(obj.tracks) for obj in clip.tracking.objects)
            print(f"[CleanErrorTracks] 📊 Tracks nach clean_error: {total_tracks_after}")
        return

    except Exception as e:
        print(f"[CleanErrorTracks] ❌ Fehler bei clean_error: {e}")
        # -> Fallback aktivieren
        pass

    # --- Fallback: API-basiertes Löschen ohne Operator-Kontext ---
    try:
        tracking = getattr(clip, "tracking", None)
        if tracking is None or not hasattr(tracking, "objects") or not tracking.objects:
            print("[CleanErrorTracks] ⚠️ Fallback: Keine Tracking-Objekte gefunden.")
            return

        # Alle betroffenen Tracks über alle Tracking-Objekte einsammeln
        candidates = []
        for obj in tracking.objects:
            try:
                for t in obj.tracks:
                    if getattr(t, "average_error", 0.0) > thr:
                        candidates.append((obj, t))
            except Exception as scan_ex:
                print(f"[CleanErrorTracks][DBG] ⚠️ Scan-Fehler in Objekt '{getattr(obj, 'name', '?')}': {scan_ex}")

        print(f"[CleanErrorTracks] ⚙️ Fallback aktiviert → {len(candidates)} Tracks über Threshold={thr:.2f}.")

        deleted = 0
        for obj, t in candidates:
            try:
                tracks_collection = obj.tracks
                total_before = len(tracks_collection)
                print(f"[CleanErrorTracks][DBG] → Lösche '{t.name}' in Objekt '{obj.name}' "
                      f"(avg_err={getattr(t, 'average_error', 0.0):.2f}, vorher={total_before})")

                # Direkte API-Entfernung
                tracks_collection.remove(t)

                total_after = len(tracks_collection)
                deleted += 1
                print(f"[CleanErrorTracks][DBG] ✅ Track '{t.name}' entfernt (nachher={total_after}).")

            except Exception as rm_ex:
                print(f"[CleanErrorTracks][DBG] ❌ API-Remove fehlgeschlagen für '{t.name}' "
                      f"in Objekt '{getattr(obj, 'name', '?')}': {rm_ex}")

        # Abschlussstatus
        remaining = sum(len(obj.tracks) for obj in tracking.objects)
        print(f"[CleanErrorTracks][DBG] 🧾 Abschlussbericht: {deleted} Tracks gelöscht, verbleibend {remaining}")
        print(f"[CleanErrorTracks] ⚙️ Fallback abgeschlossen (API-basiert).")

    except Exception as ex:
        print(f"[CleanErrorTracks][ERR] Unerwarteter Fallback-Fehler: {ex}")
