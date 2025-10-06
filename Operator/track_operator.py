import bpy
from ..Helper.track_forward import track_forward_selected_markers
from ..Helper.bootstrap import run_bootstrap
from ..Helper.frames_limit import set_one_frame_limit


class KAISERLICHTRACKER_OT_track_cycle(bpy.types.Operator):
	"""Setzt Frames-Limit=1 auf Settings & selektierte Tracks und trackt dann vorwärts (sequence=True).

	Durch das Limit stoppt jeder Track nach genau einem Frame Fortschritt; erneuter Aufruf
	verarbeitet den nächsten Frame. Damit ist das Verhalten deterministisch ohne eigene Schleife.
	"""
	bl_idname = "kaiserlich_tracker.track_cycle"
	bl_label = "Track 1 Frame (Limit)"
	bl_description = "Setzt Frames-Limit=1 und trackt (sequence=True) genau einen Frame pro Track."
	bl_options = {"REGISTER", "INTERNAL"}

	use_bootstrap: bpy.props.BoolProperty(  # type: ignore
		name="Bootstrap vorab",
		default=False,
		description="Vor dem Tracking einmal Bootstrap ausführen (Markergrößen etc.)"
	)

	def execute(self, context):
		clip = context.space_data.clip if getattr(context, 'space_data', None) else None
		if not clip:
			self.report({'WARNING'}, "Kein Clip aktiv")
			return {'CANCELLED'}

		if self.use_bootstrap:
			ef = getattr(context.scene, 'kaiserlich_markers_per_frame', 10)
			params = run_bootstrap(context, ef)
			if not params:
				self.report({'WARNING'}, "Bootstrap fehlgeschlagen")
				return {'CANCELLED'}

		changed = set_one_frame_limit(clip, only_selected=True)
		print(f"[Kaiserlich Tracker] Frame-Limit gesetzt für {changed} Elemente")

		ok = track_forward_selected_markers(context, sequence=True, backwards=False)
		if not ok:
			self.report({'WARNING'}, "Tracking fehlgeschlagen oder keine selektierten Marker")
			return {'CANCELLED'}

		self.report({'INFO'}, "Ein Frame pro Track verarbeitet (Frames-Limit=1)")
		return {'FINISHED'}

__all__ = [
	"KAISERLICHTRACKER_OT_track_cycle",
]
