import bpy

def cleanup_tracks(context):
    scene = context.scene
    clip = context.space_data.clip
    tracking = clip.tracking
    tracks = tracking.tracks

    width, height = clip.size
    ee_initial = width / 300.0         # Dynamischer Schwellwert in Abhängigkeit von Auflösung
    threshold_factor = 0.9             # Reduktionsfaktor für eb

    frame_range = (scene.frame_start, scene.frame_end)

    # Nur ein Durchlauf über das ganze Bild
    passes = [
        {"x_min": 0.0, "x_max": 1.0, "y_min": 0.0, "y_max": 1.0}
    ]

    def get_marker_position(track, frame):
        for marker in track.markers:
            if marker.frame == frame:
                return marker.co
        return None

    total_deleted = 0
    overall_max_error = 0.0

    for p in passes:
        ee = ee_initial  # Einheitlicher Fehlerwert für gesamten Framebereich
        for frame in range(frame_range[0] + 1, frame_range[1] - 1):
            valid_tracks = []
            vm_values = []
            velocities = []

            for track in tracks:
                p1 = get_marker_position(track, frame - 1)
                p2 = get_marker_position(track, frame)
                p3 = get_marker_position(track, frame + 1)
                if not (p1 and p2 and p3):
                    continue

                # Nur Marker im erlaubten Bildbereich
                if not (p["x_min"] <= p2[0] <= p["x_max"] and p["y_min"] <= p2[1] <= p["y_max"]):
                    continue

                # Koordinaten in Pixel umrechnen
                pxi_f1 = p1[0] * width
                pyi_f1 = p1[1] * height
                pxi_fi = p2[0] * width
                pyi_fi = p2[1] * height
                pxi_f2 = p3[0] * width
                pyi_f2 = p3[1] * height

                # Formel: vm_i = ((fi - f1) + (f2 - fi)) / 2, getrennt für x und y
                vxm = (pxi_fi - pxi_f1) + (pxi_f2 - pxi_fi)
                vym = (pyi_fi - pyi_f1) + (pyi_f2 - pyi_fi)
                vm = (vxm + vym) / 2

                print(f"vm_i: {vm:.6f}")  # einzige Konsolenausgabe

                vm_values.append(vm)
                velocities.append((vxm, vym))
                valid_tracks.append((track, vxm, vym, vm))

            maa = len(valid_tracks)
            if maa == 0:
                continue

            # Durchschnittliche Bewegung aller gültigen Marker
            vxa = sum(v[0] for v in velocities) / maa
            vya = sum(v[1] for v in velocities) / maa
            va = (vxa + vya) / 2

            eb = max(abs(vm - va) for (_, _, _, vm) in valid_tracks)
            overall_max_error = max(overall_max_error, eb)

            # Stufenweise Bereinigung (Ausreißer entfernen)
            while eb > ee:
                deleted_this_round = 0
                for track, vxm, vym, vm in valid_tracks:
                    if abs(vm - va) >= eb:
                        track.select = True
                        deleted_this_round += 1
                if deleted_this_round > 0:
                    bpy.ops.clip.delete_track()
                    total_deleted += deleted_this_round
                eb *= threshold_factor  # schrittweise Reduktion

    return total_deleted, overall_max_error


class CLIP_OT_cleanup_tracks(bpy.types.Operator):
    bl_idname = "clip.cleanup_tracks"
    bl_label = "Cleanup Tracks"

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.clip is not None

    def execute(self, context):
        deleted, max_error = cleanup_tracks(context)
        if deleted:
            self.report({'INFO'}, f"{deleted} Marker gelöscht. Max. Fehler: {max_error:.2f}")
        else:
            self.report({'INFO'}, "Keine Marker gelöscht.")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(CLIP_OT_cleanup_tracks)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_cleanup_tracks)

if __name__ == "__main__":
    register()
