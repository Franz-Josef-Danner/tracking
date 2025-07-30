import bpy

def create_proxy():
    """Erstellt Proxy-Dateien mit dem vorhandenen Operator."""
    if bpy.ops.clip.proxy_build.poll():
        bpy.ops.clip.proxy_build()


def enable_proxy():
    """Enable proxies if possible."""
    if bpy.ops.clip.proxy_on.poll():
        bpy.ops.clip.proxy_on()


def disable_proxy():
    """Disable proxies if possible."""
    if bpy.ops.clip.proxy_off.poll():
        bpy.ops.clip.proxy_off()

