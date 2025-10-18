import bpy
from typing import List, Dict, Any, Optional
from ..Helper.track_length_helper import get_total_track_length
from ..Helper.playhead_helper import get_start_frame, reset_to_frame
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.delete import delete_tracks_by_names
from ..Helper.reset_helper import reset_all_thresholds, THRESH_LIST, set_scene_value, get_scene_value

# Direct import of the procedural tracking function used by the operator
from .track_operator import track_cycle as run_track_cycle
from .detect_adapt_operator import KAISERLICHTRACKER_OT_detect_adapt


def run_tracking_cycle(context) -> int:
	"""Hilfswrapper: führt den Track-Cycle aus und liefert die Gesamtlänge zurück.

	Wichtig: erwartet, dass vor Aufruf die gewünschten Scene-Properties gesetzt
	wurden (Thresholds). Start-Frame wird gemerkt und am Ende zurückgesetzt.
	"""
	start = get_start_frame(context)
	clip = getattr(context.space_data, "clip", None)
	print(f"[AutoCal] run_tracking_cycle: start_frame={start}, clip_present={bool(clip)}")
	if clip is None:
		print("[AutoCal] Kein aktiver Clip - Tracklauf wird übersprungen.")
		return 0

	tracking = getattr(clip, 'tracking', None)
	if tracking is None:
		print("[AutoCal] Clip hat kein Tracking-Objekt - Länge=0")
		return 0

	selected_tracks = [t.name for t in tracking.tracks if getattr(t, 'select', False)]
	print(f"[AutoCal] selektierte Tracks vor Tracklauf: {selected_tracks}")

	# Fallback: wenn keine Tracks selektiert sind, selektiere konservativ alle sichtbaren (nicht gemuteten) Tracks
	if not selected_tracks:
		available = [t for t in tracking.tracks if not getattr(t, 'mute', False)]
		if available:
			for t in tracking.tracks:
				try:
					t.select = False
				except Exception:
					pass
			for t in available:
				try:
					t.select = True
				except Exception:
					pass
			selected_tracks = [t.name for t in available]
			print(f"[AutoCal] Keine Tracks selektiert — Fallback: selektiere alle {len(available)} verfügbaren Tracks: {selected_tracks}")
		else:
			print("[AutoCal] Keine verfügbaren Tracks im Tracking-Objekt.")

	try:
		res = run_track_cycle(context, max_frames=0, verbose=False)
	except Exception as e:
		print(f"[AutoCal] Exception in track_cycle: {e}")
		res = {'CANCELLED'}

	print(f"[AutoCal] track_cycle returned: {res}")

	# Reset des Playheads
	reset_to_frame(context, start)

	# Berechne Länge
	length = get_total_track_length(context, start_frame=start)
	print(f"[AutoCal] berechnete Gesamtlänge: {length}")
	return length


def save_result(context, prop: str, value: float):
	"""Speichert das finale Ergebnis in der Scene unter einem klaren Namen.

	Beispiel: kaiserlich_opt_kaiserlich_scale_thresh_min
	"""
	scene = context.scene
	key = f"kaiserlich_opt_{prop}"
	try:
		setattr(scene, key, float(value))
	except Exception:
		pass


class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
	bl_idname = "kaiserlich_tracker.auto_calibrate"
	bl_label = "Auto Calibrate Thresholds"
	bl_description = "Automatische Kalibrierung der Threshold-Parameter mit Reset nach jedem Lauf"
	bl_options = {"REGISTER", "INTERNAL"}

	def execute(self, context):
		# Minimaler Testwert (aus UI oder Konvention)
		min_threshold = getattr(context.scene, "kaiserlich_scale_thresh_min", 0.002)

		# Short test: iteriere über Gruppen
		self._short_test(context, min_threshold)

		# Nach kompletter Kalibrierung: setze finale Werte aus gespeicherten Resultaten
		# (In dieser Implementierung sind save_result-Aufrufe in _main_test)
		self.report({"INFO"}, "Auto-Calibrate abgeschlossen.")
		return {"FINISHED"}

	def _short_test(self, context, min_threshold: float):
		current_index = 0
		# Wir arbeiten mit der globalen THRESH_LIST aus reset_helper
		while current_index < len(THRESH_LIST):
			thresh = THRESH_LIST[current_index]
			props = thresh["props"]

			# Szenario A: Doppelwerte (Länge 2)
			if len(props) == 2:
				pA, pB = props

				# Beide minimal → Baseline
				set_scene_value(context, pA, min_threshold)
				set_scene_value(context, pB, min_threshold)
				len_min = run_tracking_cycle(context)
				reset_all_thresholds(context, [pA, pB])

				# Beide maximal → Vergleich
				set_scene_value(context, pA, 1.0)
				set_scene_value(context, pB, 1.0)
				len_max = run_tracking_cycle(context)
				reset_all_thresholds(context, [pA, pB])

				if len_max > len_min:
					# Positiv reagierende Gruppe -> Teste beide einzeln
					# Test 1: pA aktiv, pB fixiert
					set_scene_value(context, pB, min_threshold)
					self._main_test(context, active_prop=pA, locked_prop=pB)
					reset_all_thresholds(context, [pA, pB])

					# Test 2: pB aktiv, pA fixiert
					set_scene_value(context, pA, min_threshold)
					self._main_test(context, active_prop=pB, locked_prop=pA)
					reset_all_thresholds(context, [pA, pB])

				else:
					current_index += 1
					continue

			# Szenario B: Einzelparameter
			elif len(props) == 1:
				p = props[0]

				set_scene_value(context, p, 1.0)
				len_high = run_tracking_cycle(context)
				reset_all_thresholds(context, [p])

				set_scene_value(context, p, min_threshold)
				len_low = run_tracking_cycle(context)
				reset_all_thresholds(context, [p])

				if len_low > len_high:
					self._main_test(context, active_prop=p)
				else:
					current_index += 1
					continue

			current_index += 1

	def _main_test(self, context, active_prop: str, locked_prop: Optional[str] = None):
		# initiale Werte
		step_value = 140.0
		target_value = get_total_track_length(context, start_frame=get_start_frame(context))
		min_threshold = getattr(context.scene, "kaiserlich_scale_thresh_min", 0.002)

		start_threshold = get_scene_value(context, active_prop) or 1.0
		lower_threshold = min_threshold

		while step_value >= 1:
			current_start = start_threshold
			current_end = current_start / step_value

			# Fixierten Parameter setzen
			if locked_prop:
				set_scene_value(context, locked_prop, min_threshold)

			# Aktiven Parameter setzen
			set_scene_value(context, active_prop, current_end)

			# Trackingdurchlauf
			track_len = run_tracking_cycle(context)

			# Nach jedem Lauf: Reset aller anderen Werte (außer aktive und ggf. locked)
			active_props = [active_prop]
			if locked_prop:
				active_props.append(locked_prop)
			reset_all_thresholds(context, active_props)

			# Bewertung
			if track_len == target_value:
				lower_threshold = current_end
				step_value /= 2
				if step_value < 1:
					break
				continue

			elif track_len > target_value:
				target_value = track_len
				lower_threshold = current_end
				step_value /= 2
				if step_value < 1:
					break
				continue

			elif current_end <= min_threshold:
				step_value /= 2
				if step_value < 1:
					break
				continue

			else:
				start_threshold = current_end
				continue

		# Ende der Kalibrierung: Ergebnis speichern
		save_result(context, active_prop, lower_threshold)


def register():
	bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)


def unregister():
	bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)
