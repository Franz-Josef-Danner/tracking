from .delete import delete_marker


def cleanup(context, new_markers, old_markers, values):
    width, height, min_distance = values["width"], values["height"], values["md"]
    min_distance_sq = min_distance * min_distance

    # Vereinfachte O(n*m) Variante – für hohe Marker-Zahlen könnte KD-Tree genutzt werden
    for nm in new_markers:
        for om in old_markers:
            dx = (om.co[0] - nm.co[0]) * width
            dy = (om.co[1] - nm.co[1]) * height
            dist_sq = dx * dx + dy * dy
            if dist_sq < min_distance_sq:
                delete_marker(nm)
                break
