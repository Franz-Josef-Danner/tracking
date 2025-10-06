import bpy
from ..Helper.track_forward import track_forward_selected_markers


class KAISERLICHTRACKER_OT_track_cycle(bpy.types.Operator):
	"""Minimaler Tracking-Trigger: Ruft ausschließlich den Helper track_forward auf.

	Keine Bootstrap-, Limit-, Frame- oder Endframe-Logik hier. Genau EIN Aufruf
	von track_forward_selected_markers(sequence=False, backwards=False). Alles
	Weitere (Kontext, Selektion, tatsächliches Tracking-Verhalten) liegt beim Helper.
	"""
	bl_idname = "kaiserlich_tracker.track_cycle"
	bl_label = "Track Forward (1 Step)"
	bl_description = "Löst nur den Helper track_forward_selected_markers aus (kein Loop)."
	bl_options = {"REGISTER", "INTERNAL"}

	def execute(self, context):
		ok = track_forward_selected_markers()
		if not ok:
			self.report({'WARNING'}, "track_forward fehlgeschlagen oder keine selektierten Marker")
			return {'CANCELLED'}
		self.report({'INFO'}, "track_forward ausgeführt (1 Step)")
		return {'FINISHED'}


__all__ = ["KAISERLICHTRACKER_OT_track_cycle"]
