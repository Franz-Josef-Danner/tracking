Verstanden. Du erwartest ein präzises, technisches `README.md` – mit Ablaufbeschreibung auf Codeebene, verwendeten Blender-APIs, Zustandslogik und Entwicklerinformationen. Hier die überarbeitete Fassung mit **technischer Tiefe**, **Modulstruktur**, **Zustandsdiagramm** und **API-Referenzen**:

---

# 📽️ Kaiserlich Tracksycle – Technisches README

Ein automatisierter Tracking-Zyklus für Blender (ab 4.0), entwickelt zur robusten Feature-Erkennung und bidirektionalen Marker-Nachverfolgung mit dynamischer Reaktion auf Markerqualität, Proxystatus und Trackingfehler.

---

## 🗂️ Struktur

```
kaiserlich_tracksycle/
├── __init__.py
├── tracksycle_operator.py        # Hauptzyklus (Execute)
├── distance_remove.py            # Entfernt Marker nahe GOOD_
├── track.py                      # BIDIR Tracking aller TRACK_-Marker
├── track_length.py               # Löscht Tracks unter min. Länge
├── find_frame_with_few_tracking_markers.py
├── set_playhead.py               # Playhead-Positionierung
├── motion_model.py               # Motion-Model-Cycling
├── tracker_logger.py             # Konfigurierbares Logging
```

---

## 🧭 Ablaufplan (Operator: `KAISERLICH_OT_auto_track_cycle`)

### 1. **Proxy-Handling**

```python
proxy_path = os.path.join(clip.directory, "BL_proxy", clip.name + ".avi")
os.path.exists(proxy_path)
clip.use_proxy = False
clip.proxy.build_50 = False
```

Wartezeit: 5 Minuten (Polling alle 5s). Danach Abbruch mit UI-Fehlermeldung.

---

### 2. **Detect Features**

```python
bpy.ops.clip.detect_features(threshold=dynamic, margin=width/200, distance=width/20)
```

* `threshold` wird bei unzureichender Markeranzahl iterativ angepasst (max. 10 Versuche).
* `default_pattern_size` dynamisch, max. 100.

---

### 3. **Marker-Filterung**

```python
for track in clip.tracking.tracks:
    if distance(track, good_marker) < margin:
        track.marked_for_deletion = True
```

Entfernt Marker nahe `GOOD_`-Markern. Danach Umbenennung in `TRACK_`.

---

### 4. **Bidirektionales Tracking**

```python
bpy.ops.clip.track_markers(forward=True)
bpy.ops.clip.track_markers(backward=True)
```

* Tracking aller `TRACK_`-Marker.
* Kontextoverride über `context.temp_override()`.

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

## 🧰 Blender API Overview

| Aktion                | API                                              |
| --------------------- | ------------------------------------------------ |
| Proxy prüfen          | `clip.proxy.build_50`, `clip.use_proxy`          |
| Features erkennen     | `bpy.ops.clip.detect_features()`                 |
| Marker zählen         | `len(clip.tracking.tracks)`                      |
| Tracking auslösen     | `bpy.ops.clip.track_markers()`                   |
| Kontext setzen        | `context.temp_override()`                        |
| Pattern Size setzen   | `clip.tracking.settings.default_pattern_size`    |
| Motion Model wechseln | `clip.tracking.settings.motion_model = 'Affine'` |
| Tracks löschen        | manuell via `clip.tracking.tracks.remove(...)`   |
| Playhead setzen       | `context.scene.frame_current = frame`            |

---

## 🛠 Debug-Logging

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

---

## ✅ Voraussetzungen

* Blender ≥ 4.0
* Movie Clip Editor aktiv
* Clip muss Frames beinhalten
* Proxy darf existieren, wird aber zur Erkennung deaktiviert

---

## 🧩 Integrationsempfehlung

* `__init__.py` muss **alle Module explizit importieren**, z. B.:

  ```python
  from .tracksycle_operator import KAISERLICH_OT_auto_track_cycle
  ```

* Einfache UI-Integration:

  ```python
  layout.operator("kaiserlich.auto_track_cycle", text="Auto Track")
  ```

* Panel im Clip-Editor:

  Ein neues Panel **"Kaiserlich Tracker"** erscheint rechts im Clip Editor. Es enthält drei Eingabefelder ("Min Marker Count", "Min Track Length", "Detect Threshold") und einen **Start**-Button, der den Operator `kaiserlich.auto_track_cycle` ausführt.

