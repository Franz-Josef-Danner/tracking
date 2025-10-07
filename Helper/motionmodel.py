def apply_motion_model(track, modeled_positions):
    # modeled_positions = Liste von (frame, (x_pred, y_pred))
    for frame, (x, y) in modeled_positions:
        marker = track.markers.find_frame(frame, exact=True)
        if not marker:
            continue  # (sollte normalerweise nicht passieren, da Frames aus Tracking stammen)
        marker.co = (x, y)  # neue Position setzen (normierte Koordinaten)