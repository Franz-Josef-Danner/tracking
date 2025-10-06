import bpy
from ..Helper.track_forward import track_forward_selected_markers
from ..Helper.bootstrap import run_bootstrap
from ..Helper.frames_limit import resolve_frames_limit


class KAISERLICHTRACKER_OT_track_cycle(bpy.types.Operator):
	"""Minimaler Tracking-Trigger: EIN einzelner Schritt vorwärts.

	Verwendet track_forward_selected_markers(sequence=False). Keine Bootstrap-/Limit-Logik.
	"""
	bl_idname = "kaiserlich_tracker.track_cycle"
	bl_label = "Track Forward (1 Step)"
	bl_description = "Trackt selektierte Marker um genau 1 Frame vorwärts."
	bl_options = {"REGISTER", "INTERNAL"}

	def execute(self, context):
		ok = track_forward_selected_markers(context, sequence=False, backwards=False)
		if not ok:
			self.report({'WARNING'}, "track_forward fehlgeschlagen oder keine selektierten Marker")
			return {'CANCELLED'}
		self.report({'INFO'}, "1 Frame vorwärts getrackt")
		return {'FINISHED'}


class KAISERLICHTRACKER_OT_track_full_cycle(bpy.types.Operator):
	"""Automatischer Tracking-Zyklus bis zum Szenen-Endframe.

	Ablauf gemäß Anforderung:
	 1) Bootstrap (run_bootstrap)
	 2) Aktuellen Playhead-Frame ausgeben (pf)
	 3) Frames-Limit bestimmen (resolve_frames_limit) – aktuell nur Logging
	 4) Schleife: track_forward (ein Frame) -> neuen pf prüfen -> wenn pf >= se: Ende sonst weiter

	Hinweis: Es wird frameweise (sequence=False) getrackt, damit wir exakt steuern können,
	ob wir das Szenen-Ende (se) erreicht haben. Ein echtes Frames-Limit könnte später
	verwendet werden, um pro Operator-Aufruf nur N Frames zu tracken (Modal-Variante).
	"""
	bl_idname = "kaiserlich_tracker.track_full_cycle"
	bl_label = "Track bis Endframe"
	bl_description = "Bootstrap und dann Frame-weise Tracking bis zum Szenen-Endframe (se)."
	bl_options = {"REGISTER", "INTERNAL"}

	max_frames: bpy.props.IntProperty(  # type: ignore
		name="Max Frames (Sicherheitslimit)",
		default=0,
		min=0,
		soft_max=5000,
		description="0 = kein internes Sicherheitslimit; >0 begrenzt die maximale Anzahl verarbeiteter Frames"
	)

	def execute(self, context):  # noqa: C901 (Ablauf klar und linear, akzeptiert)
		scene = context.scene
		# Versuche UI Property (falls vorhanden), ansonsten Fallback
		ef = getattr(scene, 'kaiserlich_markers_per_frame', 10)
		params = run_bootstrap(context, ef)
		if not params:
			self.report({'WARNING'}, "Bootstrap fehlgeschlagen (kein Clip?)")
			return {'CANCELLED'}

		se = params.get('se')
		if se is None:
			# Fallback auf Scene frame_end falls Bootstrap kein 'se' liefert
			se = getattr(scene, 'frame_end', None)
			if se is None:
				self.report({'WARNING'}, "Kein Szenen-Endframe verfügbar")
				return {'CANCELLED'}

		frames_limit_value = resolve_frames_limit(context)
		print(f"[Kaiserlich Tracker] Frames-Limit (aktuell nur informativ): {frames_limit_value}")

		processed = 0
		start_frame = scene.frame_current
		print(f"[Kaiserlich Tracker] Start pf={start_frame} | Ziel se={se}")

		while True:
			pf = scene.frame_current
			print(f"[Kaiserlich Tracker] Zyklus Frame pf={pf}")
			if pf >= se:
				print("[Kaiserlich Tracker] Endframe erreicht oder überschritten -> Fertig")
				break

			ok = track_forward_selected_markers(context, sequence=True, backwards=False)
			if not ok:
				self.report({'WARNING'}, f"Tracking abgebrochen bei Frame {pf}")
				return {'CANCELLED'}

			processed += 1
			if self.max_frames > 0 and processed >= self.max_frames:
				print(f"[Kaiserlich Tracker] Sicherheitslimit max_frames={self.max_frames} erreicht -> Stop")
				break

		self.report({'INFO'}, f"Tracking fertig: Start={start_frame} Ende={scene.frame_current} (se={se}) Schritte={processed}")
		return {'FINISHED'}

__all__ = [
	"KAISERLICHTRACKER_OT_track_cycle",
	"KAISERLICHTRACKER_OT_track_full_cycle",
]
