import bpy
from math import isclose

from tracking.Helper.bootstrap import bootstrap
from tracking.Helper.snapshot import snapshot_markers
from tracking.Helper.detect import detect_features
from tracking.Helper.newmarker import new_markers
from tracking.Helper.cleaneup import cleanup_new_markers
from tracking.Helper.delete import delete_marker


def run_cycle(context):
    scn = context.scene
    desired = getattr(scn, 'tracking_markers_per_frame', 25)

    data = bootstrap(context, desired)
    hz = data['hz']
    vc = data['vc']
    md = data['md']
    pz = data['pz']
    tr = data['tr']
    za = data['za']
    og = data['og']
    ug = data['ug']

    frame = context.scene.frame_current

    # Initial snapshot (alte Marker)
    alte_marker = snapshot_markers(frame)

    iteration = 0
    max_iterations = 100

    while iteration < max_iterations:
        iteration += 1
        print(f"\n--- Zyklus Iteration {iteration} ---")
        print(f"Parameter: tr={tr:.4f} md={md} pz={pz} (ug={ug:.2f}, og={og:.2f})")

        # Detect attempt
        detect_features(margin=data['ma'], threshold=tr, min_distance=md)

        # Snapshot after detection
        neue_marker = new_markers(frame, alte_marker)

        # Anzahl neue Marker (vor Cleanup)
        am_raw = len(neue_marker)
        if am_raw == 0:
            print("Keine neuen Marker gefunden. Beende.")
            break

        # Cleanup gegen alte Marker (Abstand OR-Regel)
        cleaned, removed = cleanup_new_markers(neue_marker, alte_marker, hz, vc, md)
        for m in removed:
            delete_marker(m, frame)
        am = len(cleaned)
        print(f"Neue Marker: vor Cleanup={am_raw} nach Cleanup={am}")

        # Speichere akzeptierte neue Marker als Teil der Basis wenn wir sie behalten
        # (erst wenn wir die Iteration als 'fertig' akzeptieren)

        # Entscheidungslogik nach Pseudocode
        # Fälle basieren auf za Ziel, ug (0.9*za) untere Grenze, og (1.1*za) obere Grenze

        if am > ug:
            if am < og:
                # Innerhalb Toleranzfenster -> Feinabstimmung über threshold & pz
                tr = tr * 0.15
                print(f"Marker innerhalb Fenster (>ug,<og) -> reduziere threshold stark: tr={tr:.4f}")
                if tr < 0.1:
                    print("Threshold < 0.1 -> Fertig. Behalte neue Marker.")
                    alte_marker.extend(cleaned)
                    break
                # pz * 1.1 (größere Pattern Size kann robustere Auswahl geben)
                pz = max(int(pz * 1.1), 1)
                print(f"Erhöhe pattern size auf {pz}, wiederhole Zyklus (lösche neue Marker)")
                for m in cleaned:
                    delete_marker(m, frame)
                continue
            else:
                # am >= og -> zu viele Marker
                if za == 0:
                    ratio = 1
                else:
                    ratio = za / am  # für Ausdruck md / (za / am) == md * (am/za); wir formen um für Stabilität
                # md_neu = md / (za / am) = md * (am/za)
                if za != 0:
                    md = max(1, int(md * (am / za)))
                print(f"Zu viele Marker (>=og). Passe md an -> {md}. Lösche neue Marker und wiederhole.")
                for m in cleaned:
                    delete_marker(m, frame)
                continue
        else:
            # am <= ug -> zu wenige Marker
            if am == 0 or za == 0:
                # Verhindere Division durch 0: verringere md leicht
                md = max(1, int(md * 0.8))
                tr = min(1.0, tr * 1.05)
                print(f"Sehr wenige/keine Marker. md->{md}, tr->{tr:.4f} Wiederhole.")
                continue
            # md / (za / am) = md * (am/za) -> da am<za -> md wird kleiner -> erlaubt dichtere Marker
            md = max(1, int(md * (am / za)))
            print(f"Zu wenige Marker (<=ug). Verringere md auf {md}, lösche neue Marker und wiederhole.")
            for m in cleaned:
                delete_marker(m, frame)
            continue

        # Falls keine Bedingung gegriffen hat (z.B. genau im sweet spot?)
        if ug <= am <= og:
            print("Zielbereich erreicht. Übernehme neue Marker und beende.")
            alte_marker.extend(cleaned)
            break

    else:
        print("Maximale Iterationen erreicht -> Stop.")

    return True
