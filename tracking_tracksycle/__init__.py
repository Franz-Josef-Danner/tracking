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
    importlib.reload(ui_panel)
else:
    from . import tracksycle_operator
    from . import ui_panel

import bpy


def register():
    tracksycle_operator.register()
    ui_panel.register()


def unregister():
    ui_panel.unregister()
    tracksycle_operator.unregister()


if __name__ == "__main__":
    register()
