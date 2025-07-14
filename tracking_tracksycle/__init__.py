bl_info = {
    'name': 'Kaiserlich Tracksycle',
    'blender': (4, 0, 0),
    'category': 'Tracking',
    'author': 'Auto Generated',
    'version': (0, 1, 0),
    'description': 'Automated tracking cycle for Blender',
}

if 'bpy' in locals():
    import importlib
    importlib.reload(tracksycle_operator)
else:
    from . import tracksycle_operator

import bpy


def register():
    tracksycle_operator.register()


def unregister():
    tracksycle_operator.unregister()


if __name__ == "__main__":
    register()
