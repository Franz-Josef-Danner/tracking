"""Blender Tracking Automation Add-on Root."""

bl_info = {
	"name": "Tracking Automation Cyclus",
	"author": "Auto-Generated",
	"version": (0, 1, 0),
	"blender": (3, 0, 0),
	"location": "Clip Editor > Sidebar > Tracking",
	"description": "Automatisierter Zyklus zur Marker-Detektion mit dynamischer Anpassung von Threshold & Min Distance",
	"category": "Tracking",
}

from importlib import import_module

_submodules = [
	"tracking.UI.ui",
]

_loaded = []


def register():
	for name in _submodules:
		mod = import_module(name)
		if hasattr(mod, "register"):
			mod.register()
		_loaded.append(mod)


def unregister():
	for mod in reversed(_loaded):
		if hasattr(mod, "unregister"):
			try:
				mod.unregister()
			except Exception as e:
				print(f"Fehler beim Unregister {mod.__name__}: {e}")
	_loaded.clear()


if __name__ == "__main__":
	register()
