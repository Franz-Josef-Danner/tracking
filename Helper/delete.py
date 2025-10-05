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


