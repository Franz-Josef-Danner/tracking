import bpy
from ..Helper.track_forward import track_forward_selected_markers
from ..Helper.bootstrap import run_bootstrap
from ..Helper.frames_limit import set_one_frame_limit


class KAISERLICHTRACKER_OT_track_cycle(bpy.types.Operator):
	"""Trackt automatisch EINEN Frame NACH DEM ANDEREN bis Szenen-Ende (hartes Limit=1 pro Track).

	Ablauf bei EINEM Aufruf:
	 1) (Optional) Bootstrap
	 2) Setzt Frame-Limit=1 (Settings + selektierte Tracks)
	 3) Interner Loop: wiederholte Aufrufe des Blender Tracking Operators (sequence=True)
	    Jeder Aufruf bringt jeden Track genau 1 Frame weiter (wegen Limit=1)
	 4) Stop wenn scene.frame_current >= scene.frame_end oder Tracking scheitert.

	Keine zusätzlichen Buttons, kein Modal – EIN Aufruf erledigt kompletten Fortschritt.
	"""
	bl_idname = "kaiserlich_tracker.track_cycle"
	bl_label = "Track bis Szenen-Ende"
	bl_description = "Automatisches Tracking: 1 Frame Schritte bis Endframe (Limit=1)."
	bl_options = {"REGISTER", "INTERNAL"}

	use_bootstrap: bpy.props.BoolProperty(  # type: ignore
		name="Bootstrap vorab",
		default=False,
		description="Vor Start einmal Bootstrap ausführen"
	)
	max_internal_calls: bpy.props.IntProperty(  # type: ignore
		name="Sicherheitslimit Calls",
		default=0,
		min=0,
		soft_max=25000,
		description="0 = kein Limit; >0 maximale Anzahl interner Tracking-Aufrufe (Schutz gegen Hänger)"
	)

	def execute(self, context):  # noqa: C901
		scene = context.scene
		clip = context.space_data.clip if getattr(context, 'space_data', None) else None
		if not clip:
			self.report({'WARNING'}, "Kein Clip aktiv")
			return {'CANCELLED'}

		if self.use_bootstrap:
			ef = getattr(scene, 'kaiserlich_markers_per_frame', 10)
			params = run_bootstrap(context, ef)
			if not params:
				self.report({'WARNING'}, "Bootstrap fehlgeschlagen")
				return {'CANCELLED'}
			end_frame = params.get('se') or scene.frame_end
		else:
			end_frame = scene.frame_end

		changed = set_one_frame_limit(clip, only_selected=True)
		print(f"[Kaiserlich Tracker] Frame-Limit=1 gesetzt (geändert: {changed}) -> Start Loop pf={scene.frame_current} se={end_frame}")

		calls = 0
		start_frame = scene.frame_current
		last_frame = start_frame - 1
		while scene.frame_current < end_frame:
			ok = track_forward_selected_markers(context, sequence=True, backwards=False)
			if not ok:
				print("[Kaiserlich Tracker] Tracking abgebrochen / Fehler")
				break
			calls += 1
			# Fortschritt prüfen
			if scene.frame_current == last_frame:  # Kein Fortschritt -> Notbremse
				print("[Kaiserlich Tracker] Kein Frame-Fortschritt erkannt -> Abbruch")
				break
			last_frame = scene.frame_current
			if self.max_internal_calls > 0 and calls >= self.max_internal_calls:
				print(f"[Kaiserlich Tracker] Sicherheitslimit erreicht (calls={calls})")
				break

		status = "vollständig" if scene.frame_current >= end_frame else "vorzeitig beendet"
		self.report({'INFO'}, f"Tracking {status}: Start={start_frame} Ende={scene.frame_current} Calls={calls}")
		return {'FINISHED'}

__all__ = [
	"KAISERLICHTRACKER_OT_track_cycle",
]
