# Helper/clean_error_tracks.py
# Zweck: Entfernt fehlerhafte Tracks im MovieClip basierend auf Reprojektion-Error
# Autor: Kaiserlich Tracker (Franz)
# Kompatibel mit: Blender 3.6+ (inkl. temp_override)
# Nutzung: clean_error_tracks(context, threshold=1.0, action='DELETE_TRACK')

import bpy


def clean_error_tracks(context, threshold: float = 1.0, action: str = 'DELETE_TRACK') -> None:
    """
    Entfernt oder selektiert Tracks, deren Reprojektion-Fehler über dem Grenzwert liegt.
    Nutzt bpy.ops.clip.clean_error(...) im sicheren CLIP_EDITOR-Kontext.

    Args:
        context (bpy.types.Context): Aktueller Kontext (beliebig, z. B. Operator-Kontext)
        threshold (float): Grenzwert (Fehler > threshold → betroffen)
        action (str): 'DELETE_TRACK', 'DELETE_SEGMENTS' oder 'SELECT'
    """
    # --- Gültigen Clip-Editor finden ---
    area = None
    region = None
    space = None

    # a) Falls aktueller Kontext bereits CLIP_EDITOR ist
    if getattr(context, "area", None) and getattr(context.area, "type", "") == "CLIP_EDITOR":
        area = context.area
        for r in area.regions:
            if r.type == "WINDOW":
                region = r
                break
        space = area.spaces.active if area.spaces else None

    # b) Sonst: ersten CLIP_EDITOR im aktiven Screen suchen
    if area is None:
        for a in bpy.context.screen.areas:
            if a.type == "CLIP_EDITOR":
                area = a
                for r in a.regions:
                    if r.type == "WINDOW":
                        region = r
                        break
                space = a.spaces.active if a.spaces else None
                break

    # c) Wenn kein Clip-Editor verfügbar → Abbruch
    if not all([area, region, space]):
        print("[CleanErrorTracks] ❌ Kein CLIP_EDITOR-Kontext gefunden.")
        return

    # d) Clip prüfen
    clip = getattr(space, "clip", None)
    if clip is None:
        print("[CleanErrorTracks] ❌ Kein aktiver MovieClip im Space vorhanden.")
        return

    # --- Operator sicher aufrufen ---
    try:
        with bpy.context.temp_override(area=area, region=region, space_data=space):
            print(f"[CleanErrorTracks] 🧹 Starte clean_error (threshold={threshold:.4f}, action={action}) …")
            bpy.ops.clip.clean_error(clean_error=threshold, action=action)
            print(f"[CleanErrorTracks] ✅ Clean-Error abgeschlossen (Clip={clip.name}).")
    except Exception as e:
        print(f"[CleanErrorTracks] ❌ Fehler bei clean_error: {e}")
