import bpy

"""Hilfsfunktionen zum Löschen einzelner Marker auf einem Frame.

Blender API Referenz:
  MovieTrackingMarkers.delete_frame(frame)
	-> Löscht (falls vorhanden) den Marker eines Tracks auf dem angegebenen Frame.

Dieses Modul kapselt die Aufrufe und liefert Logging + Statistiken.
"""

def _log(msg: str):
	print(f'[delete] {msg}')

def delete_marker_on_track(track, frame: int) -> bool:
	"""Löscht den Marker eines einzelnen Tracks auf "frame".

	Rückgabe:
	  True  -> Marker existierte und wurde gelöscht
	  False -> Kein Marker vorhanden oder Fehler
	"""
	if track is None:
		return False
	try:
		# Vorab prüfen ob ein Marker auf dem Frame existiert (beschleunigt Logging)
		has_marker = any(m.frame == frame for m in track.markers)
		if not has_marker:
			return False
		track.markers.delete_frame(frame)
		return True
	except Exception as e:
		_log(f'Fehler beim Löschen in Track {getattr(track, "name", "?")}: {e}')
		return False

def delete_markers_at_frame(frame: int, tracks=None, selected_only: bool = False) -> int:
	"""Löscht Marker auf angegebenem Frame für alle übergebenen oder (falls None) alle Tracks.

	Parameter:
	  frame (int)            – Frame auf dem gelöscht werden soll
	  tracks (Iterable|None) – Explizite Track-Liste; wenn None werden alle Tracks des aktiven Clips genommen
	  selected_only (bool)   – Nur selektierte Tracks berücksichtigen (nur wenn tracks=None)

	Rückgabe:
	  Anzahl der tatsächlich gelöschten Marker.
	"""
	clip = bpy.context.edit_movieclip
	if not clip:
		_log('Kein aktiver Clip – Abbruch')
		return 0
	if tracks is None:
		all_tracks = list(clip.tracking.tracks)
		if selected_only:
			tracks = [t for t in all_tracks if getattr(t, 'select', False)]
		else:
			tracks = all_tracks
	deleted = 0
	for t in tracks:
		if delete_marker_on_track(t, frame):
			_log(f'Marker in {t.name} auf Frame {frame} gelöscht')
			deleted += 1
	_log(f'Gesamt gelöschte Marker auf Frame {frame}: {deleted}')
	return deleted

def run(context, frame: int = None, selected_only: bool = False) -> int:
	"""Convenience Entry (vereinheitlicht mit anderen Helper.* Modulen).

	Parameter:
	  frame (int|None) – Frame; None => aktueller Szenenframe
	  selected_only    – Nur selektierte Tracks berücksichtigen

	Rückgabe:
	  Anzahl gelöschter Marker.
	"""
	if frame is None:
		try:
			frame = context.scene.frame_current
		except Exception:
			frame = bpy.context.scene.frame_current
	return delete_markers_at_frame(frame, tracks=None, selected_only=selected_only)

# -------------------------------------------------------------
# Erweiterungen: gezieltes Löschen nach Track-Namen oder Index
# -------------------------------------------------------------

def _resolve_tracks_by_names(clip, names):
	name_map = {t.name: t for t in clip.tracking.tracks}
	resolved = []
	for n in names:
		t = name_map.get(n)
		if t:
			resolved.append(t)
		else:
			_log(f'Name nicht gefunden: {n}')
	return resolved

def _resolve_track_by_index(clip, index: int):
	try:
		return clip.tracking.tracks[index]
	except Exception:
		_log(f'Index ausserhalb Bereich: {index}')
		return None

def delete_marker_by_track_name(frame: int, track_name: str) -> bool:
	"""Löscht Marker auf Frame für angegebenen Track-Namen."""
	clip = bpy.context.edit_movieclip
	if not clip:
		_log('Kein aktiver Clip')
		return False
	tracks = _resolve_tracks_by_names(clip, [track_name])
	if not tracks:
		return False
	return delete_marker_on_track(tracks[0], frame)

def delete_marker_by_track_index(frame: int, index: int) -> bool:
	"""Löscht Marker auf Frame anhand des Track-Index (Collection Index)."""
	clip = bpy.context.edit_movieclip
	if not clip:
		_log('Kein aktiver Clip')
		return False
	t = _resolve_track_by_index(clip, index)
	if not t:
		return False
	return delete_marker_on_track(t, frame)

def delete_markers_by_names(frame: int, names) -> int:
	"""Löscht Marker auf Frame für alle angegebenen Track-Namen."""
	clip = bpy.context.edit_movieclip
	if not clip:
		_log('Kein aktiver Clip')
		return 0
	tracks = _resolve_tracks_by_names(clip, names)
	return delete_markers_at_frame(frame, tracks=tracks)

def delete_tracks_by_names(names) -> int:
	"""Entfernt komplette Tracks (nicht nur Marker) anhand von Namen.

	Rückgabe: Anzahl tatsächlich entfernter Tracks.
	"""
	clip = bpy.context.edit_movieclip
	if not clip:
		_log('Kein aktiver Clip')
		return 0
	before = list(clip.tracking.tracks)
	name_set = set(names)
	removed = 0
	# Kopie, weil wir die Collection mutieren
	for t in before:
		if t.name in name_set:
			try:
				clip.tracking.tracks.remove(t)
				removed += 1
				_log(f'Track entfernt: {t.name}')
			except Exception as e:
				_log(f'Fehler beim Entfernen Track {t.name}: {e}')
	_log(f'Entfernte Tracks: {removed}')
	return removed

def delete_track_by_index(index: int) -> bool:
	"""Entfernt einen Track per Collection-Index."""
	clip = bpy.context.edit_movieclip
	if not clip:
		_log('Kein aktiver Clip')
		return False
	t = _resolve_track_by_index(clip, index)
	if not t:
		return False
	try:
		nm = t.name
		clip.tracking.tracks.remove(t)
		_log(f'Track entfernt (Index {index}): {nm}')
		return True
	except Exception as e:
		_log(f'Fehler beim Entfernen Index {index}: {e}')
		return False

def delete(frame: int = None, names=None, indices=None, markers_only=True) -> dict:
	"""High-Level API für gezieltes Löschen.

	Parameter:
	  frame (int|None)  – Frame für Marker-Löschung (None => aktueller Frame)
	  names (Iterable)  – Track-Namen
	  indices (Iterable)– Track-Indizes
	  markers_only (bool) – True: nur Marker auf Frame löschen, False: ganze Tracks löschen

	Rückgabe:
	  dict mit Keys: markers_deleted, tracks_deleted
	"""
	clip = bpy.context.edit_movieclip
	if not clip:
		_log('Kein aktiver Clip')
		return {'markers_deleted': 0, 'tracks_deleted': 0}
	if frame is None:
		frame = bpy.context.scene.frame_current
	names = list(names) if names else []
	indices = list(indices) if indices else []

	markers_deleted = 0
	tracks_deleted = 0

	if markers_only:
		if names:
			markers_deleted += delete_markers_by_names(frame, names)
		for idx in indices:
			if delete_marker_by_track_index(frame, idx):
				markers_deleted += 1
	else:
		if names:
			tracks_deleted += delete_tracks_by_names(names)
		for idx in indices:
			if delete_track_by_index(idx):
				tracks_deleted += 1

	summary = {'markers_deleted': markers_deleted, 'tracks_deleted': tracks_deleted}
	_log(f'Summary: {summary}')
	return summary


