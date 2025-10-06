import bpy  # type: ignore

from ..Helper.bootstrap import run_bootstrap
from ..Helper.track_forward import track_forward_selected_markers


class KAISERLICHTRACKER_OT_track_cycle(bpy.types.Operator):
	bl_idname = "kaiserlich_tracker.track_cycle"
	bl_label = "Track Cycle"
	bl_description = (
		"Bootstrap -> Vorwärts-Tracking (sequence=True) der selektierten Marker bis Blender stoppt (Ende/Fehler)."
		" GANZ WICHTIG: sequence=True umgesetzt."
	)
	bl_options = {"REGISTER", "INTERNAL"}

	def execute(self, context):  # noqa: C901
		scene = getattr(context, 'scene', None)
		if scene is None:
			self.report({'WARNING'}, "Keine Szene im Kontext")
			return {'CANCELLED'}

		ef = getattr(scene, 'kaiserlich_markers_per_frame', 0) or 0
		params = run_bootstrap(context, ef)
		if not params:
			self.report({'WARNING'}, "Bootstrap fehlgeschlagen")
			return {'CANCELLED'}

		se = params.get('se')
		pf = int(scene.frame_current)
		print(f"[Kaiserlich Tracker] Track Cycle Start: pf={pf} se={se}")

		clip = context.space_data.clip if getattr(context, 'space_data', None) else None
		if clip is None:
			self.report({'WARNING'}, "Kein aktiver Clip")
			return {'CANCELLED'}

	# frames_limit wurde auf Wunsch entfernt – keine Limit-Anpassung mehr

		# Ein einziger Tracking-Call mit sequence=True
		ok = track_forward_selected_markers(context, sequence=True, backwards=False)
		if not ok:
			self.report({'WARNING'}, "Tracking fehlgeschlagen oder abgebrochen")
			return {'CANCELLED'}

		# Nach dem Operator aktuellen Frame erneut auslesen (kann sich bewegt haben)
		pf_after = int(scene.frame_current)
		print(f"[Kaiserlich Tracker] Track Cycle Ende: pf={pf_after} (Start war {pf}) se={se}")
		self.report({'INFO'}, f"Tracking ausgeführt (sequence=True). StartFrame={pf} EndeFrame={pf_after} se={se}")
		return {'FINISHED'}


__all__ = [
	'KAISERLICHTRACKER_OT_track_cycle',
]

