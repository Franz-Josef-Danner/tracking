"""Test package setup."""

import sys
import types

# Ensure modules that expect Blender's ``bpy`` can be imported during tests
sys.modules.setdefault("bpy", types.SimpleNamespace())

