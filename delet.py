import bpy
import mathutils


def delete_close_new_markers(context, min_distance=0.02, report=None):
    """Delete NEW_ tracks near GOOD_ tracks in the current frame."""
    clip = context.space_data.clip
    if not clip:
        if report:
            report({'WARNING'}, "❌ Kein aktiver Clip gefunden.")
        return False

    current_frame = context.scene.frame_current
    tracks = clip.tracking.tracks

    neu_tracks = [t for t in tracks if t.name.startswith("NEW_")]
    good_tracks = [t for t in tracks if t.name.startswith("GOOD_")]

    to_remove = []

    for neu in neu_tracks:
        neu_marker = neu.markers.find_frame(current_frame)
        if not neu_marker:
            continue
        neu_pos = mathutils.Vector(neu_marker.co)

        for good in good_tracks:
            good_marker = good.markers.find_frame(current_frame)
            if not good_marker:
                continue
            good_pos = mathutils.Vector(good_marker.co)

            distance = (neu_pos - good_pos).length
            if distance < min_distance:
                msg = (
                    f"⚠️ {neu.name} ist zu nahe an {good.name} (Distanz: {distance:.5f}) → Löschen"
                )
                if report:
                    report({'INFO'}, msg)
                to_remove.append(neu)
                break

    if not to_remove:
        if report:
            report({'INFO'}, "Keine NEW_-Marker zum Löschen gefunden")
        return False

    for t in tracks:
        t.select = False
    for t in to_remove:
        t.select = True

    for area in context.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    for space in area.spaces:
                        if space.type == 'CLIP_EDITOR':
                            with context.temp_override(
                                area=area,
                                region=region,
                                space_data=space,
                            ):
                                bpy.ops.clip.delete_track()
                            if report:
                                report(
                                    {'INFO'},
                                    f"🗑️ Gelöscht: {len(to_remove)} NEW_-Marker im Frame {current_frame}",
                                )
                            return True

    if report:
        report({'ERROR'}, "Kein geeigneter Clip Editor Bereich gefunden")
    return False
