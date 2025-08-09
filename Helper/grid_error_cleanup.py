# Helper/grid_error_cleanup.py
import bpy

def _get_marker_position(track, frame):
    m = track.markers.find_frame(frame)
    return m.co if m else None

def _run_cleanup_in_region(tracks, frame_range, xmin, xmax, ymin, ymax, ee, width, height):
    """Innere Routine für eine Kachel + Toleranz. Löscht Ausreißer-Tripel (f1, fi, f2)."""
    total_deleted = 0
    frame_start, frame_end = frame_range

    # Wir brauchen 3-Frame-Fenster ⇒ keine Ränder
    for fi in range(frame_start + 1, frame_end - 1):
        f1, f2 = fi - 1, fi + 1
        marker_data = []

        # Kandidaten sammeln (Marker existiert auf f1, fi, f2 und p2 liegt in Kachel)
        for track in tracks:
            p1 = _get_marker_position(track, f1)
            p2 = _get_marker_position(track, fi)
            p3 = _get_marker_position(track, f2)
            if not (p1 and p2 and p3):
                continue

            x, y = p2[0] * width, p2[1] * height
            if not (xmin <= x < xmax and ymin <= y < ymax):
                continue

            # 2-Frame-Gesamtverschiebung über 3 Frames
            vxm = (p3[0] - p1[0])  # == (p2.x - p1.x) + (p3.x - p2.x)
            vym = (p3[1] - p1[1])
            vm = (vxm + vym) / 2.0
            marker_data.append((track, vm, f1, fi, f2))

        if not marker_data:
            continue

        # Lokaler Mittelwert
        va = sum(vm for _, vm, *_ in marker_data) / len(marker_data)

        # Initiales Fehlerband = max Abweichung (mind. 1e-4)
        eb = max((abs(vm - va) for _, vm, *_ in marker_data), default=0.0)
        if eb < 1e-4:
            eb = 1e-4

        # Iterativ „peelen“, bis Ziel-EE erreicht
        while eb > ee:
            eb *= 0.95
            # Kandidaten, die ≥ eb abweichen, komplett tripelweise löschen
            to_kill = [item for item in marker_data if abs(item[1] - va) >= eb]
            if not to_kill:
                break
            for track, _, f1, fi, f2 in to_kill:
                for f in (f1, fi, f2):
                    if track.markers.find_frame(f):
                        track.markers.delete_frame(f)
                        total_deleted += 1
            # Übrig gebliebene neu bewerten (optional; hier: lassen wir so)
            marker_data = [item for item in marker_data if item not in to_kill]

    return total_deleted


def grid_error_cleanup(context, space, *, verbose=False):
    """
    Führt die 3-Stufen-Grid-Error-Prüfung aus:
    - 1x1, 2x2, 4x4 Kacheln
    - Toleranz: ee, ee/2, ee/4; ee aus scene.error_track
    Löscht Ausreißer *Marker-Tripel* (f1, fi, f2). Gibt Anzahl gelöschter Marker zurück.
    """
    scene = context.scene
    clip = space.clip
    tracks = clip.tracking.tracks

    # keine laute Konsole
    for t in tracks:
        t.select = False

    width, height = clip.size
    frame_range = (scene.frame_start, scene.frame_end)

    # Basis-Toleranz (kompatibel zur ursprünglichen Logik)
    ee_base = 0.005
    tolerances = (ee_base, ee_base / 2.0, ee_base / 4.0)
    divisions  = (1, 2, 4)

    total_deleted_all = 0
    for ee, div in zip(tolerances, divisions):
        cell_w = width  / div
        cell_h = height / div
        for ix in range(div):
            for iy in range(div):
                xmin = ix * cell_w
                xmax = (ix + 1) * cell_w
                ymin = iy * cell_h
                ymax = (iy + 1) * cell_h
                total_deleted_all += _run_cleanup_in_region(
                    tracks, frame_range, xmin, xmax, ymin, ymax, ee, width, height
                )

    if verbose:
        print(f"[GridErrorCleanup] deleted_markers={total_deleted_all}")
    # Für Folgeschritte UI aktualisieren
    bpy.context.view_layer.update()
    return total_deleted_all
