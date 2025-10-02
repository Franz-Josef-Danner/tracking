from .delete import delete_marker


def cleanup(context, nm, lm, values):
    """Entfernt neu erkannte Marker, die zu nah an alten Markern liegen.

    Gibt Liste der verbleibenden (nicht gemuteten) neuen Marker zurück.
    Abstandsprüfung getrennt horizontal/vertikal wie im Pseudocode.
    """
    hz = values['hz']
    vc = values['vc']
    md = values['md']

    removed = 0
    for nm_i in nm:
        if getattr(nm_i, 'mute', False):
            continue
        nmhpo = nm_i.co[0] * hz
        nmvpo = nm_i.co[1] * vc
        for ama_i in lm:
            amahpo = ama_i.co[0] * hz
            amavpo = ama_i.co[1] * vc
            disH = abs(amahpo - nmhpo)
            disV = abs(amavpo - nmvpo)
            if disH < md or disV < md:
                delete_marker(nm_i)
                removed += 1
                break
    if removed:
        print(f'[Kaiserlich][cleanup] {removed} Marker entfernt (zu nah)')

    # Nur nicht gemutete Marker zurückgeben
    remaining = [m for m in nm if not getattr(m, 'mute', False)]
    return remaining


def delete_marker(marker, hard=False):
    if not hard:
        marker.mute = True
        return
    import bpy
    ctx_scene = bpy.context.scene
    old_frame = ctx_scene.frame_current
    try:
        ctx_scene.frame_current = marker.frame
        track = marker.track
        # Auswahl zurücksetzen
        clip = bpy.context.space_data.clip
        for t in clip.tracking.tracks:
            t.select = False
        track.select = True
        # Einzelmarker-Selektion (Marker hat kein eigenes select Flag, Track-Selekt reicht für Frame)
        bpy.ops.clip.delete_marker()  # löscht Marker im aktuellen Frame für selektierte Tracks
    finally:
        ctx_scene.frame_current = old_frame
