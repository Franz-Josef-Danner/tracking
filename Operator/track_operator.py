import bpy
from ..Helper.bootstrap import run_bootstrap
from ..Helper.frames_limit import resolve_frames_limit


class KAISERLICHTRACKER_OT_track_cycle(bpy.types.Operator):
	"""Minimaler Track-Operator: führt nur Bootstrap aus und gibt den aktuellen Frame aus."""
	bl_idname = "kaiserlich_tracker.track_cycle"
	bl_label = "Track Cycle (Minimal)"
	bl_description = "Führt Bootstrap aus und gibt den aktuellen Playhead-Frame aus."
	bl_options = {"REGISTER", "INTERNAL"}

	def execute(self, context):
		scene = context.scene
		# 1) Bootstrap auslösen
		ef = getattr(scene, 'kaiserlich_markers_per_frame', 25)
		params = run_bootstrap(context, ef)
		if not params:
			self.report({'WARNING'}, "Bootstrap fehlgeschlagen (kein aktiver Clip)")
			return {'CANCELLED'}

		# 2) Playhead Frame erfassen
		pf = scene.frame_current

		# 3) Frames-Limit ermitteln (Scene-Property falls vorhanden)
		limit_prop = getattr(scene, 'kaiserlich_track_frames_limit', None)
		fl = resolve_frames_limit(context, limit_prop)

		# 4) Ausgaben
		print("[Kaiserlich Tracker] ===== Track Operator Minimal =====")
		print(f"[Kaiserlich Tracker] Playhead Frame (pf): {pf}")
		print(f"[Kaiserlich Tracker] Frames-Limit (fl): {fl}")
		self.report({'INFO'}, f"pf={pf} fl={fl}")
		return {'FINISHED'}


__all__ = ["KAISERLICHTRACKER_OT_track_cycle"]
