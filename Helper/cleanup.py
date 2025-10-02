from .delete import delete_marker

def cleanup(context, nm, lm, values):
    hz, vc, md = values["hz"], values["vc"], values["md"]

    # Entferne neue Marker, die zu nah an alten liegen
    for nm_i in list(nm):
        for lm_i in lm:
            disH = abs((lm_i.co[0] - nm_i.co[0]) * hz)
            disV = abs((lm_i.co[1] - nm_i.co[1]) * vc)
            if disH < md or disV < md:
                delete_marker(nm_i)
                break
