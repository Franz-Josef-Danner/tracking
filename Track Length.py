import bpy

class TRACKING_OT_delete_short_tracks_with_prefix(bpy.types.Operator):
    bl_idname = "tracking.delete_short_tracks_with_prefix"
    bl_label = "Delete Short Tracks with Prefix"
    bl_description = "Delete tracking tracks with prefix 'TRACK_' and less than 25 frames"

    def execute(self, context):
        print("\n=== [Operator gestartet: TRACKING_OT_delete_short_tracks_with_prefix] ===")

        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "No clip loaded")
            print("❌ Kein Movie Clip geladen – Abbruch.")
            return {'CANCELLED'}
        print(f"🎬 Clip: {clip.name}")

        active_obj = clip.tracking.objects.active
        tracks = active_obj.tracks
        print(f"📷 Aktives Objekt: {active_obj.name} — {len(tracks)} Tracks vorhanden")

        # Filter nach Präfix und Marker-Anzahl
        tracks_to_delete = [
            t for t in tracks
            if t.name.startswith("TRACK_") and len(t.markers) < 25
        ]

        print("🎯 Tracks mit Präfix 'TRACK_' und < 25 Frames:")
        for t in tracks_to_delete:
            print(f"   - {t.name} ({len(t.markers)} Frames)")

        for track in tracks:
            track.select = track in tracks_to_delete

        if not tracks_to_delete:
            print("ℹ️ Keine passenden Tracks gefunden – beende.")
            self.report({'INFO'}, "No short tracks found with prefix 'TRACK_'")
            return {'CANCELLED'}

        print("🔎 Suche nach CLIP_EDITOR Bereich für Operator...")
        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        for space in area.spaces:
                            if space.type == 'CLIP_EDITOR':
                                print("✅ Kontext bereit – führe delete_track() aus")
                                with context.temp_override(
                                    area=area,
                                    region=region,
                                    space_data=space
                                ):
                                    bpy.ops.clip.delete_track()
                                print(f"🗑️ {len(tracks_to_delete)} Track(s) gelöscht.")
                                self.report({'INFO'}, f"Deleted {len(tracks_to_delete)} short tracks with prefix 'TRACK_'")
                                print("=== [Operator erfolgreich beendet] ===\n")
                                return {'FINISHED'}

        print("❌ Kein geeigneter Clip Editor Bereich gefunden.")
        self.report({'ERROR'}, "No Clip Editor area found.")
        print("=== [Operator abgebrochen] ===\n")
        return {'CANCELLED'}

def register():
    bpy.utils.register_class(TRACKING_OT_delete_short_tracks_with_prefix)
    print("🔧 Operator registriert")

def unregister():
    bpy.utils.unregister_class(TRACKING_OT_delete_short_tracks_with_prefix)
    print("🧹 Operator entfernt")

if __name__ == "__main__":
    register()