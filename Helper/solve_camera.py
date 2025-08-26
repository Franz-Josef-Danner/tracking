import bpy

def solve_camera_only(context):
    """Löst nur den Kamera-Solve aus, mit optionalem Kontext-Override."""
    area = region = space = None
    if context.window and context.window.screen:
        for area in context.window.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        space = area.spaces.active
                        region_window = region
                        break
                break

    try:
        if area and region_window and space:
            with context.temp_override(area=area, region=region_window, space_data=space):
                return bpy.ops.clip.solve_camera('INVOKE_DEFAULT')
        else:
            return bpy.ops.clip.solve_camera('INVOKE_DEFAULT')
    except Exception as e:
        print(f"[Solve] Fehler beim Start des Solve-Operators: {e}")
        return {'CANCELLED'}
