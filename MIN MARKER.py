import bpy

# Beispielwert aus einem Menü (z.B. Benutzer-Eingabe oder UI-Property)
x = 10  # Diesen Wert kannst du durch eine Variable oder UI-Element ersetzen

# Berechnungen
min_marker_count_plus = x * 4
min_marker_count_plus_min = min_marker_count_plus * 0.8
min_marker_count_plus_max = min_marker_count_plus * 1.2

# Speichern als benutzerdefinierte Eigenschaften in der Szene (z. B. für späteren Zugriff)
bpy.context.scene["MIN_MARKER_COUNT"] = x
bpy.context.scene["MIN_MARKER_COUNT_PLUS"] = min_marker_count_plus
bpy.context.scene["MIN_MARKER_COUNT_PLUS_MIN"] = min_marker_count_plus_min
bpy.context.scene["MIN_MARKER_COUNT_PLUS_MAX"] = min_marker_count_plus_max

# Ausgabe in der Konsole zur Kontrolle
print("MIN_MARKER_COUNT:", x)
print("MIN_MARKER_COUNT_PLUS:", min_marker_count_plus)
print("MIN_MARKER_COUNT_PLUS_MIN:", min_marker_count_plus_min)
print("MIN_MARKER_COUNT_PLUS_MAX:", min_marker_count_plus_max)