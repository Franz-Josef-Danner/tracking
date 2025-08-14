# Helper/main_to_adapt.py
import bpy
from typing import Optional, Tuple, Set, Dict, Any

__all__ = ("main_to_adapt", "clip_override")

def clip_override(context: bpy.types.Context) -> Optional[Dict[str, Any]]:
    """Sicherer CLIP_EDITOR-Override (oder None)."""
    win = getattr(context, "window", None)
    if not win or not getattr(win, "screen", None):
        return None
    for area in win.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return {'area': area, 'region': region, 'space_data': area.spaces.active}
    return None


def main_to_adapt(
    context: bpy.types.Context,
    *,
    factor: int = 4,
    use_override: bool = True,
    call_next: bool = False,
    invoke_next: bool = False,  # beibehalten für API-Kompatibilität; wird nicht verwendet
) -> Tuple[bool, int, Optional[Set[str]]]:
    """
    Setzt scene['marker_adapt'] aus scene['marker_basis'] * factor * 0.9.
    Rein passiv, keine Folge-Schritte. Gibt (ok, marker_adapt, op_result) zurück.
    """
    scene = getattr(context, "scene", None)
    if scene is None:
        print("[MainToAdapt][ERROR] Kein gültiger Scene-Kontext.")
        return False, 0, {'CANCELLED'}

    # Faktor robust halten (entspricht altem Operator: min=1)
    try:
        factor = int(factor)
        if factor < 1:
            factor = 1
    except Exception:
        factor = 4

    # marker_basis robust lesen
    try:
        marker_basis = int(scene.get("marker_basis", 25))
    except Exception as e:
        print(f"[MainToAdapt][ERROR] marker_basis nicht lesbar: {e}")
        return False, 0, {'CANCELLED'}

    print(f"[MarkerHelper] basis={marker_basis}, factor={factor}")
    marker_adapt = int(marker_basis * factor * 0.9)
    scene["marker_adapt"] = marker_adapt
    print(f"[MainToAdapt] marker_adapt gesetzt: {marker_adapt} (basis={marker_basis}, factor={factor})")

    # Passiver Rückgabewert für Aufrufer-Kompatibilität
    op_result: Set[str] = {'FINISHED'}
    return True, marker_adapt, op_result
