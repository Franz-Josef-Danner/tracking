import bpy
import math
from ..Helper.bootstrap import run_bootstrap
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.detect import detect_features
from ..Helper.newmarker import classify_markers
from ..Helper.cleaneup import cleanup_new_markers
from ..Helper.delete import delete_tracks_by_names

def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


class KAISERLICHTRACKER_OT_detect_cycle(bpy.types.Operator):
    bl_idname = "kaiserlich_tracker.detect_cycle"
    bl_label = "Detect Zyklus (vereinfacht)"
    bl_description = (
        "Iterativer Zyklus gemäß Vorgabe: Bootstrap → Detect → Klassifikation → Cleanup → "
        "md-basierte Selbstregelung (ohne Threshold- oder Pattern-Anpassung)."
    )
    bl_options = {"REGISTER", "INTERNAL"}

    max_iterations: bpy.props.IntProperty(  # type: ignore
        name="Max Iterationen",
        default=0,
        min=0,
        soft_max=200,
        description="0 oder kleiner = kein Limit; Sicherheitsbremse für Endlosschleifen"
    )

    def execute(self, context):
        scene = context.scene
        ef = scene.kaiserlich_markers_per_frame

        params = run_bootstrap(context, ef)
        if not params:
            self.report({'WARNING'}, "Bootstrap fehlgeschlagen")
            return {'CANCELLED'}

        # Parameter aus Bootstrap
        md = float(params['md'])
        ma = int(params['ma'])
        tr = float(params['tr'])
        za = float(params['za'])
        ug = int(params['ug'])
        og = int(params['og'])
        pz = int(params['pz'])
        sz = int(params['sz'])
        hz = params['hz']
        vc = params['vc']

        # Harte Grenzen für md
        md_min = max(1.0, hz * 0.002)
        md_max = hz * 0.25

        # Baseline vor Start
        baseline = snapshot_active_markers(context)
        baseline_start_count = len(baseline)
        baseline_start_tracknames = {m['track'] for m in baseline}

        print("[Kaiserlich Tracker] ================ Neuer Detect Zyklus Start ================")
        print(f"[Kaiserlich Tracker] ug={ug} og={og} za={za:.2f} | Start md={md:.2f} tr={tr:.3f} pz={pz} sz={sz}")

        iterations = 0
        accepted = False
        total_deleted_cleanup = 0

        while (self.max_iterations <= 0) or (iterations < self.max_iterations):
            iterations += 1
            print(f"[Kaiserlich Tracker] ---- Iteration {iterations} ---- md={md:.2f} tr={tr:.4f}")

            pre_snapshot = snapshot_active_markers(context)
            detect_features(
                context,
                placement='FRAME',
                margin=ma,
                threshold=tr,
                min_distance=int(max(1, round(md)))
            )
            post_snapshot = snapshot_active_markers(context)
            alte_marker, neue_marker = classify_markers(pre_snapshot, post_snapshot)
            am = len(neue_marker)
            print(f"[Kaiserlich Tracker] Neue Marker am={am}")

            # ===============================
            # Korridor erreicht → akzeptieren
            # ===============================
            if am >= ug and am <= og:
                print(f"[Kaiserlich Tracker] Korridor: {ug} <= {am} <= {og}")
                cleaned_new, deleted_old = cleanup_new_markers(
                    context,
                    alte_marker,
                    neue_marker,
                    pz=pz,
                    hz=hz,
                    vc=vc
                )
                total_deleted_cleanup += deleted_old
                print(f"[Kaiserlich Tracker] Cleanup: {deleted_old} alte Tracks gelöscht; verbleibend neue={len(cleaned_new)}")
                baseline = pre_snapshot + cleaned_new
                accepted = True
                break

            # ===================================
            # Über OG → md erhöhen (Marker zu dicht)
            # ===================================
            elif am > og:
                print(f"[Kaiserlich Tracker] Über OG: am={am} > og={og}")
                eps  = 1.0
                k    = 0.6
                L    = 1.5
                Ufac = 1.5
                Ofac = 1.5
                d    = 0.03
                beta = 0.3

                r = (am + eps) / (za + eps)
                if abs(r - 1.0) < d:
                    md_next = md
                    reason = "deadband"
                else:
                    delta = max(-L, min(L, math.log(r)))
                    raw = md * math.exp(k * delta)
                    raw = max(md / Ufac, min(md * Ofac, raw))
                    raw = max(md_min, min(md_max, raw))
                    md_next = (1 - beta) * md + beta * raw
                    reason = f"delta={delta:.3f} raw={raw:.2f}"
                print(f"[Kaiserlich Tracker] md Regel (über OG): md_alt={md:.2f} md_neu={md_next:.2f} r={r:.3f} ({reason})")
                md = md_next

                if neue_marker:
                    names = [m['track'] for m in neue_marker]
                    removed = delete_tracks_by_names(context, names)
                    print(f"[Kaiserlich Tracker] {removed} neue Tracks gelöscht (über OG)")
                baseline = pre_snapshot
                continue

            # ===================================
            # Unter UG → md verringern (Marker zu selten)
            # ===================================
            elif am < ug:
                print(f"[Kaiserlich Tracker] Unter UG: am={am} < ug={ug}")
                eps  = 1.0
                k    = 0.6
                L    = 1.5
                Ufac = 1.5
                Ofac = 1.5
                d    = 0.03
                beta = 0.3

                r = (am + eps) / (za + eps)
                if abs(r - 1.0) < d:
                    md_next = md
                    reason = "deadband"
                else:
                    delta = max(-L, min(L, math.log(r)))
                    raw = md * math.exp(k * delta)
                    raw = max(md / Ufac, min(md * Ofac, raw))
                    raw = max(md_min, min(md_max, raw))
                    md_next = (1 - beta) * md + beta * raw
                    reason = f"delta={delta:.3f} raw={raw:.2f}"
                print(f"[Kaiserlich Tracker] md Regel (unter UG): md_alt={md:.2f} md_neu={md_next:.2f} r={r:.3f} ({reason})")
                md = md_next

                if neue_marker:
                    names = [m['track'] for m in neue_marker]
                    removed = delete_tracks_by_names(context, names)
                    print(f"[Kaiserlich Tracker] {removed} neue Tracks gelöscht (unter UG)")
                baseline = pre_snapshot
                continue

            else:
                print("[Kaiserlich Tracker] Warnung: Kein Regelpfad aktiv – Abbruch.")
                break

        else:
            if self.max_iterations > 0:
                print(f"[Kaiserlich Tracker] Iterationslimit ({self.max_iterations}) erreicht – Abbruch.")

        # ===============================
        # Abschluss & Selektion neuer Tracks
        # ===============================
        final_snapshot = snapshot_active_markers(context)
        final_total = len(final_snapshot)
        added_effective = final_total - baseline_start_count

        clip = context.space_data.clip if getattr(context, 'space_data', None) else None
        selected_new_tracks = 0
        if clip and getattr(clip, 'tracking', None):
            tracking = clip.tracking
            new_tracks = [trk for trk in tracking.tracks if trk.name not in baseline_start_tracknames]
            try:
                for trk in tracking.tracks:
                    trk.select = False
                for new_trk in new_tracks:
                    new_trk.select = True
                selected_new_tracks = len(new_tracks)
                print(f"[Kaiserlich Tracker] Selektion: {selected_new_tracks} neue Tracks selektiert.")
            except Exception as e:
                print(f"[Kaiserlich Tracker] Selektion fehlgeschlagen: {e}")
        else:
            print("[Kaiserlich Tracker] Keine Clip/Tracking Daten für Selektion verfügbar.")

        status = "Abgeschlossen" if accepted else ("Limit erreicht" if (self.max_iterations > 0 and iterations >= self.max_iterations) else "Abbruch")
        self.report({'INFO'}, (
            f"{status}: Iterationen={iterations} | Effektiv hinzugefügt={added_effective} | "
            f"md={md:.2f} | tr={tr:.4f} | Gelöschte alte Tracks im Cleanup={total_deleted_cleanup} | "
            f"Gesamt Marker (Ende)={final_total} | Neue Tracks selektiert={selected_new_tracks}"
        ))

        print("[Kaiserlich Tracker] ================ Detect Zyklus Ende ==================")
        return {'FINISHED'}
