import bpy
from ..Helper.bootstrap import run_bootstrap
from ..Helper.frames_limit import resolve_frames_limit, default_frames_limit
from ..Helper.track_forward import track_forward_selected_markers


class KAISERLICHTRACKER_OT_track_cycle(bpy.types.Operator):
	bl_idname = "kaiserlich_tracker.track_cycle"
	bl_label = "Track Zyklus"
	bl_description = "Bootstrap -> Frames-Limit aufrufen -> frameweise tracken bis pf >= se (Ende)."
	bl_options = {"REGISTER", "INTERNAL"}

	def execute(self, context):
		# 1) Bootstrap auslösen
		scene = context.scene if getattr(context, 'scene', None) else None
		ef = getattr(scene, 'kaiserlich_markers_per_frame', 0) if scene else 0
		params = run_bootstrap(context, ef)
		if not params:
			self.report({'WARNING'}, "Bootstrap fehlgeschlagen")
			return {'CANCELLED'}
		se = params.get('se')  # Szenen-Endframe (kann None sein)

		# 2) Frames-Limit bestimmen (aus Scene-Property statt Operator-Property)
		scene_limit = getattr(scene, 'kaiserlich_track_frames_limit', default_frames_limit) if scene else default_frames_limit
		limit = resolve_frames_limit(context, scene_limit)
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
		print(f"[Kaiserlich Tracker] Start-Frame={context.scene.frame_current} Endframe(se)={se} selected={len(selected)} (frames_limit aufgerufen={limit})")

		frames_done = 0
		while True:  # cycle start
			pf = context.scene.frame_current
			print(f"[Kaiserlich Tracker] cycle start (pf={pf})")
			if se is not None and pf >= se:  # pf >= se => fertig
				print(f"[Kaiserlich Tracker] Endframe erreicht (pf={pf} >= se={se}) -> finished")
				break
			# auslösen -> helper/track_forward.py
			ok = track_forward_selected_markers(context, sequence=False, backwards=False)
			if not ok:
				print("[Kaiserlich Tracker] Tracking Schritt fehlgeschlagen oder CANCELLED -> Abbruch")
				break
			frames_done += 1
			# nächster cycle start automatisch durch Schleife

		status = "Fertig (Endframe)" if (se is not None and context.scene.frame_current >= se) else ("Abbruch/Fehler" if frames_done == 0 else "Abbruch vor Endframe")
		self.report({'INFO'}, f"Track Cycle: {status} | Schritte={frames_done} | Aktueller Frame={context.scene.frame_current}")
		print("[Kaiserlich Tracker] ===== Track Cycle Ende =====")
		return {'FINISHED'} if frames_done > 0 else {'CANCELLED'}

