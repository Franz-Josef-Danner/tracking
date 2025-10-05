"""Snapshot der aktuell aktiven Tracking Marker.

Ermittelt für den aktuellen Frame alle Marker (pro Track der zuletzt gültige / sichtbare Marker) und
liefert eine strukturierte Liste zurück.
"""
from __future__ import annotations

import bpy
from dataclasses import dataclass
from typing import List


@dataclass
class MarkerInfo:
    track_name: str
    frame: int
    co_x: float
    co_y: float
    is_keyed: bool
    mute: bool


def collect_active_markers(context: bpy.types.Context) -> List[MarkerInfo]:
    clip = _get_active_clip(context)
    if clip is None:
        return []
    tracking = clip.tracking
    tracks = tracking.tracks
    frame_current = context.scene.frame_current
    result: List[MarkerInfo] = []

    for tr in tracks:
        marker = _get_marker_for_frame(tr, frame_current)
        if marker is None:
            continue
        result.append(
            MarkerInfo(
                track_name=tr.name,
                frame=marker.frame,
                co_x=marker.co[0],
                co_y=marker.co[1],
                is_keyed=marker.is_keyed,
                mute=marker.mute,
            )
        )
    print(f"[Kaiserlich Tracker][SNAPSHOT] {len(result)} aktive Marker auf Frame {frame_current}")
    return result


def _get_active_clip(context: bpy.types.Context):
    space = getattr(context, 'space_data', None)
    if space and space.type == 'CLIP_EDITOR':
        return space.clip
    return None


def _get_marker_for_frame(track: bpy.types.MovieTrackingTrack, frame: int):
    # Exakte Übereinstimmung suchen
    for m in track.markers:
        if m.frame == frame:
            return m
    # Falls nicht vorhanden: den letzten Marker vor dem Frame nehmen (als Proxy für aktuellen Zustand)
    candidate = None
    for m in track.markers:
        if m.frame <= frame:
            if candidate is None or m.frame > candidate.frame:
                candidate = m
    return candidate
