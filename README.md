---

# 🍴 Kaiserlich Tracksycle – Technisches README

Ein automatisierter Tracking-Zyklus für Blender (ab 4.0), entwickelt zur robusten Feature-Erkennung und bidirektionalen Marker-Nachverfolgung mit dynamischer Reaktion auf Markerqualität, Proxystatus und Trackingfehler.

---

## 📂 Struktur

```

__init__.py
modules/                      # Unterordner für logische Trennung
├── __init__.py
├── operators/
├── __init__.py
│   └── tracksycle_operator.py
├── proxy/
│   ├── __init__.py
│   └── proxy_wait.py
├── detection/
│   ├── __init__.py
│   ├── distance_remove.py
│   └── find_frame_with_few_tracking_markers.py
├── tracking/
│   ├── __init__.py
│   ├── track.py
│   ├── motion_model.py
│   └── track_length.py
├── playback/
│   ├── __init__.py
│   └── set_playhead.py
├── util/
│   ├── __init__.py
│   └── tracker_logger.py
└── ui/
    ├── __init__.py
    └── kaiserlich_panel.py
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
## 🚀 Nutzung

1. Öffne den Movie Clip Editor in Blender und lade einen Clip.
2. Wechsle in der Sidebar zum Tab "Kaiserlich".
3. Stelle die gewünschten Parameter ein (siehe Abschnitt "Parameter").
4. Klicke auf **Auto Track starten**, um den Tracking-Zyklus zu beginnen.

### Tracking-Zyklus in Kürze

Der Operator `KAISERLICH_OT_auto_track_cycle` durchläuft automatisch folgende Schritte:

1. Entfernen vorhandener Proxy-Dateien und Erzeugen eines neuen 50%-Proxys.
2. Feature-Erkennung mit dynamisch angepasstem Threshold, bis die Markeranzahl im Bereich von 80‑120 % von `min_marker_count * 4` liegt.
3. Bereinigung und Umbenennung der Marker zu `TRACK_*`.
4. Bidirektionales Tracking aller Marker.
5. Löschen zu kurzer Tracks basierend auf `min_track_length`.
6. Optionales Nachjustieren von Motion Model und Pattern Size, falls zu wenige Marker vorhanden sind.
7. Setzen des Playheads auf einen Frame mit wenig Markern und Ausgabe der Abschlusmeldung.

## 🧩 Kernstellen der Blender-Kommunikation

Mehrere Funktionen greifen direkt über die `bpy`‑API auf Blender zu:

1. **Registrierung und Properties** – Im Wurzel-`__init__.py` werden alle Operator‑ und Panelklassen mittels `bpy.utils.register_class` registriert und Szenen‑Properties wie `Scene.min_marker_count` definiert.
2. **Proxy-Erstellung und UI-Overrides** – `KAISERLICH_OT_auto_track_cycle.execute()` aktiviert die Proxy-Einstellungen und ruft mit `context.temp_override(...)` `bpy.ops.clip.rebuild_proxy()` auf.
3. **Asynchroner Ablauf über Timer** – Während der Proxy erstellt wird, überwacht der Operator im Modalmodus per `wm.event_timer_add` das Auftauchen der Proxy-Datei.
4. **Feature-Erkennung im gültigen UI-Kontext** – `detect_features_in_ui_context` sucht nach einem Clip-Editor-Bereich und führt dort `bpy.ops.clip.detect_features()` aus.
5. **Direkter Aufruf ohne Proxy** – `detect_features_no_proxy` schaltet `clip.use_proxy` aus und startet die Erkennung sofort.
6. **Timer-basierte, wiederholte Erkennung** – `detect_features_async` registriert sich mit `bpy.app.timers.register`, um die Erkennung mehrfach zu wiederholen, bis genügend Marker gefunden wurden.

## 🔄 Ablauf: Start bis Feature-Erkennung

1. Nach dem Klick auf **Auto Track starten** prüft `KAISERLICH_OT_auto_track_cycle`, ob im Movie‑Clip‑Editor ein Clip geladen ist. Fehlt dieser, wird der Operator abgebrochen.
2. Der Logger wird eingerichtet, `scene.proxy_built` zurückgesetzt und diverse Proxy-Flags am Clip aktiviert. Alte Proxy-Dateien im Zielordner werden entfernt.
3. Mit einem UI-Override wird `bpy.ops.clip.rebuild_proxy()` gestartet. Der Operator merkt sich die erwarteten Proxy-Dateipfade, setzt `scene.kaiserlich_tracking_state` auf `WAIT_FOR_PROXY` und registriert einen Timer.
4. In der `modal`‑Methode prüft jeder Timer-Event, ob die Proxy-Datei existiert. Bei Erfolg wird der Timer entfernt, `clip.use_proxy` deaktiviert, `scene.proxy_built` auf `True` gesetzt und der Status auf `DETECTING` geändert.
5. Anschließend ruft der Operator `detect_features_in_ui_context()` auf. Diese Funktion führt die Marker-Erkennung im Clip‑Editor-Kontext mit den übergebenen Parametern aus.

---

## ⚙️ Parameter

| Property | Beschreibung |
| -------- | ------------ |
| `scene.min_marker_count` | Mindestanzahl erkannter Marker, ab der das Tracking fortgeführt wird. |
| `scene.min_track_length` | Minimale Länge eines Tracks in Frames, damit er nicht gelöscht wird. |
| `scene.error_threshold`  | Maximal erlaubter Reprojektionfehler (für zukünftige Prüfungen nutzbar). |
| `scene.debug_output`     | Aktiviert detaillierte Log-Ausgaben im Terminal. |

---

## 🏗 Wichtige Proxy-Funktionen

Aus `modules.proxy.proxy_wait` stammen die Helfer zur Proxy-Erstellung. Das
Herzstück bildet `create_proxy_and_wait_async`:

```python
def create_proxy_and_wait_async(clip, callback=None, timeout=300, logger=None):
    clip.use_proxy = True
    clip.use_proxy_custom_directory = True
    clip.proxy.build_50 = True
    override = {"clip": clip}
    override.update(_get_clip_editor_override())
    bpy.ops.clip.rebuild_proxy(override)
    bpy.app.timers.register(_wait_for_proxy)
```

Startet die Proxy-Erstellung und registriert einen Timer, der auf die fertige
Datei wartet. Nach Abschluss kann optional `callback` ausgeführt werden.

```python
def wait_for_proxy_and_trigger_detection(clip, proxy_path, threshold=1.0,
                                         margin=0, min_distance=0,
                                         placement="FRAME", logger=None):
    def wait_loop():
        for _ in range(300):
            if os.path.exists(proxy_path):
                bpy.app.timers.register(
                    lambda: detect_features_in_ui_context(
                        threshold, margin, min_distance, placement, logger
                    ),
                    first_interval=0.1,
                )
                return
```

Überwacht das angegebene Proxy-File und startet anschließend die
Feature-Erkennung im Clip-Editor.

## 🔍 Wichtige Detect-Funktionen

Im Paket `modules.detection` befinden sich die Routinen für die eigentliche
Marker-Erkennung:

```python
def detect_features_no_proxy(clip, threshold=1.0, margin=None,
                             min_distance=None, logger=None):
    clip.proxy.build_50 = False
    clip.use_proxy = False
    bpy.ops.clip.detect_features(
        threshold=threshold,
        margin=margin,
        min_distance=min_distance,
    )
```

Führt die Erkennung ohne aktivierte Proxys aus.

```python
from modules.util.tracking_utils import count_markers_in_frame
def detect_features_async(scene, clip, logger=None, attempts=10):
    state = {"attempt": 0, "threshold": 1.0}
    def _step():
        detect_features_no_proxy(
            clip,
            threshold=state["threshold"],
            margin=clip.size[0] / 200,
            min_distance=int(clip.size[0] / 20),
            logger=logger,
        )
        marker_count = count_markers_in_frame(
            clip.tracking.tracks, scene.frame_current
        )
        state["threshold"] = max(
            round(state["threshold"] * ((marker_count + 0.1) / state["expected"]), 5),
            0.0001,
        )
    bpy.app.timers.register(_step)
```

Wiederholt die Erkennung asynchron und passt dabei Threshold sowie Pattern Size
dynamisch an.

---

## 🗂 Ablaufplan (Operator: `KAISERLICH_OT_auto_track_cycle`)

### 1. **Proxy-Handling (async)**

```python
from modules.proxy.proxy_wait import create_proxy_and_wait_async
```

* Entfernt zuvor generierte Proxy-Dateien via `remove_existing_proxies()`
* Erstellt 50%-Proxy in `proxies/`
* Aktiviert `clip.use_proxy = True` vor der Proxy-Erstellung
* Wartet asynchron mit Timer auf erste Proxy-Datei (`proxy_50.avi`, max. Timeout: 300s)
* Nutzt Dateigrößen-Prüfung zur Validierung abgeschlossener Proxy-Erstellung
* Implementiert überarbeitetes und stabiles Verfahren laut `proxy_wait (1).py`

#### ✨ Besonderheiten der stabilen Version

* Separate Thread-Logik zur Dateiprüfung
* Fehlerbehandlung via Logging
* Proxy-Pfad-Validierung (Existenz & Schreibrechte)
* Fehlender Proxy-Ordner wird automatisch angelegt
* Custom-Verzeichnis aktivieren via `clip.use_proxy_custom_directory = True`
* Sauberes Abbrechen nach Timeout
* ✉ Referenzdatei: `proxy_wait (1).py`

#### Proxy-Status abfragen

```python
import bpy

space = bpy.context.space_data
if space and space.type == 'CLIP_EDITOR':
    clip = space.clip
    if clip:
        if clip.use_proxy:
            print(f"[Proxy] Clip \"{clip.name}\" ist AKTIV (use_proxy=True)")
            p = clip.proxy
            print(
                f" \u2192 build_25: {p.build_25}, build_50: {p.build_50}, "
                f"build_75: {p.build_75}, build_100: {p.build_100}"
            )
        else:
            print(f"[Proxy] Clip \"{clip.name}\" ist INAKTIV (use_proxy=False)")
    else:
        print("[Proxy] Kein Clip im Editor ausgewählt.")
else:
    print("[Proxy] Script läuft nicht im Movie Clip Editor.")
```

---

### 2. **Detect Features**

```python
bpy.ops.clip.detect_features(threshold=dynamic, margin=width/200, min_distance=width/20)
```

* Proxy-Status wird vor jedem Aufruf deaktiviert: `clip.proxy.build_50 = False`, `clip.use_proxy = False`
* `threshold` wird bei unzureichender Markeranzahl iterativ angepasst (max. 10 Versuche)
* `default_pattern_size` dynamisch, max. 100
* Optionales Debug-Logging via `detect_features_no_proxy(..., logger=TrackerLogger())`
* Bei sehr großen Clips kann `detect_features_async` genutzt werden, um die Erkennung per Timer zu unterteilen

#### 📊 Threshold-Formel (Feature Detection)

Wenn `marker_count < min_marker_count`, wird `threshold` wie folgt angepasst:

```python
threshold = max(threshold * ((marker_count + 0.1) / expected), 0.0001)
threshold = round(threshold, 5)
```

Dabei ist:

* `expected = min_marker_count * 4`
* Der Detection-Loop endet, sobald `marker_count` zwischen `expected * 0.8` und `expected * 1.2` liegt.
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
active = count_markers_in_frame(clip.tracking.tracks, frame)
if active < min_marker_count:
    sparse_frame = frame
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
| Marker zählen         | `count_markers_in_frame(clip.tracking.tracks, frame)` |
| Tracking auslösen     | `bpy.ops.clip.track_markers()`                   |
| Kontext setzen        | `context.temp_override()`                        |
| Pattern Size setzen   | `clip.tracking.settings.default_pattern_size`    |
| Motion Model wechseln | `clip.tracking.settings.motion_model = 'Affine'` |
| Tracks löschen        | `track = clip.tracking.tracks.get(name)`<br>`safe_remove_track(track)` |
| Playhead setzen       | `context.scene.frame_current = frame`            |

> **Hinweis:** Direktes Entfernen über `clip.tracking.tracks.remove()` wird ab Blender 4.4+ nicht mehr unterstützt. Verwende `safe_remove_track` oder `bpy.ops.clip.track_remove()`.

---

## 🔧 Debug-Logging

```python
from modules.util.tracker_logger import TrackerLogger, configure_logger

configure_logger(debug=True, log_file="tracksycle.log")
logger = TrackerLogger()
logger.info(), logger.warning(), logger.error(), logger.debug()
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

* **Event-Validierung vor Verarbeitung**:

  ```python
  if event.type in bpy.types.Event.bl_rna.properties["type"].enum_items.keys():
      pass
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

