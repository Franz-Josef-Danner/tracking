import bpy


def _apply_pattern_size(clip, size):
    """Setze Pattern Size kompatibel für verschiedene Blender-Versionen.

    In Blender-Versionen < 4.x existiert 'default_pattern_size'. Ein direktes
    'pattern_size' Attribut auf tracking.settings ist (laut Fehler) nicht vorhanden.
    Wir versuchen mehrere mögliche Namen (defensiv), setzen den ersten der existiert.
    """
    settings = clip.tracking.settings
    for attr in ("default_pattern_size", "pattern_size"):
        if hasattr(settings, attr):
            try:
                setattr(settings, attr, size)
            except Exception:
                pass
            break


def _normalize_pattern_size(raw):
    # Mindestgröße 5, Obergrenze moderat begrenzen (z.B. 51)
    v = int(max(5, min(raw, 51)))
    # Pattern Sizes sind typischerweise ungerade → sicherstellen
    if v % 2 == 0:
        v += 1
    return v


def detect_features(context, values):
    clip = context.edit_movieclip
    if clip is None:
        return

    # Dynamische Pattern Size vorbereiten
    p_size = _normalize_pattern_size(values["pz"])
    _apply_pattern_size(clip, p_size)

    bpy.ops.clip.detect_features(
        placement='FRAME',
        margin=values["ma"],
        threshold=values["tr"],
        min_distance=values["md"],
    )
