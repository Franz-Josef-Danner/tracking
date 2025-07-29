import bpy


def execute(self, context):
    """Execute a simple operator reporting 'Hello World from Addon'."""
    self.report({'INFO'}, "Hello World from Addon")
    return {'FINISHED'}
