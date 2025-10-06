import bpy
from ..Helper.bootstrap import run_bootstrap


class KAISERLICHTRACKER_OT_track_cycle(bpy.types.Operator):
	"""Minimaler Track-Operator: führt nur Bootstrap aus und gibt den aktuellen Frame aus."""
	bl_idname = "kaiserlich_tracker.track_cycle"
	bl_label = "Track Cycle (Minimal)"
	bl_description = "Führt Bootstrap aus und gibt den aktuellen Playhead-Frame aus."
	bl_options = {"REGISTER", "INTERNAL"}

	def execute(self, context):
		scene = context.scene
		ef = getattr(scene, 'kaiserlich_markers_per_frame', 25)
		params = run_bootstrap(context, ef)
		if not params:
			self.report({'WARNING'}, "Bootstrap fehlgeschlagen (kein aktiver Clip)")
			return {'CANCELLED'}
		frame = scene.frame_current
		print(f"[Kaiserlich Tracker] Playhead Frame: {frame}")
		self.report({'INFO'}, f"Playhead Frame: {frame}")
		return {'FINISHED'}


__all__ = ["KAISERLICHTRACKER_OT_track_cycle"]
