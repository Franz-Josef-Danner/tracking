"""Helpers for removing NEW_ markers.

The module provides :func:`delete_close_new_markers` to remove only the
NEW_ markers that are too close to GOOD_ markers in the current frame and
``delete_new_markers`` to wipe all NEW_ markers from the clip."""

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


def delete_new_markers(context, prefix="NEW_", report=None):
    """Delete all tracks starting with ``prefix`` using the delete operator."""

    space = getattr(context, "space_data", None)
    clip = getattr(space, "clip", None)
    if clip is None:
        clip = getattr(context.scene, "clip", None)
    if not clip:
        if report:
            report({'WARNING'}, "❌ Kein aktiver Clip gefunden.")
        return 0

    tracks = clip.tracking.tracks
    to_remove = [t for t in tracks if t.name.startswith(prefix)]
    if not to_remove:
        return 0

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
                            space.clip = clip
                            with context.temp_override(area=area, region=region, space_data=space):
                                bpy.ops.clip.delete_track()
                            if report:
                                report({'INFO'}, f"🗑️ Gelöscht: {len(to_remove)} {prefix} Marker")
                            return len(to_remove)

    if report:
        report({'ERROR'}, "Kein geeigneter Clip Editor Bereich gefunden")
    return 0
