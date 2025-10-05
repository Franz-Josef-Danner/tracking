import importlib
import bpy
from ..Helper import bootstrap as helper_bootstrap


class KT_OT_detect_cyclus(bpy.types.Operator):
	bl_idname = "kt.detect_cyclus"
	bl_label = "Detect Cyclus"
	bl_description = "Starte den Zyklus-Detektionsprozess"
	bl_options = {"REGISTER", "UNDO"}

	def execute(self, context):
		# Reload Helper Bootstrap für schnelle Iteration
		importlib.reload(helper_bootstrap)
		# Zugriff über PropertyGroup (persistente Parameter)
		params_pg = context.scene.kt_params
		marker_per_frame = params_pg.marker_per_frame
		try:
			params = helper_bootstrap.run_detect_cyclus(context, marker_per_frame)
		except RuntimeError as e:
			self.report({'WARNING'}, f"Abgebrochen: {e}")
			return {'CANCELLED'}
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
		self.report({'INFO'}, f"Detect Cyclus fertig (pz={params['pz']} sz={params['sz']} markers={params.get('marker_count', 0)})")
		return {'FINISHED'}


classes = (KT_OT_detect_cyclus,)


def register():
	for c in classes:
		bpy.utils.register_class(c)


def unregister():
	for c in reversed(classes):
		bpy.utils.unregister_class(c)

