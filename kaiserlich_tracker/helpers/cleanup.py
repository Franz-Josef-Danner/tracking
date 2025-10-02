from .delete import delete_marker


def cleanup(context, nm, lm, values):
    """Entfernt neu erkannte Marker, die zu nah an alten Markern liegen.

    Abstandsprüfung getrennt horizontal/vertikal wie im Pseudocode.
    """
    hz = values['hz']
    vc = values['vc']
    md = values['md']

    removed = 0
    for nm_i in nm:
        nmhpo = nm_i.co[0] * hz
        nmvpo = nm_i.co[1] * vc
        too_close = False
        for ama_i in lm:
            amahpo = ama_i.co[0] * hz
            amavpo = ama_i.co[1] * vc
            disH = abs(amahpo - nmhpo)
            disV = abs(amavpo - nmvpo)
            if disH < md or disV < md:
                delete_marker(nm_i)
                removed += 1
                too_close = True
                break
        if not too_close:
            # Gültiger Marker
            pass
    if removed:
        print(f'[Kaiserlich][cleanup] {removed} Marker entfernt (zu nah)')
