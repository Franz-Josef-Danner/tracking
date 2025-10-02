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
    """Iterative Steuerung des Marker-Detektionszyklus nach geänderter Bedingung.

    Änderung: Falls Reinbereich NICHT erreicht wird, werden ALLE neu entstandenen Marker
    (dieses Zyklus) vor Anpassung & Restart wieder gelöscht – egal ob zu wenig oder zu viele.
    """
    values = bootstrap(context)
    print(
        f"Kaiserlich Tracker: Zielkorridor – ug={values['ug']:.1f} za={values['za']:.1f} og={values['og']:.1f}"
    )
    cycle = 0
    while cycle < max_cycles:
        cycle += 1
        lm = snapshot(context)  # Alte Marker vor neuem Detect
        old_count = len(lm)
        clip = context.edit_movieclip
        pre_track_names = {t.name for t in clip.tracking.tracks}

        print(
            f"Kaiserlich Tracker: Zyklus {cycle} – Start: {old_count} alt | ug={values['ug']:.1f} za={values['za']:.1f} og={values['og']:.1f} tr={values['tr']:.3f} md={values['md']:.1f}"
        )

        # Neue Features suchen
        detect_features(context, values)

        # Marker nach Detection und vor Cleanup
        all_after_detection = newmarker(context)
        raw_total = len(all_after_detection)
        raw_added = raw_total - old_count

        # Cleanup (Duplikate entfernen)
        cleanup(context, all_after_detection, lm, values)

        # Nach Cleanup neu zählen
        after_cleanup_all = snapshot(context)
        total_after_cleanup = len(after_cleanup_all)
        removed = raw_total - total_after_cleanup

        # Neu entstandene Tracks (Feature-Detect erstellt i.d.R. neue Tracks pro Marker)
        post_tracks = [t for t in clip.tracking.tracks]
        new_tracks = [t for t in post_tracks if t.name not in pre_track_names]

        # Neu entstandene Marker (nur zur Info)
        new_markers = [m for tr in new_tracks for m in tr.markers if m.frame == context.scene.frame_current]
        new_count = len(new_markers)
        candidate_total = total_after_cleanup

        print(
            f"Kaiserlich Tracker: Zyklus {cycle} – Roh +{raw_added} | entfernt {removed} | neu {new_count} | total {candidate_total}"
        )

        status = control_cycle(context, clip, new_tracks, candidate_total, values)

        if status == STOP:
            print(
                f"Kaiserlich Tracker: Fertig nach {cycle} Zyklen mit {candidate_total} Markern (ug≤{candidate_total}≤og)"
            )
            break
        elif status == RETRY_TOO_FEW:
            print(
                f"Kaiserlich Tracker: Restart (zu wenig) – threshold={values['tr']:.3f} pz={values['pz']:.3f} md={values['md']:.1f}"
            )
            continue
        elif status == RETRY_TOO_MANY:
            print(
                f"Kaiserlich Tracker: Restart (zu viele) – threshold={values['tr']:.3f} md={values['md']:.1f}"
            )
            continue
        else:
            print(f"Kaiserlich Tracker: Unbekannter Status '{status}', Abbruch.")
            break
    else:
        print(f"Kaiserlich Tracker: Abbruch nach max_cycles={max_cycles} ohne Stabilisierung.")


def control_cycle(context, clip, new_tracks, candidate_total, values):
    """Bewertet Gesamtmarkerzahl; löscht bei Abweichung komplette neu entstandene Tracks.

    Rückgabe: STOP | RETRY_FEW | RETRY_MANY
    """
    ug = values["ug"]
    og = values["og"]

    if ug <= candidate_total <= og:
        return STOP

    # Neue Tracks verwerfen
    for tr in new_tracks:
        try:
            clip.tracking.tracks.remove(tr)
        except Exception:
            pass

    if candidate_total < ug:
        values["tr"] *= 0.5
        if values["tr"] < 0.1:
            return STOP
        values["pz"] *= 1.1
        return RETRY_TOO_FEW

    if candidate_total > og:
        if values["za"] > 0:
            factor = candidate_total / values["za"]
            factor = min(factor, 4.0)
            values["md"] *= factor
        return RETRY_TOO_MANY

    return STOP
