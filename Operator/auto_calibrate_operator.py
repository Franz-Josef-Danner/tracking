import bpy
from typing import List, Dict, Any, Optional
from ..Helper.track_length_helper import get_total_track_length
from ..Helper.playhead_helper import get_start_frame, reset_to_frame
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.delete import delete_tracks_by_names

# Direct import of the procedural tracking function used by the operator
from ..Operator.track_operator import track_cycle


class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
	"""Automatisches Feintuning von Tracking-Thresholds.

	Diese Implementierung kapselt die Logik aus dem ursprünglich
	bereitgestellten Skript in eine kontextbewusste Klasse.  Werte
	werden bevorzugt in Scene-RNA-Properties geschrieben/ gelesen
	(falls vorhanden). Ansonsten werden temporäre Werte in einer
	internen Map verwahrt.
	"""

	bl_idname = "kaiserlich_tracker.auto_calibrate"
	bl_label = "Auto Calibrate"
	bl_options = {"REGISTER", "INTERNAL"}

	def _scene_get(self, context: bpy.types.Context, name: str, default: float = 0.0) -> float:
		scene = context.scene
		# prefer RNA attribute
		if hasattr(scene, name):
			try:
				return float(getattr(scene, name))
			except Exception:
				pass
		# fallback to custom property
		if name in scene.keys():
			try:
				return float(scene[name])
			except Exception:
				pass
		# internal state
		return float(self._state.get(name, default))

	def _scene_set(self, context: bpy.types.Context, name: str, value: float) -> None:
		scene = context.scene
		if hasattr(scene, name):
			try:
				setattr(scene, name, value)
				return
			except Exception:
				pass
		try:
			scene[name] = value
			return
		except Exception:
			pass
		self._state[name] = value

	def run_tracking_cycle(self, context: bpy.types.Context, start_frame: Optional[int] = None) -> int:
		"""Führt Detect + Track-Zyklus aus und liefert die Track-Gesamtlänge.

		Der Playhead wird vor dem Zyklus auf `start_frame` gesetzt. Falls
		`start_frame` None ist, wird der aktuelle Frame verwendet.
		"""
		if start_frame is None:
			start_frame = get_start_frame(context)
		# Reset playhead so each Durchlauf vom selben Frame startet
		reset_to_frame(context, start_frame)

		# Versuch, adaptiven Detect-Operator (falls registriert) auszuführen.
		try:
			if hasattr(bpy.ops.kaiserlich_tracker, 'detect_adapt'):
				bpy.ops.kaiserlich_tracker.detect_adapt()
		except Exception:
			# nicht kritisch, weiter mit Tracking
			pass

		# Track-Zyklus (funktionaler Aufruf) — gibt Operator-Resultat zurück
		try:
			# track_cycle ist die funktionale Implementierung aus track_operator
			track_cycle(context, max_frames=0, verbose=False, report_fn=self.report)
		except Exception:
			# Falls Aufruf fehlschlägt, versuchen wir die Operator-Variante
			try:
				if hasattr(bpy.ops.kaiserlich_tracker, 'track_cycle'):
					bpy.ops.kaiserlich_tracker.track_cycle()
			except Exception:
				pass

		# Länge berechnen (ab start_frame)
		length = get_total_track_length(context, start_frame=start_frame)
		return int(length)

	def _init_state(self) -> None:
		# interne Defaults (übernommen aus dem gelieferten Skript)
		self._state: Dict[str, Any] = {
			'start_value': 1.0,
			'end_gate': 1e-8,
			'target_value': 0.0,
			'step_value': 140.0,
			'min_threshold': 1e-8,
			'threshold_variable': 0.0,
			# placeholder thresholds
			'kaiserlich_rot_thresh_x': 1.0,
			'kaiserlich_scale_thresh_min': 1.0,
			'kaiserlich_scale_thresh_max': 1.0,
			'kaiserlich_rot_scale_thresh_rot': 1.0,
			'kaiserlich_rot_scale_thresh_scale': 1.0,
			'kaiserlich_perspective_thresh': 1.0,
		}

		self.thresh_liste = [
			{"name": "rot_x", "props": ["kaiserlich_rot_thresh_x"]},
			{"name": "scale", "props": ["kaiserlich_scale_thresh_min", "kaiserlich_scale_thresh_max"]},
			{"name": "rot_scale", "props": ["kaiserlich_rot_scale_thresh_rot", "kaiserlich_rot_scale_thresh_scale"]},
			{"name": "perspective", "props": ["kaiserlich_perspective_thresh"]},
		]

		self.thresh_count = len(self.thresh_liste)
		self.current_index = 0

	def _short_test(self, context: bpy.types.Context) -> None:
		# Kurztest: entscheidet, ob Feintuning nötig ist
		while self.current_index < self.thresh_count:
			thresh = self.thresh_liste[self.current_index]
			props = thresh['props']
			self.report({'INFO'}, f"Short-Test für '{thresh['name']}'")

			if len(props) > 1:
				for p in props:
					self._scene_set(context, p, self._state['min_threshold'])
				l1 = self.run_tracking_cycle(context)

				for p in props:
					self._scene_set(context, p, 1.0)
				l2 = self.run_tracking_cycle(context)

				if l2 > l1:
					self._state['target_value'] = l2
					self._state['end_gate'] = self._state['min_threshold']
					self._state['threshold_variable'] = 1.0
					self._state['step_value'] = 140.0
					self.report({'INFO'}, f"Verbesserung bei '{thresh['name']}' -> start Feintuning")
					self._main_test(context)
					return
				else:
					self.current_index += 1
					continue
			else:
				p = props[0]
				self._scene_set(context, p, 1.0)
				l1 = self.run_tracking_cycle(context)
				self._scene_set(context, p, self._state['min_threshold'])
				l2 = self.run_tracking_cycle(context)
				if l2 > l1:
					self._state['target_value'] = l2
					self._state['end_gate'] = self._state['min_threshold']
					self._state['threshold_variable'] = 1.0
					self._state['step_value'] = 140.0
					self.report({'INFO'}, f"Verbesserung gefunden ({l2}) -> Feintuning")
					self._main_test(context)
					return
				else:
					self.current_index += 1
					continue

		# wenn alle fertig
		self.report({'INFO'}, "Alle Threshold-Gruppen fertig getestet.")

	def _main_test(self, context: bpy.types.Context) -> None:
		# Feintuning: iterativer Ansatz, vermeidet tiefe Rekursion
		while self.current_index < self.thresh_count:
			thresh = self.thresh_liste[self.current_index]
			props = thresh['props']

			for prop in props:
				current_value = self._scene_get(context, prop, self._state.get(prop, 1.0))
				# Versuche kleinere Werte
				test_value = current_value / self._state['step_value']
				self._scene_set(context, prop, test_value)
				seg_len = self.run_tracking_cycle(context)

				if seg_len == self._state['target_value']:
					# keine Verbesserung
					self._state['end_gate'] = self._scene_get(context, prop)
					self._scene_set(context, prop, self._state['threshold_variable'])
					self._state['step_value'] /= 2.0
					if self._state['step_value'] >= 1.0:
						continue
					else:
						self.current_index += 1
						break

				elif seg_len > self._state['target_value']:
					# Verbesserung
					self._state['target_value'] = seg_len
					self._state['end_gate'] = self._scene_get(context, prop)
					self._scene_set(context, prop, self._state['threshold_variable'])
					self._state['step_value'] /= 2.0
					if self._state['step_value'] >= 1.0:
						continue
					else:
						self.current_index += 1
						break
				else:
					# schlechteres Ergebnis -> adjust back
					self._scene_set(context, prop, current_value / self._state['step_value'])
					if self._scene_get(context, prop) < self._state['end_gate']:
						self._scene_set(context, prop, self._state['threshold_variable'] / (self._state['step_value'] / 2.0))
					else:
						continue

			# Ende for props: falls wir nicht weiter innerhalb for entschieden haben,
			# erhöhen wir index um sicherzustellen, dass wir Fortschritt machen.
			if all(self._scene_get(context, p) == self._state.get(p) for p in props):
				self.current_index += 1

	def execute(self, context: bpy.types.Context) -> set:
		self._init_state()
		# startrahmen sichern
		start = get_start_frame(context)
		try:
			self._short_test(context)
		finally:
			# playhead zurücksetzen
			reset_to_frame(context, start)
		return {'FINISHED'}
