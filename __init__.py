bl_info = {
    "name": "Kaiserlich Tracking Optimizer",
    "author": "Franz (converted by ChatGPT)",
    "version": (1, 0, 0),
    "blender": (4, 4, 3),
    "location": "Movie Clip Editor > Sidebar > Kaiserlich",
    "description": (
        "Automatisches Motion-Tracking mit adaptiver Marker-"
        "Platzierung und Kamera-Lösung"
    ),
    "category": "Tracking",
}

from . import ui


def register():
    ui.register()


def unregister():
    ui.unregister()


if __name__ == "__main__":
    register()
