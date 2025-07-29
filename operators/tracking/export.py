import bpy
from bpy.props import BoolProperty
import unicodedata
# Import helper modules from absolute package path
from tracking_tools.helpers import strip_prefix
from tracking_tools.helpers.prefix_new import PREFIX_NEW
from tracking_tools.helpers.prefix_track import PREFIX_TRACK
from tracking_tools.helpers.prefix_good import PREFIX_GOOD
from tracking_tools.helpers.prefix_testing import PREFIX_TEST

class CLIP_OT_prefix_new(bpy.types.Operator):
    bl_idname = "clip.prefix_new"
    bl_label = "NEW"
    bl_description = "Präfix NEW_ für selektierte Tracks setzen"

    silent: BoolProperty(default=False, options={'HIDDEN'})

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        selected = [t for t in clip.tracking.tracks if t.select]
        count = 0
        for i, track in enumerate(selected):
            try:
                _ = track.name
            except Exception as e:
                print(f"\u26a0\ufe0f Marker-Name fehlerhaft: {track} ({e})")
                track.name = f"{PREFIX_TRACK}{i:03d}"
            else:
                safe = unicodedata.normalize("NFKD", track.name).encode(
                    "ascii", "ignore"
                ).decode("ascii")
                if not safe:
                    safe = f"{PREFIX_TRACK}{i:03d}"
                track.name = safe
            track.name = f"{PREFIX_NEW}{i:03d}"
            count += 1
        if not self.silent:
            self.report({'INFO'}, f"{count} Tracks umbenannt")
        return {'FINISHED'}


class CLIP_OT_prefix_test(bpy.types.Operator):
    bl_idname = "clip.prefix_test"
    bl_label = "Name Test"
    bl_description = "Präfix TEST_ für selektierte Tracks setzen"

    silent: BoolProperty(default=False, options={'HIDDEN'})

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        prefix = PREFIX_TEST
        count = 0
        for track in clip.tracking.tracks:
            if track.select and not track.name.startswith(prefix):
                track.name = prefix + track.name
                count += 1
        if not self.silent:
            self.report({'INFO'}, f"{count} Tracks umbenannt")
        return {'FINISHED'}


class CLIP_OT_prefix_track(bpy.types.Operator):
    bl_idname = "clip.prefix_track"
    bl_label = "Name Track"
    bl_description = "Präfix TRACK_ für selektierte Tracks setzen"

    silent: BoolProperty(default=False, options={'HIDDEN'})

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        prefix = PREFIX_TRACK
        count = 0
        for track in clip.tracking.tracks:
            if track.select:
                base_name = strip_prefix(track.name)
                new_name = prefix + base_name
                if track.name != new_name:
                    track.name = new_name
                    count += 1
        if not self.silent:
            self.report({'INFO'}, f"{count} Tracks umbenannt")
        return {'FINISHED'}


class CLIP_OT_prefix_good(bpy.types.Operator):
    bl_idname = "clip.prefix_good"
    bl_label = "Name GOOD"
    bl_description = "TRACK_ durch GOOD_ ersetzen"

    silent: BoolProperty(default=False, options={'HIDDEN'})

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        count = 0
        for track in clip.tracking.tracks:
            if track.name.startswith(PREFIX_TRACK):
                track.name = PREFIX_GOOD + track.name[len(PREFIX_TRACK):]
                count += 1
        if not self.silent:
            self.report({'INFO'}, f"{count} Tracks umbenannt")
        return {'FINISHED'}

operator_classes = (
    CLIP_OT_prefix_new,
    CLIP_OT_prefix_test,
    CLIP_OT_prefix_track,
    CLIP_OT_prefix_good,
)

