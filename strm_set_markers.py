import bpy
from .strm_overlay import get_overlay_state


class STRM_OT_PlaceMarkers(bpy.types.Operator):
    bl_idname = "clip.strm_place_markers"
    bl_label = "Marker setzen (STRM)"
    bl_description = "Linksklick fügt Marker hinzu, Rechtsklick oder ESC beendet"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        if context.space_data.type != 'CLIP_EDITOR':
            self.report({'ERROR'}, "Nicht im Clip Editor.")
            return {'CANCELLED'}
        clip = context.edit_movieclip
        if not clip:
            self.report({'ERROR'}, "Kein MovieClip aktiv.")
            return {'CANCELLED'}
        self._add_handler(context)
        context.window_manager.modal_handler_add(self)
        self.report({'INFO'}, "Marker-Modus: Linksklick=Hinzufügen, Rechtsklick/ESC=Fertig")
        return {'RUNNING_MODAL'}

    def _add_handler(self, context):
        # Stelle sicher, dass Overlay-State existiert
        get_overlay_state(context.scene, ensure=True)

    def modal(self, context, event):
        if event.type in {'RIGHTMOUSE', 'ESC'}:
            self._redraw(context)
            return {'FINISHED'}

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            region = context.region
            rv2d = region.view2d
            x = event.mouse_region_x
            y = event.mouse_region_y
            vx, vy = rv2d.region_to_view(x, y)
            ov = get_overlay_state(context.scene)
            markers = ov.get("markers") or []
            markers.append((float(vx), float(vy)))
            ov["markers"] = markers
            self._redraw(context)
        return {'RUNNING_MODAL'}

    def _redraw(self, context):
        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        region.tag_redraw()


def register():
    bpy.utils.register_class(STRM_OT_PlaceMarkers)


def unregister():
    bpy.utils.unregister_class(STRM_OT_PlaceMarkers)
