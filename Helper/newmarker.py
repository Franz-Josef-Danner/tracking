"""Anlegen neuer Tracking Marker (Platzhalter-Strategie)."""
from __future__ import annotations

import bpy
from math import floor


def create_new_markers(context: bpy.types.Context, desired: int):
	"""Legt bis zu 'desired' neue Marker gleichmäßig über das Bild verteilt an.

	Dies ist ein einfacher Platzhalter: echte Strategien würden Textur-Kontraste
	oder vorhandene Marker berücksichtigen.
	"""
	clip = _get_active_clip(context)
	if clip is None:
		print("[Kaiserlich Tracker][NEWMARKER] Kein aktiver Clip")
		return 0
	tracking = clip.tracking
	width, height = clip.size

	rows = int(floor(desired ** 0.5)) or 1
	cols = max(1, desired // rows)
	count = 0
	frame_current = context.scene.frame_current

	for r in range(rows):
		if count >= desired:
			break
		for c in range(cols):
			if count >= desired:
				break
			# Normalisierte Koordinaten (0..1)
			nx = (c + 0.5) / cols
			ny = (r + 0.5) / rows
			track = tracking.tracks.new(name=f"auto_{frame_current}_{count}", frame=frame_current)
			track.markers[0].co[0] = nx
			track.markers[0].co[1] = ny
			count += 1

	print(f"[Kaiserlich Tracker][NEWMARKER] {count} Marker angelegt (desired={desired})")
	return count


def _get_active_clip(context):
	space = getattr(context, 'space_data', None)
	if space and space.type == 'CLIP_EDITOR':
		return space.clip
	return None
