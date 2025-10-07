def get_positions(track, cur_frame, max_frames=5):
    positions = []
    # Frame-Bereich bestimmen
    start_frame = max(cur_frame - (max_frames - 1), track.markers[0].frame)
    for frame in range(start_frame, cur_frame + 1):
        marker = track.markers.find_frame(frame)
        if not marker:
            break  # falls Track hier endet
        co = marker.co  # 2D-Vector (normierte Koordinate)
        positions.append((frame, co.copy()))
    return positions