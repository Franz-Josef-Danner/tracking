import bpy  # type: ignore

from ..Helper.bootstrap import run_bootstrap
from ..Helper.frames_limit import set_one_frame_limit
from ..Helper.track_forward import track_forward_selected_markers


class KAISERLICHTRACKER_OT_track_cycle(bpy.types.Operator):
	bl_idname = "kaiserlich_tracker.track_cycle"
	bl_label = "Track bis Szenen-Ende"
	bl_description = (
		"Trackt die aktuell selektierten Marker frameweise vorwärts bis zum Szenen-Ende. "
		"Verwendet Bootstrap für Parameter (se) und setzt Frames-Limit auf 1."
	)
	bl_options = {"REGISTER", "INTERNAL"}

	max_steps: bpy.props.IntProperty(  # type: ignore
		name="Max Schritte",
		default=0,
		min=0,
		soft_max=10000,
		description="Sicherheitslimit der zu trackenden Einzelschritte (0 = unbegrenzt)"
	)

	advance_scene_frame: bpy.props.BoolProperty(  # type: ignore
		name="Szene-Frame vorsetzen",
		default=True,
		description="Nach jedem Tracking-Schritt den Szenen-Frame (+1) setzen, damit pf sichtbar fortschreitet."
	)

	def execute(self, context):  # noqa: C901 (Ablauf bewusst linear gehalten)
		scene = getattr(context, 'scene', None)
		if scene is None:
			self.report({'WARNING'}, "Keine Szene im Kontext")
			return {'CANCELLED'}

		# Holen der Nutzer-Eingabe (Marker per Frame) – wird nur an Bootstrap gereicht (für Konsistenz / Logging)
		ef = getattr(scene, 'kaiserlich_markers_per_frame', 0) or 0
		params = run_bootstrap(context, ef)
		if not params:
			self.report({'WARNING'}, "Bootstrap fehlgeschlagen")
			return {'CANCELLED'}

		se = params.get('se')
		if se is None:
			self.report({'WARNING'}, "Szenen-Endframe (se) unbekannt")
			return {'CANCELLED'}

		clip = context.space_data.clip if getattr(context, 'space_data', None) else None
		if clip is None:
			self.report({'WARNING'}, "Kein aktiver Clip")
			return {'CANCELLED'}

		# Frame-Limit (pro Marker) auf 1 setzen, nur für selektierte Tracks
		changed = set_one_frame_limit(clip, only_selected=True)
		print(f"[Kaiserlich Tracker] frames_limit auf 1 gesetzt (Änderungen={changed})")

		pf = int(scene.frame_current)
		print(f"[Kaiserlich Tracker] Start pf={pf} se={se}")

		if pf >= se:
			self.report({'INFO'}, f"Bereits am oder hinter Szenen-Ende (pf={pf} >= se={se})")
			return {'FINISHED'}

		steps_done = 0
		reached_end = False

		# Schleife: solange aktueller Frame < Szenen-Ende
		while pf < se:
			# Sicherheitslimit prüfen
			if self.max_steps > 0 and steps_done >= self.max_steps:
				print("[Kaiserlich Tracker] Max Steps erreicht – Abbruch")
				break

			print(f"[Kaiserlich Tracker] Tracking Schritt {steps_done+1}: pf={pf}")
			ok = track_forward_selected_markers(context, sequence=False, backwards=False)
			if not ok:
				print("[Kaiserlich Tracker] Tracking abgebrochen / fehlgeschlagen")
				break

			steps_done += 1

			# Szene-Frame optional vorrücken (ansonsten bleibt die Anzeige stehen)
			if self.advance_scene_frame:
				pf += 1
				scene.frame_current = pf
			else:
				# Falls Scene-Frame nicht bewegt wird, versuchen wir pf via Auslesen neu zu bestimmen
				pf = int(scene.frame_current)

			if pf >= se:
				reached_end = True
				print(f"[Kaiserlich Tracker] Szenen-Ende erreicht pf={pf} se={se}")
				break

		status = "Fertig" if reached_end else ("Limit" if (self.max_steps > 0 and steps_done >= self.max_steps) else "Abbruch")
		self.report({'INFO'}, f"{status}: Schritte={steps_done} Letzter Frame={pf} (se={se})")
		return {'FINISHED'}


__all__ = [
	'KAISERLICHTRACKER_OT_track_cycle',
]

