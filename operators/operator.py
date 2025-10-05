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
		marker_per_frame = context.scene.kt_marker_per_frame
		try:
			params = helper_bootstrap.run_detect_cyclus(context, marker_per_frame)
		except RuntimeError as e:
			self.report({'WARNING'}, f"Abgebrochen: {e}")
			return {'CANCELLED'}
		self.report({'INFO'}, f"Detect Cyclus fertig (pz={params['pz']} sz={params['sz']})")
		return {'FINISHED'}


classes = (KT_OT_detect_cyclus,)


def register():
	for c in classes:
		bpy.utils.register_class(c)


def unregister():
	for c in reversed(classes):
		bpy.utils.unregister_class(c)

