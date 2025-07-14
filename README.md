---

# 🍴 Kaiserlich Tracksycle – Technisches README

Ein automatisierter Tracking-Zyklus für Blender (ab 4.0), entwickelt zur robusten Feature-Erkennung und bidirektionalen Marker-Nachverfolgung mit dynamischer Reaktion auf Markerqualität, Proxystatus und Trackingfehler.

---

## 📂 Struktur

```
tracking-tracksycle/
├── __init__.py           # Add-on entry point
├── detect_features.py    # Dynamische Feature-Erkennung
# Weitere Module sind geplant, aber noch nicht implementiert
```

## Installation

1. Erstelle ein ZIP-Archiv des Ordners `tracking_tracksycle`.
2. In Blender unter **Edit → Preferences → Add-ons** auf **Install...** klicken und das ZIP wählen.
3. Das Add-on "Kaiserlich Tracksycle" aktivieren.
4. Den Operator `KAISERLICH_OT_detect_features` über die Suchfunktion oder ein eigenes Panel ausführen.

---

## 🧽 Ablaufplan (Operator: `KAISERLICH_OT_auto_track_cycle`)

### 1. **Proxy-Handling (async)**

```python
from .proxy_wait import create_proxy_and_wait
```

* Entfernt zuvor generierte Proxy-Dateien via `remove_existing_proxies()`
* Erstellt 50%-Proxy in `BL_Tr_proxy/`
* Wartet asynchron mit Timer auf erste Proxy-Datei (`proxy_50.avi`, max. Timeout: 300s)
* Nutzt Dateigrößen-Prüfung zur Validierung abgeschlossener Proxy-Erstellung
* Implementiert überarbeitetes und stabiles Verfahren laut `proxy_wait (1).py`

#### ✨ Besonderheiten der stabilen Version

* Separate Thread-Logik zur Dateiprüfung
* Fehlerbehandlung via Logging
* Sauberes Abbrechen nach Timeout

---

### 2. **Detect Features**

```python
bpy.ops.clip.detect_features(threshold=dynamic, margin=width/200, distance=width/20)
```

* Proxy-Status wird vor jedem Aufruf deaktiviert: `clip.proxy.build_50 = False`, `clip.use_proxy = False`
* `threshold` wird bei unzureichender Markeranzahl iterativ angepasst (max. 10 Versuche)
* `default_pattern_size` dynamisch, max. 100

#### 📊 Threshold-Formel (Feature Detection)

Wenn `marker_count < min_marker_count`, wird `threshold` wie folgt angepasst:

```python
threshold = max(threshold * ((marker_count + 0.1) / expected), 0.0001)
threshold = round(threshold, 5)
```

Dabei ist:

* `expected = min_marker_count * 4`
* `threshold_start = 1.0`
* `0.0001` = untere Grenze zur Vermeidung von Null/Negativwerten

Ziel: Empfindlichkeit steigt bei zu wenigen erkannten Features.

---

### 3. **Marker-Filterung**

```python
for track in clip.tracking.tracks:
    if distance(track, good_marker) < margin:
        track.marked_for_deletion = True
```

* Entfernt Marker nahe `GOOD_`-Markern
* Danach: automatische Umbenennung zu `TRACK_`

---

### 4. **Bidirektionales Tracking**

```python
bpy.ops.clip.track_markers(forward=True)
bpy.ops.clip.track_markers(backward=True)
```

* Tracking aller `TRACK_`-Marker mit Kontextoverride `context.temp_override()`
* UI-Override zwingend notwendig (da sonst `track_markers` nicht läuft)

---

### 5. **Löschen kurzer Tracks**

```python
track.markers → [marker.frame]
if max(frame) - min(frame) < min_track_length: → DELETE
```

---

### 6. **Re-Analyse**

```python
clip.tracking.tracks → active_marker_count_per_frame
if active < min_marker_count → sparse_frame = frame
```

Falls `sparse_frame` erneut auftritt:

```python
clip.tracking.settings.motion_model = next_model()
clip.tracking.settings.default_pattern_size *= 1.1
```

---

### 7. **Playhead setzen**

```python
context.scene.frame_current = sparse_frame
```

---

## 🧠 Zustandssteuerung (`scene.kaiserlich_tracking_state`)

```text
WAIT_FOR_PROXY
↓
DETECTING
↓
TRACKING
↓
CLEANUP
↓
REVIEW / LOOP
```

---

## 🛠️ Blender API Overview

| Aktion                | API                                              |
| --------------------- | ------------------------------------------------ |
| Proxy prüfen          | `clip.proxy.build_50`, `clip.use_proxy`          |
| Features erkennen     | `bpy.ops.clip.detect_features()`                 |
| Marker zählen         | `len(clip.tracking.tracks)`                      |
| Tracking auslösen     | `bpy.ops.clip.track_markers()`                   |
| Kontext setzen        | `context.temp_override()`                        |
| Pattern Size setzen   | `clip.tracking.settings.default_pattern_size`    |
| Motion Model wechseln | `clip.tracking.settings.motion_model = 'Affine'` |
| Tracks löschen        | `clip.tracking.tracks.remove(...)`               |
| Playhead setzen       | `context.scene.frame_current = frame`            |

---

## 🔧 Debug-Logging

```python
from .tracker_logger import TrackerLogger
logger = TrackerLogger(debug=True)
logger.info(), logger.warn(), logger.error(), logger.debug()
```

---

## 🔐 Sicherheitslogik

* **Abbruchbedingungen** bei:

  * Timeout Proxy
  * Kein Clip gefunden
* **Grenzwerte**:

  * `threshold >= 0.0001`
  * `pattern_size <= 100`
* **Fallback-Property-Zugriffe**:

  ```python
  getattr(scene, "min_marker_count", 10)
  ```
* **Blender Version/Attributprüfung**:

  ```python
  if hasattr(settings, "motion_model"):
  ```

---

## ✅ Voraussetzungen

* Blender ≥ 4.0
* Movie Clip Editor aktiv
* Clip muss Frames beinhalten
* Proxy darf existieren, wird aber zur Erkennung deaktiviert

---

## 🧹 Integrationsempfehlung

* `__init__.py` muss **alle Module explizit importieren**, z. B.:

  ```python
  from .tracksycle_operator import KAISERLICH_OT_auto_track_cycle
  ```

* UI-Integration via:

  ```python
  layout.operator("kaiserlich.auto_track_cycle", text="Auto Track")
  ```

---

## 🧹 UI-Integration (Blender Sidebar)

### Panel: `KAISERLICH_PT_tracking_tools`

| UI-Element                     | Typ               | Property                      | Tooltip Beschreibung                                              |
| ------------------------------ | ----------------- | ----------------------------- | ----------------------------------------------------------------- |
| **Auto Track starten**         | Button (Operator) | `kaiserlich.auto_track_cycle` | Startet den automatischen Tracking-Zyklus                         |
| **Minimale Markeranzahl**      | `IntProperty`     | `scene.min_marker_count`      | Anzahl an erkannten Features, die mindestens erreicht werden soll |
| **Tracking-Länge (min)**       | `IntProperty`     | `scene.min_track_length`      | Minimale Anzahl Frames pro Marker                                 |
| **Fehler-Schwelle**            | `FloatProperty`   | `scene.error_threshold`       | Maximal tolerierter Reprojektionfehler                            |
| **🛠 Debug Output aktivieren** | `BoolProperty`    | `scene.debug_output`          | Aktiviert ausführliches Logging zur Fehleranalyse                 |

### Panel-Position in Blender:

* Editor: **Movie Clip Editor**
* Region: **Sidebar (N)**
* Tab: **„Kaiserlich“**
* Kontext: `space_data.type == 'CLIP_EDITOR'`

---

## Lizenz

Dieses Projekt steht unter der [MIT-Lizenz](LICENSE).
