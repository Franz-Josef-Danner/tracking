import bpy
from ..Helper.bootstrap import run_bootstrap
from ..Helper.frames_limit import resolve_frames_limit, default_frames_limit
from ..Helper.track_forward import track_forward_selected_markers


class KAISERLICHTRACKER_OT_track_cycle(bpy.types.Operator):
	bl_idname = "kaiserlich_tracker.track_cycle"
	bl_label = "Track Zyklus"
	bl_description = "Bootstrap -> Frames-Limit -> solange nicht am Endframe: forward track (frameweise)"
	bl_options = {"REGISTER", "INTERNAL"}

	frames_limit: bpy.props.IntProperty(  # type: ignore
		name="Frames pro Zyklus",
		default=default_frames_limit,
		min=1,
		description="Max Frames die in diesem Aufruf getrackt werden (oder bis Endframe erreicht)"
	)

	def execute(self, context):
		# 1) Bootstrap auslösen
		scene = context.scene if getattr(context, 'scene', None) else None
		ef = getattr(scene, 'kaiserlich_markers_per_frame', 0) if scene else 0
		params = run_bootstrap(context, ef)
		if not params:
			self.report({'WARNING'}, "Bootstrap fehlgeschlagen")
			return {'CANCELLED'}
		se = params.get('se')  # Szenen-Endframe (kann None sein)

		# 2) Frames-Limit bestimmen
		limit = resolve_frames_limit(context, self.frames_limit)
		if limit < 1:
			limit = 1

		clip = context.space_data.clip if getattr(context, 'space_data', None) else None
		if clip is None:
			self.report({'WARNING'}, "Kein Clip aktiv")
			return {'CANCELLED'}
		tracking = getattr(clip, 'tracking', None)
		if tracking is None:
			self.report({'WARNING'}, "Kein Tracking Objekt")
			return {'CANCELLED'}

		selected = [t for t in tracking.tracks if getattr(t, 'select', False)]
		if not selected:
			self.report({'WARNING'}, "Keine selektierten Marker")
			return {'CANCELLED'}

		print("[Kaiserlich Tracker] ===== Track Cycle Start =====")
		print(f"[Kaiserlich Tracker] Start-Frame={context.scene.frame_current} Endframe(se)={se} limit={limit} selected={len(selected)}")

		frames_done = 0
		finished = False
		for _ in range(limit):  # Zyklus
			pf = context.scene.frame_current
			if se is not None and pf >= se:
				finished = True
				print(f"[Kaiserlich Tracker] Endframe erreicht (pf={pf} >= se={se})")
				break
			# 3) Forward Track (ein Frame Schritt sequence=False damit Limit greift)
			ok = track_forward_selected_markers(context, sequence=False, backwards=False)
			if not ok:
				print("[Kaiserlich Tracker] Tracking Schritt fehlgeschlagen oder CANCELLED")
				break
			frames_done += 1
			print(f"[Kaiserlich Tracker] Frame-Schritt abgeschlossen (frames_done={frames_done})")

		status = "Fertig (Endframe)" if finished else ("Limit erreicht" if frames_done == limit else "Abbruch/Fehler")
		self.report({'INFO'}, f"Track Cycle: {status} | Schritte={frames_done} | Aktueller Frame={context.scene.frame_current}")
		print("[Kaiserlich Tracker] ===== Track Cycle Ende =====")
		return {'FINISHED'} if frames_done > 0 or finished else {'CANCELLED'}

