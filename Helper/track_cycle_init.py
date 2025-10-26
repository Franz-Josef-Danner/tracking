import bpy
from typing import List, Tuple, Dict, Deque
from collections import deque

def initialize_tracking_state(clip: bpy.types.MovieClip, selected_names: List[str]) -> Dict[str, Deque[Tuple[int, float, float]]]:
    """Erzeugt leere Verlaufs-Deques für alle aktiven Tracks."""
    return {name: deque(maxlen=10) for name in selected_names}

def restore_selection(clip: bpy.types.MovieClip, original_names: List[str]) -> None:
    """Stellt ursprüngliche Track-Selektion wieder her."""
    for tr in clip.tracking.tracks:
        tr.select = (tr.name in original_names)