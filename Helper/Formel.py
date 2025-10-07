import marker_positions_helper  # Helfer 2
import motion_model_helper     # Helfer 3

def apply_formula_to_tracks(context):
    scene = context.scene
    clip  = context.space_data.clip  # aktiver Clip im Movie Clip Editor
    tracks = [t for t in clip.tracking.tracks if t.select]  # alle ausgewählten Tracks ermitteln
    if not tracks: 
        tracks = [clip.tracking.tracks.active]  # falls nichts explizit selektiert, aktiven Track nehmen
    for track in tracks:
        cur_frame = scene.frame_current
        positions = marker_positions_helper.get_positions(track, cur_frame, max_frames=5)
        if len(positions) < 2:
            continue  # Mit weniger als 2 Punkten keine Bewegung berechenbar
        # Lineares Bewegungsmodell berechnen (Steigung und Offset für x und y):
        frames = [f for (f, _co) in positions]
        xs     = [co.x for (_f, co) in positions]
        ys     = [co.y for (_f, co) in positions]
        # Mittelwerte:
        f_avg = sum(frames) / len(frames)
        x_avg = sum(xs) / len(xs)
        y_avg = sum(ys) / len(ys)
        # Steigung berechnen (Least Squares Fit):
        denom = sum((f - f_avg)**2 for f in frames)
        if denom == 0:
            continue
        beta_x = sum((f - f_avg)*(x - x_avg) for f, x in zip(frames, xs)) / denom
        beta_y = sum((f - f_avg)*(y - y_avg) for f, y in zip(frames, ys)) / denom
        alpha_x = x_avg - beta_x * f_avg
        alpha_y = y_avg - beta_y * f_avg
        # Auf Basis des Modells Soll-Positionen für jedes Frame berechnen:
        modeled_positions = []
        for f in frames:
            x_pred = alpha_x + beta_x * f
            y_pred = alpha_y + beta_y * f
            modeled_positions.append((f, (x_pred, y_pred)))
        # Übergabe an Motion-Model-Helfer zur Aktualisierung der Marker:
        motion_model_helper.apply_motion_model(track, modeled_positions)