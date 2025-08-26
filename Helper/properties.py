# properties.py
import bpy
from bpy.props import StringProperty, IntProperty

class RepeatEntry(bpy.types.PropertyGroup):
    frame: StringProperty(name="Frame")
    count: IntProperty(name="Count")
