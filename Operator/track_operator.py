import bpy
from ..Helper.track_forward import track_forward_selected_markers
from ..Helper.bootstrap import run_bootstrap
from ..Helper.frames_limit import resolve_frames_limit


class KAISERLICHTRACKER_OT_track_cycle(bpy.types.Operator):
	"""Tracking über die gesamte Sequenz (ein Blender Operator-Aufruf).

	Verwendet track_forward_selected_markers(sequence=True). Keine Bootstrap-/Limit-Logik.
	"""
	bl_idname = "kaiserlich_tracker.track_cycle"
	bl_label = "Track Forward (Sequence)"
	bl_description = "Trackt selektierte Marker vorwärts durch die gesamte Sequenz (sequence=True)."
	bl_options = {"REGISTER", "INTERNAL"}

	def execute(self, context):
		ok = track_forward_selected_markers(context, sequence=True, backwards=False)
		if not ok:
			self.report({'WARNING'}, "Tracking fehlgeschlagen oder keine selektierten Marker")
			return {'CANCELLED'}
		self.report({'INFO'}, "Vorwärts-Tracking (Sequenz) abgeschlossen")
		return {'FINISHED'}


class KAISERLICHTRACKER_OT_track_full_cycle(bpy.types.Operator):
	"""Bootstrap + vollständiges Sequenz-Tracking (ein Aufruf, sequence=True).

	Bootstrap dient der Parametrierung (Markergrößen etc.). Danach wird direkt
	der Blender Operator über den Helper mit sequence=True gestartet.
	"""
	bl_idname = "kaiserlich_tracker.track_full_cycle"
	bl_label = "Bootstrap + Track Sequence"
	bl_description = "Führt Bootstrap aus und trackt dann selektierte Marker durch die ganze Sequenz."
	bl_options = {"REGISTER", "INTERNAL"}

	def execute(self, context):
		scene = context.scene
		ef = getattr(scene, 'kaiserlich_markers_per_frame', 10)
		params = run_bootstrap(context, ef)
		if not params:
			self.report({'WARNING'}, "Bootstrap fehlgeschlagen (kein Clip?)")
			return {'CANCELLED'}

		_ = resolve_frames_limit(context)  # aktuell rein informativ – ggf. später nutzen
		start_frame = scene.frame_current
		if not track_forward_selected_markers(context, sequence=True, backwards=False):
			self.report({'WARNING'}, "Tracking fehlgeschlagen oder keine selektierten Marker")
			return {'CANCELLED'}
		self.report({'INFO'}, f"Sequenz-Tracking abgeschlossen (Start={start_frame} Ende={scene.frame_current})")
		return {'FINISHED'}

__all__ = [
	"KAISERLICHTRACKER_OT_track_cycle",
	"KAISERLICHTRACKER_OT_track_full_cycle",
]
