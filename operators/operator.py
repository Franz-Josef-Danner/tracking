import importlib
import bpy
from ..Helper import bootstrap as helper_bootstrap
from ..Helper import snapshot as helper_snapshot
from ..Helper import detect as helper_detect
from ..Helper import newmarker as helper_newmarker


class KT_OT_detect_cyclus(bpy.types.Operator):
	bl_idname = "kt.detect_cyclus"
	bl_label = "Detect Cyclus"
	bl_description = "Starte den Zyklus-Detektionsprozess"
	bl_options = {"REGISTER", "UNDO"}

	def execute(self, context):
		# Reload Helper Module für schnelle Iteration
		importlib.reload(helper_bootstrap)
		importlib.reload(helper_snapshot)
		importlib.reload(helper_detect)
		importlib.reload(helper_newmarker)
		# Zugriff über PropertyGroup (persistente Parameter)
		params_pg = context.scene.kt_params
		marker_per_frame = params_pg.marker_per_frame
		try:
			# 1. Parameter berechnen
			params = helper_bootstrap.compute_parameters(context, marker_per_frame)
		except RuntimeError as e:
			self.report({'WARNING'}, f"Abgebrochen: {e}")
			return {'CANCELLED'}
		# 2. Snapshot vor Detection
		markers = helper_snapshot.collect_active_markers(context)
		params['marker_count'] = len(markers)
		# 3. Marker Größen setzen (Pattern/Search) – bereits durch compute_parameters pz/sz ermittelt
		from ..Helper import marker_size as helper_marker_size  # local import to ensure latest
		importlib.reload(helper_marker_size)
		helper_marker_size.apply_marker_size(params['pz'], params['sz'])
		# 4. Neue Marker anlegen (heuristisch) – optional: hier nutzen wir og als Zielmenge Obergrenze
		new_added = helper_newmarker.create_new_markers(context, desired=int(params['og']))
		params['new_marker_added'] = new_added
		# 5. Feature Detection mit tr, md, ma
		detect_res = helper_detect.run_detect(
			context,
			tr=params['tr'],
			md=params['md'],
			ma=params['ma'],
		)
		# Werte zurück in PropertyGroup schreiben
		params_pg.hz = int(params['hz'])
		params_pg.vc = int(params['vc'])
		params_pg.pz = int(params['pz'])
		params_pg.sz = int(params['sz'])
		params_pg.og = int(params['og'])
		params_pg.ug = int(params['ug'])
		params_pg.md = float(params['md'])
		params_pg.ma = float(params['ma'])
		params_pg.za = float(params['za'])
		params_pg.tr = int(params['tr'])
		params_pg.marker_count = int(params.get('marker_count', 0))
		self.report({'INFO'}, f"Detect Cyclus fertig (detect={detect_res} neu={params.get('new_marker_added',0)} pz={params['pz']} sz={params['sz']} markers={params.get('marker_count', 0)})")
		return {'FINISHED'}


classes = (KT_OT_detect_cyclus,)


def register():
	for c in classes:
		bpy.utils.register_class(c)


def unregister():
	for c in reversed(classes):
		bpy.utils.unregister_class(c)

