bl_info = {
    "name": "Simple Addon",
    "author": "Your Name",
    "version": (1, 11),
    "blender": (4, 4, 0),
    "location": "View3D > Object",
    "description": "Zeigt eine einfache Meldung an",
    "category": "Object",
}

import bpy
import os
import shutil
from bpy.props import IntProperty, BoolProperty

class OBJECT_OT_simple_operator(bpy.types.Operator):
    bl_idname = "object.simple_operator"
    bl_label = "Simple Operator"
    bl_description = "Gibt eine Meldung aus"

    def execute(self, context):
        self.report({'INFO'}, "Hello World from Addon")
        return {'FINISHED'}


class CLIP_OT_panel_button(bpy.types.Operator):
    bl_idname = "clip.panel_button"
    bl_label = "Proxy"
    bl_description = "Erstellt Proxy-Dateien mit 50% Gr\u00f6\u00dfe"

    def execute(self, context):
        clip = context.space_data.clip

        clip.use_proxy = True

        clip.proxy.build_25 = False
        clip.proxy.build_50 = True
        clip.proxy.build_75 = False
        clip.proxy.build_100 = False

        # Proxy mit Qualität 50 erzeugen
        clip.proxy.quality = 50

        clip.proxy.directory = "//proxies"

        # absoluten Pfad zum Proxy-Verzeichnis auflösen
        proxy_dir = bpy.path.abspath(clip.proxy.directory)
        project_dir = bpy.path.abspath("//")

        # nur löschen, wenn das Verzeichnis innerhalb des Projektes liegt
        if os.path.abspath(proxy_dir).startswith(os.path.abspath(project_dir)):
            if os.path.exists(proxy_dir):
                try:
                    shutil.rmtree(proxy_dir)
                except Exception as e:
                    self.report({'WARNING'}, f"Fehler beim L\u00f6schen des Proxy-Verzeichnisses: {e}")

        # Blender-Operator zum Erzeugen der Proxys aufrufen
        bpy.ops.clip.rebuild_proxy()

        self.report({'INFO'}, "Proxy auf 50% erstellt")
        return {'FINISHED'}


class CLIP_OT_marker_button(bpy.types.Operator):
    bl_idname = "clip.marker_button"
    bl_label = "Marker"
    bl_description = (
        "Setzt einen Clip Marker (Movie Tracking Marker) am angegebenen Frame"
    )

    def execute(self, context):
        frame = context.scene.marker_frame
        context.scene.frame_current = frame

        bpy.ops.clip.detect_features(
            threshold=0.8,
            min_distance=120,
            margin=1,
        )
        self.report({'INFO'}, f"Features bei Frame {frame} erkannt")
        return {'FINISHED'}


class CLIP_OT_clean_new_tracks(bpy.types.Operator):
    bl_idname = "clip.clean_new_tracks"
    bl_label = "Clean NEW Tracks"
    bl_description = (
        "Entfernt neu erkannte Tracks, die zu nahe an bestehenden GOOD_ "
        "Tracks im aktuellen Frame liegen"
    )

    detect: BoolProperty(
        name="Detect New Features",
        description="Vor dem Bereinigen neue Features erkennen",
        default=True,
    )

    def execute(self, context):
        space = context.space_data
        clip = space.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        width, height = clip.size
        margin = width / 100.0
        distance_px = width / 20.0

        threshold = 1.0

        if self.detect:
            bpy.ops.clip.detect_features(
                threshold=threshold,
                min_distance=distance_px,
                margin=margin,
            )

            for track in clip.tracking.tracks:
                if track.select and not track.name.startswith("NEW_"):
                    track.name = "NEW_" + track.name

        frame = context.scene.frame_current
        good_tracks = [t for t in clip.tracking.tracks if t.name.startswith("GOOD_")]

        to_remove = []
        for track in clip.tracking.tracks:
            if not track.name.startswith("NEW_"):
                continue
            marker = track.markers.find_frame(frame)
            if not marker:
                continue
            nx = marker.co[0] * width
            ny = marker.co[1] * height

            for good in good_tracks:
                g_marker = good.markers.find_frame(frame)
                if not g_marker:
                    continue
                gx = g_marker.co[0] * width
                gy = g_marker.co[1] * height
                dist = ((nx - gx) ** 2 + (ny - gy) ** 2) ** 0.5
                if dist < distance_px:
                    to_remove.append(track)
                    break

        for track in to_remove:
            try:
                clip.tracking.tracks.remove(track)
            except Exception as e:
                self.report({'WARNING'}, f"Fehler beim Entfernen von {track.name}: {e}")

        self.report({'INFO'}, f"Entfernte {len(to_remove)} NEW_ Tracks")
        return {'FINISHED'}


class CLIP_PT_tracking_panel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Track'
    bl_label = 'Addon Panel'

    def draw(self, context):
        layout = self.layout
        layout.label(text="Addon Informationen")


class CLIP_PT_button_panel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Addon'
    bl_label = 'Button Panel'

    def draw(self, context):
        layout = self.layout
        layout.prop(context.scene, 'marker_frame', text='Marker / Frame')
        layout.operator('clip.marker_button')
        layout.operator('clip.panel_button')
        row = layout.row(align=True)
        op = row.operator('clip.clean_new_tracks', text='Detect & Clean')
        op.detect = True
        op = row.operator('clip.clean_new_tracks', text='Clean Only')
        op.detect = False

classes = (
    OBJECT_OT_simple_operator,
    CLIP_OT_panel_button,
    CLIP_OT_marker_button,
    CLIP_OT_clean_new_tracks,
    CLIP_PT_tracking_panel,
    CLIP_PT_button_panel,
)


def register():
    bpy.types.Scene.marker_frame = IntProperty(
        name="Marker / Frame",
        description="Frame f\u00fcr neuen Timeline Marker",
        default=1,
    )
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.marker_frame

if __name__ == "__main__":
    register()
