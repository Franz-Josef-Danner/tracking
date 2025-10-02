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
    print(
        f"Kaiserlich Tracker: Zielkorridor initialisiert – Untergrenze (ug)={values['ug']:.1f}, Ziel (za)={values['za']:.1f}, Obergrenze (og)={values['og']:.1f}"
    )
    cycle = 0
    while cycle < max_cycles:
        cycle += 1
        lm = snapshot(context)  # Marker vor neuem Detect
        prev_count = len(lm)

        print(
            f"Kaiserlich Tracker: Zyklus {cycle} – Start: {prev_count} Marker | Untergrenze={values['ug']:.1f} Ziel={values['za']:.1f} Obergrenze={values['og']:.1f}"
        )

        # Feature Detection
        detect_features(context, values)

        # Marker direkt nach Detection (vor Cleanup)
        nm_raw = newmarker(context)
        raw_count = len(nm_raw)
        raw_added = raw_count - prev_count

        # Cleanup Duplikate entfernen
        cleanup(context, nm_raw, lm, values)

        # Finale Marker nach Cleanup erneut zählen
        nm_final = snapshot(context)
        final_count = len(nm_final)
        final_added = final_count - prev_count
        removed = raw_count - final_count

        print(
            f"Kaiserlich Tracker: Zyklus {cycle} – Roh +{raw_added} -> bereinigt -{removed} = +{final_added} (End: {final_count}) | tr={values['tr']:.3f} md={values['md']:.1f}"
        )

        status = control_cycle(context, nm_final, values)
        if status == STOP:
            print(
                f"Kaiserlich Tracker: Finished nach {cycle} Zyklen mit {final_count} Markern (ug={values['ug']:.1f} ≤ {final_count} ≤ og={values['og']:.1f})"
            )
            break
        elif status == RETRY_TOO_FEW:
            print(
                f"Kaiserlich Tracker: Zu wenige Marker ({final_count} < ug={values['ug']:.1f}) – threshold abgesenkt auf {values['tr']:.3f}, nächster Zyklus..."
            )
            continue
        elif status == RETRY_TOO_MANY:
            print(
                f"Kaiserlich Tracker: Zu viele Marker ({final_count} > og={values['og']:.1f}) – Mindestabstand erhöht auf {values['md']:.1f}, nächster Zyklus..."
            )
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
