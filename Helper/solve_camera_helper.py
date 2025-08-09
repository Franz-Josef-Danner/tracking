# Helper/solve_camera_helper.py
# -*- coding: utf-8 -*-
import bpy


def _find_clip_editor_ctx(context):
    """Liefert (area, region, space) eines sichtbaren CLIP_EDITOR oder (None, None, None)."""
    for area in context.window.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return area, region, area.spaces.active
    return None, None, None


def solve_camera_helper(
    context,
    *,
    refine=None,           # z.B. 'FOCAL_LENGTH_RADIAL_K1_K2' – wird gegen Enum geprüft
    keyframe_a=None,       # int oder None
    keyframe_b=None,       # int oder None
    use_tripod=False,      # Stativ-Solver
    clear_before=False     # vorhandene Lösung vorher löschen
):
    area, region, space = _find_clip_editor_ctx(context)
    if not space or not getattr(space, "clip", None):
        raise RuntimeError("Kein aktiver CLIP_EDITOR mit Movie Clip gefunden.")

    clip = space.clip
    settings = clip.tracking.settings

    # Optional bestehende Lösung löschen
    if clear_before:
        override = context.copy()
        override.update({"area": area, "region": region, "space_data": space, "edit_movieclip": clip})
        try:
            bpy.ops.clip.clear_solution(override)
        except RuntimeError:
            pass  # z. B. wenn keine Lösung existiert

    # Solver-Parameter setzen (Enum robust gegen API-Änderungen prüfen)
    if refine is not None:
        allowed = settings.bl_rna.properties['refine'].enum_items.keys()
        if refine in allowed:
            settings.refine = refine
        else:
            print(f"[Solve] Warnung: refine='{refine}' nicht gültig. Zulässig: {list(allowed)}")

    if keyframe_a is not None and hasattr(settings, "keyframe_a"):
        settings.keyframe_a = int(keyframe_a)
    if keyframe_b is not None and hasattr(settings, "keyframe_b"):
        settings.keyframe_b = int(keyframe_b)

    if hasattr(settings, "use_tripod_solver"):
        settings.use_tripod_solver = bool(use_tripod)

    # Operator im korrekten Kontext ausführen
    override = context.copy()
    override.update({"area": area, "region": region, "space_data": space, "edit_movieclip": clip})

    result = bpy.ops.clip.solve_camera(override)

    # Erfolgsmetriken auslesen
    recon = clip.tracking.reconstruction
    avg_err = getattr(recon, "average_error", None)
    is_valid = getattr(recon, "is_valid", False)

    print(f"[Solve] Result: {result}, valid={is_valid}, avg_error={avg_err}")
    return {"result": result, "valid": is_valid, "average_error": avg_err}
