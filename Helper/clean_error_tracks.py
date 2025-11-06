# Helper/clean_error_tracks.py
# Zweck: Sichere Hülle um bpy.ops.clip.clean_error mit zuverlässigem Fallback.
#        Wenn kein gültiger Schwellenwert ermittelt werden kann -> threshold = 20.0

import math
import bpy

DEFAULT_CLEAN_ERROR = 20.0  # Harte Vorgabe laut Anforderung

def _coerce_threshold(value) -> float:
    """Konvertiert beliebige Eingaben in einen nutzbaren float-Threshold.
    Fallback: DEFAULT_CLEAN_ERROR (20.0), wenn None/NaN/inf/<=0.
    """
    try:
        thr = float(value)
    except (TypeError, ValueError):
        return DEFAULT_CLEAN_ERROR

    if not math.isfinite(thr) or thr <= 0.0:
        return DEFAULT_CLEAN_ERROR
    return thr


def clean_error_tracks(
    context: bpy.types.Context,
    threshold: float | None = None,
    action: str = 'DELETE_TRACK'
) -> None:
    """
    Führt bpy.ops.clip.clean_error kontext-sicher aus.
    Fallback-Policy: threshold -> 20.0, wenn value ungültig.

    Args:
        context: beliebiger Blender-Kontext (Operator/Modal/UI)
        threshold: gewünschter Grenzwert; None/NaN/inf/≤0 -> 20.0
        action: 'DELETE_TRACK' | 'DELETE_SEGMENTS' | 'SELECT'
    """
    thr = _coerce_threshold(threshold)

    # --- CLIP_EDITOR suchen ---
    area = None
    region = None
    space = None

    # a) aktueller Kontext bereits CLIP_EDITOR?
    if getattr(context, "area", None) and getattr(context.area, "type", "") == "CLIP_EDITOR":
        area = context.area
        region = next((r for r in area.regions if r.type == "WINDOW"), None)
        space  = area.spaces.active if area.spaces else None

    # b) sonst ersten CLIP_EDITOR im aktiven Screen nehmen
    if area is None:
        for a in bpy.context.screen.areas:
            if a.type == "CLIP_EDITOR":
                area = a
                region = next((r for r in a.regions if r.type == "WINDOW"), None)
                space  = a.spaces.active if a.spaces else None
                break

    if not all([area, region, space]):
        print("[CleanErrorTracks] ❌ Kein CLIP_EDITOR-Kontext gefunden.")
        return

    clip = getattr(space, "clip", None)
    if clip is None:
        print("[CleanErrorTracks] ❌ Kein aktiver MovieClip im Space vorhanden.")
        return

    # --- Operator sicher ausführen ---
    try:
        total_before = 0
        try:
            total_before = sum(len(obj.tracks) for obj in clip.tracking.objects)
        except Exception:
            total_before = len(getattr(clip.tracking, "tracks", []))
        print(f"[CleanErrorTracks] 🔍 Vorbereitungen:")
        print(f"  ↳ area={area}, region={region}, space={space}")
        print(f"  ↳ window={getattr(bpy.context, 'window', None)}, screen={getattr(getattr(bpy.context, 'window', None), 'screen', None)}")
        print(f"  ↳ Clip='{clip.name}', Tracks gesamt (vorher)={total_before}")
        print(f"  ↳ Action={action}, Threshold={thr:.4f}")
        print(f"[CleanErrorTracks] 🧹 clean_error() wird gestartet …")

        # 🪟 Sicherstellen, dass ein Clip-Editor-Fenster existiert
        if not any(a.type == 'CLIP_EDITOR' for a in bpy.context.window.screen.areas):
            print("[CleanErrorTracks] 🪟 Kein CLIP_EDITOR offen – öffne temporäres Fenster.")
            bpy.ops.screen.userpref_show('INVOKE_DEFAULT')
            win = bpy.context.window_manager.windows[-1]
            scr = win.screen
            scr.areas[0].type = 'CLIP_EDITOR'
            temp_window_used = True
        else:
            win = bpy.context.window
            scr = win.screen
            temp_window_used = False
        print(f"[CleanErrorTracks][DBG] Fenster/Screens:")
        print(f"  ↳ win={win}, scr={scr}, areas={len(scr.areas)}")

        area = next((a for a in scr.areas if a.type == 'CLIP_EDITOR'), None)
        if area is None:
            raise RuntimeError("[CleanErrorTracks] Kein CLIP_EDITOR in aktuellem Screen gefunden.")
        region = next((r for r in area.regions if r.type == 'WINDOW'), None)
        if region is None:
            raise RuntimeError("[CleanErrorTracks] Keine WINDOW-Region im CLIP_EDITOR gefunden.")
        space = area.spaces.active
        if space is None:
            raise RuntimeError("[CleanErrorTracks] Keine aktive Space im CLIP_EDITOR.")
        space.clip = clip
        if space.clip is None:
            raise RuntimeError("[CleanErrorTracks] space.clip ist None nach Zuweisung.")
        print(f"[CleanErrorTracks][DBG] Clip-Editor ready → area={area}, region={region}, space={space}, clip={space.clip}")
        # 🔁 Sicherer Kontext
        with bpy.context.temp_override(window=win, screen=scr, area=area, region=region, space_data=space, edit_movieclip=clip):
            result = bpy.ops.clip.clean_error(clean_error=thr, action=action)
            print(f"[CleanErrorTracks] ✅ Operator ausgeführt (Result={result}).")

        try:
            total_after = sum(len(obj.tracks) for obj in clip.tracking.objects)
        except Exception:
            total_after = len(getattr(clip.tracking, "tracks", []))
        print(f"[CleanErrorTracks] 📊 Tracks nach clean_error: {total_after} (Δ={total_before - total_after})")
        # 🧹 Fenster wieder schließen, falls es nur temporär geöffnet wurde
        if temp_window_used:
            try:
                bpy.ops.wm.window_close({'window': win})
                print("[CleanErrorTracks] 🪟 Temporäres Fenster geschlossen.")
            except Exception as wc_ex:
                print(f"[CleanErrorTracks] ⚠️ Fenster-Schließung fehlgeschlagen: {wc_ex}")

    except Exception as e:
        print(f"[CleanErrorTracks] ❌ Fehler bei clean_error: {e}")
