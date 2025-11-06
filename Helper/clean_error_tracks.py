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
        # Log: Vorbereitungsprüfung
        print(f"[CleanErrorTracks] 🔍 Vorbereitungen: area={area}, region={region}, space={space}")

        clip = getattr(space, "clip", None)
        if clip is None:
            print("[CleanErrorTracks] ❌ Kein aktiver Clip im Space – clean_error kann nicht ausgeführt werden.")
            raise RuntimeError("Kein aktiver Clip im Space")

        # Log: Clipname und Track-Anzahl vor Ausführung
        if hasattr(clip, "tracking") and hasattr(clip.tracking, "tracks"):
            print(f"[CleanErrorTracks] 🎞️ Clip '{clip.name}' enthält {len(clip.tracking.tracks)} Tracks vor dem Clean.")

        # Sichere Context-Übergabe inkl. edit_movieclip
        with bpy.context.temp_override(area=area, region=region, space_data=space, edit_movieclip=clip):
            print(f"[CleanErrorTracks] 🧹 clean_error(threshold={thr:.4f}, action={action}) …")
            result = bpy.ops.clip.clean_error(clean_error=thr, action=action)
            print(f"[CleanErrorTracks] ✅ Operator ausgeführt (Result={result}, Clip={clip.name}).")

        # Log: Anzahl Tracks nach erfolgreichem Operator
        if hasattr(clip, "tracking") and hasattr(clip.tracking, "tracks"):
            print(f"[CleanErrorTracks] 📊 Tracks nach clean_error: {len(clip.tracking.tracks)}")

    except Exception as e:
        print(f"[CleanErrorTracks] ❌ Fehler bei clean_error: {e}")

        if hasattr(clip, "tracking"):
            tracks = clip.tracking.tracks
            to_delete = [t for t in tracks if getattr(t, "average_error", 0.0) > thr]
            print(f"[CleanErrorTracks] ⚙️ Fallback aktiviert → {len(to_delete)} Tracks über Threshold={thr:.2f}.")

            area = None
            region = None
            space = None
            for a in bpy.context.screen.areas:
                if a.type == "CLIP_EDITOR":
                    area = a
                    region = next((r for r in a.regions if r.type == "WINDOW"), None)
                    space = a.spaces.active
                    break

            deleted = 0
            for t in to_delete:
                    print(f"[CleanErrorTracks][DBG] → Starte API-basierte Löschung von '{t.name}' (avg_err={getattr(t, 'average_error', 0.0):.2f})")

                    tracking_obj = clip.tracking.objects.active
                    if not tracking_obj:
                        print("[CleanErrorTracks][DBG] ⚠️ Kein aktives Tracking-Objekt gefunden – überspringe.")
                        continue

                    tracks_collection = tracking_obj.tracks
                    total_before = len(tracks_collection)
                    print(f"[CleanErrorTracks][DBG] Aktives Tracking-Objekt: {tracking_obj.name}, Tracks gesamt vor Entfernen={total_before}")

                    # Manuelle, Low-Level Entfernung
                    try:
                        tracks_collection.remove(t)
                        deleted += 1
                        total_after = len(tracks_collection)
                        print(f"[CleanErrorTracks][DBG] ✅ Track '{t.name}' entfernt (vorher={total_before}, nachher={total_after}).")
                    except Exception as rm_ex:
                        print(f"[CleanErrorTracks][DBG] ❌ API-Remove fehlgeschlagen für '{t.name}': {rm_ex}")

                except Exception as ex:
                    print(f"[CleanErrorTracks][ERR] Ausnahme beim Entfernen von '{t.name}': {ex}")

            remaining = len(clip.tracking.objects.active.tracks) if clip.tracking.objects.active else -1
            print(f"[CleanErrorTracks][DBG] 🧾 Abschlussbericht: {deleted} Tracks gelöscht, verbleibend {remaining}")
            print(f"[CleanErrorTracks] ⚙️ Fallback abgeschlossen (API-basiert).")
