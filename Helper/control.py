from .bootstrap import bootstrap
from .snapshot import snapshot
from .detect import detect_features
from .newmarker import newmarker
from .cleanup import cleanup
from .delete import delete_marker

# Status-Codes für den Kontrollzyklus
STOP = "STOP"
RETRY_TOO_FEW = "RETRY_FEW"
RETRY_TOO_MANY = "RETRY_MANY"

def detect_cyclus(context, max_cycles: int = 15):
    """Führt einen adaptiven Feature-Detection-Zyklus iterativ aus.

    max_cycles: Sicherheitsgrenze gegen endlose Schleifen.
    """
    values = bootstrap(context)
    cycle = 0
    while cycle < max_cycles:
        cycle += 1
        lm = snapshot(context)
        detect_features(context, values)
        nm = newmarker(context)
        cleanup(context, nm, lm, values)
        status = control_cycle(context, nm, values)
        if status == STOP:
            print(f"Kaiserlich Tracker: Finished after {cycle} cycle(s) with {len(nm)} markers")
            break
        elif status == RETRY_TOO_FEW or status == RETRY_TOO_MANY:
            continue
        else:
            print(f"Kaiserlich Tracker: Unbekannter Status '{status}', Abbruch.")
            break
    else:
        print(f"Kaiserlich Tracker: Abbruch nach max_cycles={max_cycles} ohne Stabilisierung.")


def control_cycle(context, nm_list, values):
    """Bewertet Ergebnis und passt Parameter an.

    Rückgabe: STOP | RETRY_FEW | RETRY_MANY
    """
    am = len(nm_list)

    # Zielkorridor erreicht
    if values["ug"] <= am <= values["og"]:
        return STOP

    # Zu wenige Marker: threshold senken, pz erhöhen (Reserve für spätere Nutzung)
    if am < values["ug"]:
        values["tr"] *= 0.5
        if values["tr"] < 0.1:
            return STOP
        values["pz"] *= 1.1
        return RETRY_TOO_FEW

    # Zu viele Marker: alle neuen löschen und Mindestabstand adaptiv erhöhen
    if am > values["og"]:
        for nm in nm_list:
            delete_marker(nm)
        if values["za"] > 0:
            values["md"] *= (am / values["za"])
        return RETRY_TOO_MANY

    return STOP  # Fallback
