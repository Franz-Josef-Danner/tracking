---

# 🍴 Kaiserlich Tracksycle – Technisches README

Ein automatisierter Tracking-Zyklus für Blender (ab 4.0), entwickelt zur robusten Feature-Erkennung und bidirektionalen Marker-Nachverfolgung mit dynamischer Reaktion auf Markerqualität, Proxystatus und Trackingfehler.

---

## 📂 Struktur

```
tracking_tracksycle/
├── __init__.py
├── modules/                      # Unterordner für logische Trennung
│   ├── __init__.py
│   ├── operators/
│   │   ├── __init__.py
│   │   └── tracksycle_operator.py
│   ├── proxy/
│   │   ├── __init__.py
│   │   └── proxy_wait.py
│   ├── detection/
│   │   ├── __init__.py
│   │   ├── distance_remove.py
│   │   └── find_frame_with_few_tracking_markers.py
│   ├── tracking/
│   │   ├── __init__.py
│   │   ├── track.py
│   │   ├── motion_model.py
│   │   └── track_length.py
│   ├── playback/
│   │   ├── __init__.py
│   │   └── set_playhead.py
│   ├── util/
│   │   ├── __init__.py
│   │   └── tracker_logger.py
│   └── ui/
│       ├── __init__.py
│       └── kaiserlich_panel.py
```

> **Hinweis:** Jeder Unterordner benötigt eine `__init__.py`, um als Modul erkannt zu werden.

### Aufbau eines `__init__.py`

Die `__init__.py`-Dateien innerhalb der Subfolder können minimalistisch sein, z. B.:

```python
# modules/detection/__init__.py
# Ermöglicht Modulimport wie: from modules.detection import distance_remove
```

Optional (für explizite Exporte):

```python
from .distance_remove import *
from .find_frame_with_few_tracking_markers import *
```

Im Stamm-`__init__.py` erfolgt der Hauptimport:

```python
from .modules.operators.tracksycle_operator import KAISERLICH_OT_auto_track_cycle
```

## 🔗 Modulregistrierung in `__init__.py`

Damit das Add-on korrekt geladen wird, müssen alle relevanten Klassen in der Hauptdatei `__init__.py` wie folgt registriert werden:

```python
from .modules.operators.tracksycle_operator import KAISERLICH_OT_auto_track_cycle
from .modules.ui.kaiserlich_panel import KAISERLICH_PT_tracking_tools

classes = [
    KAISERLICH_OT_auto_track_cycle,
    KAISERLICH_PT_tracking_tools,
    # ggf. weitere Klassen...
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
```

Jedes Submodul ist in seinem eigenen Unterordner organisiert und wird dort durch ein eigenes `__init__.py` als Paketstruktur kenntlich gemacht. Diese Dateien können leer sein oder zusätzlich lokale `register()`-Funktionen definieren, wenn innerhalb des Pakets mehrere Klassen verwaltet werden.

Beispiel für ein leeres `__init__.py`:

```python
# erforderlich zur Modulinitialisierung
```

Alternativ mit Unterregistrierung:

```python
from .some_operator import SOME_OT_Class

def register():
    bpy.utils.register_class(SOME_OT_Class)

def unregister():
    bpy.utils.unregister_class(SOME_OT_Class)
```

---

## 🗂 Ablaufplan (Operator: `KAISERLICH_OT_auto_track_cycle`)

### 1. **Proxy-Handling (async)**

```python
from modules.proxy.proxy_wait import create_proxy_and_wait
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
* ✉ Referenzdatei: `proxy_wait (1).py`

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
🔻
DETECTING
🔻
TRACKING
🔻
CLEANUP
🔻
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
from modules.util.tracker_logger import TrackerLogger
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

* `__init__.py` im Add-on-Stammverzeichnis importiert aus Submodulen:

  ```python
  from .modules.operators.tracksycle_operator import KAISERLICH_OT_auto_track_cycle
  ```

* Jeder Unterordner benötigt eine `__init__.py` für Modulregistrierung

* Struktur für tiefe Imports:

  ```python
  from modules.detection.distance_remove import distance_remove
  ```

* UI-Integration via:

  ```python
  layout.operator("kaiserlich.auto_track_cycle", text="Auto Track")
  ```

* Bei Beendigung des gesamten Tracking-Zyklus erscheint die Meldung:
  „Es war sehr sch\u00f6n, es hat mich sehr gefreut."

---

## 🪺 UI-Integration (Blender Sidebar)

### Panel: `KAISERLICH_PT_tracking_tools`

| UI-Element                     | Typ               | Property                      | Tooltip Beschreibung                                              |
| ------------------------------ | ----------------- | ----------------------------- | ----------------------------------------------------------------- |
| **Auto Track starten**         | Button (Operator) | `kaiserlich.auto_track_cycle` | Startet den automatischen Tracking-Zyklus                         |
| **Minimale Markeranzahl**      | `IntProperty`     | `scene.min_marker_count`      | Anzahl an erkannten Features, die mindestens erreicht werden soll |
| **Tracking-Länge (min)**       | `IntProperty`     | `scene.min_track_length`      | Minimale Anzahl Frames pro Marker                                 |
| **Fehler-Schwelle**            | `FloatProperty`   | `scene.error_threshold`       | Maximal tolerierter Reprojektionfehler                            |
| **🔧 Debug Output aktivieren** | `BoolProperty`    | `scene.debug_output`          | Aktiviert ausführliches Logging zur Fehleranalyse                 |

### Panel-Position in Blender:

* Editor: **Movie Clip Editor**
* Region: **Sidebar (**\`\`**)**
* Tab: **„Kaiserlich“**
* Kontext: `space_data.type == 'CLIP_EDITOR'`

---

## 📄 Lizenz

Dieses Projekt steht unter der **MIT-Lizenz**. Siehe die Datei [LICENSE](LICENSE) für weitere Details.

