import bpy


def test_marker_base(context):
    """Berechnet Marker-Basiswerte aus dem Eingabefeld 'marker/Frame'."""

    scene = context.scene
    marker_basis = scene.get("marker_basis", 12)

    marker_plus = marker_basis / 3
    marker_adapt = marker_plus
    max_marker = marker_adapt + 1
    min_marker = marker_adapt - 1

    return {
        "marker_basis": marker_basis,
        "marker_plus": marker_plus,
        "marker_adapt": marker_adapt,
        "max_marker": max_marker,
        "min_marker": min_marker,
    }
