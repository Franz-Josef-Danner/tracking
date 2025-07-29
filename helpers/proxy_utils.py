import bpy


def enable_proxy():
    """Enable proxies if possible."""
    if bpy.ops.clip.proxy_on.poll():
        bpy.ops.clip.proxy_on()


def disable_proxy():
    """Disable proxies if possible."""
    if bpy.ops.clip.proxy_off.poll():
        bpy.ops.clip.proxy_off()
