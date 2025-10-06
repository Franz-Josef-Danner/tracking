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
	step_mode: bpy.props.BoolProperty(  # type: ignore
		name="Frameweise (sequence=False)",
		default=True,
		description="Wenn aktiv: pro Iteration nur 1 Frame tracken (sequence=False) und kein frames_limit=1 setzen"
	)
	min_progress_ratio: bpy.props.FloatProperty(  # type: ignore
		name="Min Fortschritt Quote",
		default=0.5,
		min=0.0,
		max=1.0,
		description="Anteil (0..1) selektierter Tracks, die in einer Iteration Fortschritt machen müssen, sonst Fallback/Abbruch"
	)
	retry_sequence_on_stall: bpy.props.IntProperty(  # type: ignore
		name="Fallback sequence-Retries",
		default=1,
		min=0,
		max=10,
		description="Wie oft bei 0-Fortschritt ein sequence=True Versuch unternommen wird (nur im step_mode)"
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

		# 1) Bootstrap (optional) -> liefert u.a. se (Endframe)
		if self.use_bootstrap:
			ef = getattr(scene, 'kaiserlich_markers_per_frame', 10)
			params = run_bootstrap(context, ef)
			if not params:
				self.report({'WARNING'}, "Bootstrap fehlgeschlagen")
				return {'CANCELLED'}
			se = params.get('se') or scene.frame_end
		else:
			se = scene.frame_end

		# 2) Playhead Frame (pf) ausgeben (vor Änderung des Frame-Limits)
		pf = scene.frame_current
		print(f"[Kaiserlich Tracker] Playhead Frame (pf): {pf} (se={se})")

		# 3) Frame-Limit setzen nur falls NICHT step_mode
		if not self.step_mode:
			changed = set_one_frame_limit(clip, only_selected=True)
			print(f"[Kaiserlich Tracker] frames_limit gesetzt (geändert={changed})")
		else:
			print("[Kaiserlich Tracker] step_mode aktiv: kein frames_limit=1 gesetzt (sequence=False)")

		# 4) Zyklus / Loop: Solange pf < se
		calls = 0
		start_frame = pf
		last_frame = pf - 1  # Damit erste Iteration als Fortschritt zählt

		stall_retries = 0
		while True:
			pf = scene.frame_current
			if pf >= se:
				print(f"[Kaiserlich Tracker] pf >= se ({pf} >= {se}) -> beendet")
				break
			print(f"[Kaiserlich Tracker] cycle start: pf={pf} se={se} calls={calls} mode={'STEP' if self.step_mode else 'SEQ_LIMIT1'}")

			tracking = getattr(clip, 'tracking', None)
			selected_tracks = []
			baseline = {}
			if self.step_mode and tracking is not None:
				for tr in tracking.tracks:
					if getattr(tr, 'select', False):
						selected_tracks.append(tr)
						markers = getattr(tr, 'markers', [])
						max_frame = -1
						for mk in markers:
							f = getattr(mk, 'frame', -1)
							if f > max_frame:
								max_frame = f
						baseline[tr] = max_frame
				# Debug: baseline summary
				if selected_tracks:
					mx = max(baseline.values()) if baseline else -1
					print(f"[Kaiserlich Tracker] STEP: baseline max marker frame={mx}")

			# Tracking: sequence=True nur im alten Modus. Im STEP Modus bleibt frame_current vor Call unverändert.
			scene_frame_before = scene.frame_current
			ok = track_forward_selected_markers(context, sequence=not self.step_mode, backwards=False)
			if not ok:
				print("[Kaiserlich Tracker] Tracking abgebrochen / Fehler")
				break
			calls += 1

			if self.step_mode:
				# Fortschrittsermittlung & Catch-Up Logik
				scene_frame_after = scene.frame_current
				delta_scene = scene_frame_after - scene_frame_before
				new_max_per_track = {}
				any_new_marker = False
				global_max_marker = -1
				global_min_marker = None
				for tr in selected_tracks:
					markers = getattr(tr, 'markers', [])
					max_frame_after = -1
					for mk in markers:
						f = getattr(mk, 'frame', -1)
						if f > max_frame_after:
							max_frame_after = f
					if max_frame_after > global_max_marker:
						global_max_marker = max_frame_after
					if global_min_marker is None or (max_frame_after >= 0 and max_frame_after < global_min_marker):
						global_min_marker = max_frame_after
					new_max_per_track[tr] = max_frame_after
					if max_frame_after > baseline.get(tr, -1):
						any_new_marker = True

				print(f"[Kaiserlich Tracker] STEP: frame_before={scene_frame_before} frame_after={scene_frame_after} delta={delta_scene} any_new_marker={any_new_marker} min_marker={global_min_marker} max_marker={global_max_marker}")

				# Fortschritt auswerten: Wieviele Tracks haben neue Marker?
				progress_count = 0
				for tr, max_after in new_max_per_track.items():
					if max_after > baseline.get(tr, -1):
						progress_count += 1
				progress_ratio = (progress_count / len(new_max_per_track)) if new_max_per_track else 0.0
				print(f"[Kaiserlich Tracker] STEP: progress_count={progress_count}/{len(new_max_per_track)} ratio={progress_ratio:.2f} threshold={self.min_progress_ratio:.2f} retries={stall_retries}/{self.retry_sequence_on_stall}")

				if progress_ratio >= self.min_progress_ratio or delta_scene > 0:
					stall_retries = 0  # Reset Stall Counter
					if delta_scene == 0:
						# Kein Szenen-Fortschritt -> versuchen manuell vorzugehen, falls alle Tracks schon nächsten Frame haben
						current_target = scene_frame_after + 1
						all_have_next = True
						for tr, max_after in new_max_per_track.items():
							if max_after < current_target:
								all_have_next = False
								break
						if all_have_next and scene_frame_after + 1 <= se:
							scene.frame_current = scene_frame_after + 1
							print(f"[Kaiserlich Tracker] STEP: manual advance -> {scene.frame_current}")
						else:
							print("[Kaiserlich Tracker] STEP: kein manual advance (noch nicht alle Tracks bereit oder Ende erreicht)")
					else:
						print(f"[Kaiserlich Tracker] STEP: Operator hat Frame verschoben (delta={delta_scene})")
					# Weiter zur nächsten Iteration
				else:
					# Kein ausreichender Fortschritt
					if progress_count == 0:
						# Prüfen ob wir nur 'aufholen' können (alle Tracks besitzen bereits Marker >= pf+1)
						current_target = scene_frame_before + 1
						all_ahead = True
						for tr, max_after in new_max_per_track.items():
							if max_after < current_target:
								all_ahead = False
								break
						if all_ahead and scene_frame_before + 1 <= se:
							scene.frame_current = scene_frame_before + 1
							print(f"[Kaiserlich Tracker] STEP: catch-up advance -> {scene.frame_current}")
							stall_retries = 0
							# weiter
						elif stall_retries < self.retry_sequence_on_stall:
							stall_retries += 1
							print(f"[Kaiserlich Tracker] STEP: stall detected -> sequence Fallback Versuch {stall_retries}/{self.retry_sequence_on_stall}")
							# Fallback: versuche einmal sequence=True sofort (ohne Loop-Zähler zu erhöhen)
							fallback_ok = track_forward_selected_markers(context, sequence=True, backwards=False)
							if not fallback_ok:
								print("[Kaiserlich Tracker] STEP: Fallback sequence fehlgeschlagen -> Abbruch")
								break
							# Nach Fallback erneut Marker aktualisieren (einfach nächste Iteration läuft neu mit Baseline)
							continue
						else:
							print("[Kaiserlich Tracker] Kein neuer Marker-Fortschritt & kein Catch-up/Fallback mehr -> Abbruch")
							break
					else:
						# Etwas Fortschritt aber unter Quote
						print("[Kaiserlich Tracker] Fortschritt unter Quote -> Abbruch (Konfiguration min_progress_ratio anpassen?)")
						break
			else:
				# SEQ_LIMIT1 Modus: Szene sollte selbst fortschreiten; prüfen ob Frame sprang
				pf_new = scene.frame_current
				if pf_new == pf:
					print("[Kaiserlich Tracker] Kein Frame-Fortschritt erkannt -> Abbruch")
					break

			if self.max_internal_calls > 0 and calls >= self.max_internal_calls:
				print(f"[Kaiserlich Tracker] Sicherheitslimit erreicht (calls={calls})")
				break
			# nächste Iteration (pf wird oben neu gelesen)

		status = "vollständig" if scene.frame_current >= se else "vorzeitig beendet"
		self.report({'INFO'}, f"Tracking {status}: Start={start_frame} Ende={scene.frame_current} Calls={calls}")
		return {'FINISHED'}

__all__ = [
	"KAISERLICHTRACKER_OT_track_cycle",
]
