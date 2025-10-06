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
	"KAISERLICHTRACKER_OT_track_until_end",
]


class KAISERLICHTRACKER_OT_track_until_end(bpy.types.Operator):
	"""Trackt automatisch Frame für Frame (Limit=1) bis zum Szenen-Ende.

	Funktionsweise:
	  * Setzt einmal zu Beginn Frames-Limit=1 (Settings + selektierte Tracks)
	  * Nutzt sequence=True -> jeder Aufruf liefert exakt 1 Frame Fortschritt pro Track
	  * Wiederholt Aufruf im Modal-Loop (Timer) bis frame_current >= frame_end
	Abbruch: ESC oder Rechtsklick.
	"""
	bl_idname = "kaiserlich_tracker.track_until_end"
	bl_label = "Track bis Szenen-Ende"
	bl_description = "Automatisches Tracking (1 Frame pro Aufruf) bis frame_end erreicht ist."
	bl_options = {"REGISTER", "INTERNAL"}

	use_bootstrap: bpy.props.BoolProperty(  # type: ignore
		name="Bootstrap vorab",
		default=False,
		description="Vor Start einmal Bootstrap ausführen"
	)
	interval: bpy.props.FloatProperty(  # type: ignore
		name="Intervall (s)",
		default=0.0,
		min=0.0,
		soft_max=1.0,
		description="Zeit zwischen Tracking-Schritten (0 = so schnell wie möglich)"
	)
	safety_max_frames: bpy.props.IntProperty(  # type: ignore
		name="Sicherheitslimit",
		default=0,
		min=0,
		soft_max=25000,
		description="0 = kein Limit; >0 maximale Anzahl Tracking-Aufrufe"
	)

	_timer = None
	_start_frame = 0
	_end_frame = 0
	_processed = 0

	def _do_step(self, context):
		scene = context.scene
		if scene.frame_current >= self._end_frame:
			return 'DONE'
		ok = track_forward_selected_markers(context, sequence=True, backwards=False)
		if not ok:
			return 'FAIL'
		# Sicherheits-Fallback: falls Frame nicht weitergerückt ist -> erhöhen
		if scene.frame_current < self._end_frame:
			# Manche Blender Builds erhöhen frame_current nicht automatisch
			# wenn nur ein Frame Fortschritt gemacht wurde.
			# Wir akzeptieren das nur, wenn keine Änderung stattfand.
			# (Keine exakte Vorher/Nachher Kontrolle hier – optional erweiterbar)
			pass
		self._processed += 1
		if self.safety_max_frames > 0 and self._processed >= self.safety_max_frames:
			return 'SAFETY'
		return 'STEP'

	def modal(self, context, event):
		if event.type in {'ESC', 'RIGHTMOUSE'}:
			self._finish(context, cancelled=True, reason="Abbruch durch Benutzer")
			return {'CANCELLED'}
		if event.type == 'TIMER':
			result = self._do_step(context)
			if result == 'DONE':
				self._finish(context, cancelled=False, reason="Szenen-Ende erreicht")
				return {'FINISHED'}
			if result == 'FAIL':
				self._finish(context, cancelled=True, reason="Tracking fehlgeschlagen")
				return {'CANCELLED'}
			if result == 'SAFETY':
				self._finish(context, cancelled=False, reason="Sicherheitslimit erreicht")
				return {'FINISHED'}
		return {'RUNNING_MODAL'}

	def _finish(self, context, cancelled: bool, reason: str):
		wm = context.window_manager
		if self._timer:
			try:
				wm.event_timer_remove(self._timer)
			except Exception:
				pass
		status = 'CANCELLED' if cancelled else 'FINISHED'
		msg = f"Track Until End {status}: Start={self._start_frame} Ende={context.scene.frame_current} Schritte={self._processed} | {reason}"
		print(f"[Kaiserlich Tracker] {msg}")
		if cancelled:
			self.report({'WARNING'}, msg)
		else:
			self.report({'INFO'}, msg)

	def invoke(self, context, event):  # noqa
		clip = context.space_data.clip if getattr(context, 'space_data', None) else None
		if not clip:
			self.report({'WARNING'}, "Kein Clip aktiv")
			return {'CANCELLED'}
		scene = context.scene
		if self.use_bootstrap:
			ef = getattr(scene, 'kaiserlich_markers_per_frame', 10)
			params = run_bootstrap(context, ef)
			if not params:
				self.report({'WARNING'}, "Bootstrap fehlgeschlagen")
				return {'CANCELLED'}
			self._end_frame = params.get('se') or scene.frame_end
		else:
			self._end_frame = scene.frame_end

		set_one_frame_limit(clip, only_selected=True)
		self._start_frame = scene.frame_current
		self._processed = 0
		wm = context.window_manager
		self._timer = wm.event_timer_add(self.interval, window=context.window)
		wm.modal_handler_add(self)
		print(f"[Kaiserlich Tracker] Track Until End Start: pf={self._start_frame} -> se={self._end_frame}")
		return {'RUNNING_MODAL'}
