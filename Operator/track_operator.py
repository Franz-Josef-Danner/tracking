import bpy
from ..Helper.frames_limit import default_frames_limit, resolve_frames_limit


class KAISERLICHTRACKER_OT_track_cycle(bpy.types.Operator):
	"""Trackt selektierte Marker für eine begrenzte Anzahl Frames (Vorwärts).

	Jeder "Zyklus" dieses Operators führt n wiederholte Aufrufe von
	`bpy.ops.clip.track_markers(backwards=False, sequence=False)` aus, wobei n
	durch `frames_limit` bestimmt wird. Zwischen den Schritten wird nicht
	automatisch ein Key gesetzt – das übernimmt die Blender Tracking-Logik.

	Abbruchkriterien:
	  - Kein Clip aktiv
	  - Keine selektierten Tracks
	  - Operator liefert 'CANCELLED'
	  - Fehler beim API-Aufruf
	"""

	bl_idname = "kaiserlich_tracker.track_cycle"
	bl_label = "Track Zyklus"
	bl_description = "Trackt selektierte Marker für eine bestimmte Anzahl Frames vorwärts"
	bl_options = {"REGISTER", "INTERNAL"}

	frames_limit: bpy.props.IntProperty(  # type: ignore
		name="Frames pro Zyklus",
		default=default_frames_limit,
		min=1,
		description="Anzahl der vorwärts zu trackenden Frames in diesem Zyklus"
	)

	def execute(self, context):  # noqa: C901 (überschaubare Komplexität)
		clip = context.space_data.clip if getattr(context, "space_data", None) else None
		if clip is None:
			self.report({'WARNING'}, "Kein Clip aktiv")
			return {'CANCELLED'}

		tracking = getattr(clip, 'tracking', None)
		if tracking is None:
			self.report({'WARNING'}, "Clip hat kein Tracking Objekt")
			return {'CANCELLED'}

		# Selektierte Tracks prüfen
		selected_tracks = [t for t in tracking.tracks if getattr(t, 'select', False)]
		if not selected_tracks:
			self.report({'WARNING'}, "Keine selektierten Tracks")
			return {'CANCELLED'}

		limit = resolve_frames_limit(context, self.frames_limit)
		if limit < 1:
			limit = 1

		print("[Kaiserlich Tracker] ================ Neuer Track Zyklus Start ================")
		print(f"[Kaiserlich Tracker] Selektierte Tracks: {len(selected_tracks)} | Frames-Limit: {limit}")

		frames_tracked = 0
		cancelled = False
		for i in range(limit):
			try:
				res = bpy.ops.clip.track_markers(backwards=False, sequence=False)
			except Exception as e:  # noqa
				print(f"[Kaiserlich Tracker] Tracking Fehler bei Schritt {i+1}: {e}")
				cancelled = True
				break
			if 'CANCELLED' in res:
				print(f"[Kaiserlich Tracker] Blender meldet CANCELLED bei Schritt {i+1} -> Abbruch")
				cancelled = True
				break
			frames_tracked += 1
			print(f"[Kaiserlich Tracker] Schritt {i+1}/{limit} ausgeführt (frames_tracked={frames_tracked})")

		status = "Abgeschlossen" if (not cancelled and frames_tracked == limit) else ("Teilweise" if frames_tracked > 0 else "Abbruch")
		self.report({'INFO'}, f"Track Zyklus: {status} | Getrackte Frames={frames_tracked} / {limit} | Selektierte Tracks={len(selected_tracks)}")
		print("[Kaiserlich Tracker] ================ Track Zyklus Ende ======================")
		return {'FINISHED'} if frames_tracked > 0 else {'CANCELLED'}

