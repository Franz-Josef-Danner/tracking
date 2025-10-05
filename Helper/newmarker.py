"""Erzeugt neue Marker (Platzhalter-Logik)."""
from __future__ import annotations

import bpy
from typing import Sequence


def create_new_markers(context: bpy.types.Context, count: int):
    """Legt eine definierte Anzahl neuer (Dummy) Marker an.

    Aktuell Platzhalter: In der Praxis müsste man Bildbereiche scannen
    oder vorhandene Feature-Kandidaten nutzen. Hier nur Logging.
    """
    if context.space_data is None or context.space_data.type != 'CLIP_EDITOR':
        print("[Kaiserlich Tracker][NEWMARKER] Nicht im Clip Editor.")
        return []
    print(f"[Kaiserlich Tracker][NEWMARKER] Soll {count} neue Marker vorbereiten (Platzhalter)")
    return []
