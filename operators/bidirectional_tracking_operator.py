import bpy


class TRACKING_OT_bidirectional_tracking(bpy.types.Operator):
    bl_idname = "tracking.bidirectional_tracking"
    bl_label = "Tracking"
    bl_description = (
        "Bidirektionales Tracking aller selektierten Marker mit L\u00f6schung kurzer Tracks"
    )

    @classmethod
    def poll(cls, context):
        return (
            context.area
            and context.area.type == "CLIP_EDITOR"
            and getattr(context.space_data, "clip", None)
        )

    def execute(self, context):
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}
        tracking = clip.tracking

        # 1. Proxy aktivieren
        if not clip.use_proxy:
            clip.use_proxy = True

        # 2. Selektierte Marker bidirektional tracken
        # Marker vorwärts tracken
        bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=True)

        # Dann rückwärts tracken
        bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=True, sequence=True)

        # 3. Kurze Tracks identifizieren und l\u00f6schen
        min_length = scene.get("frames_per_track", 10)
        short_tracks = []

        for track in tracking.tracks:
            if not track.select or track.mute:
                continue

            frame_numbers = [m.frame for m in track.markers if not m.mute]
            if not frame_numbers:
                continue

            track_length = max(frame_numbers) - min(frame_numbers) + 1
            if track_length < min_length:
                short_tracks.append(track)

        if short_tracks:
            for t in short_tracks:
                t.select = True
            bpy.ops.clip.delete_track()
            self.report({'INFO'}, f"{len(short_tracks)} kurze Tracks gel\u00f6scht (< {min_length} Frames)")
        else:
            self.report({'INFO'}, "Keine kurzen Tracks gefunden.")

        return {'FINISHED'}
