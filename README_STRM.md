# STRM Feature Tracker (Blender Add-on)

Dieses Add-on analysiert Video-Frames in Tiles (STRM: Texture/Motion/Divergence/Flicker), seeded Features, trackt sie, passt Bewegungsmodelle (Global & pro Cluster) an und bietet Stabilisierung, Reseeding, HUD/Overlay sowie Logging.

Wichtige Hinweise:

- Entwicklung außerhalb von Blender zeigt oft „Import nicht aufgelöst“ für `bpy`, `numpy`, `cv2`. Das ist normal – Blender bringt seine eigene Python-Umgebung mit. Teste das Add-on in Blender.
- Optionale Features nutzen HDBSCAN; ohne installiertes `hdbscan` wird automatisch nur DBSCAN verwendet.

Installation (lokal testen):

1. Blender öffnen → Edit → Preferences → Add-ons → Install…
2. Den Ordner `strm_tracker` als Zip packen oder das Repo zippen und installieren.
3. Add-on aktivieren: „STRM Feature Tracker“.
4. Movie Clip Editor öffnen → Sidebar „STRM“.

Funktionen (Auszug):

- Analyse: Tiles farblich nach Score, Auswahl der ROIs.
- Seeding: normales und „Staged Seeding (/5)“ mit Budget & Priorisierung.
- Tracking & KPIs: LK-Flow, Qualitätsmetriken, Cleanup.
- Modelle: Fit globaler Modelle + Promotion Engine (Level: loc → locrot → lrs → affine → perspective).
- Clustering: Adaptive DBSCAN, HDBSCAN-Fallback, pro Cluster Promotion.
- Stabilisierung: Peer-Snap Outlier → Medianfluss, Reseed leere Tiles.
- HUD/Overlay: Residual-Vektoren und Statistiken.
- Logging: Snapshots aufnehmen, Export als JSON/CSV.

Troubleshooting:

- Wenn keine Tiles erscheinen: sicherstellen, dass ein MovieClip aktiv ist und Overlay eingeschaltet ist.
- cv2-Fehler: OpenCV muss in der Blender-Python-Umgebung installiert sein (oder System-Python kompatibel einbinden).
- Performance: Reduziere Tile-Größe, Marker-Anzahl oder die Anzahl Frames pro Tracking.
