import bpy
import math
from ..Helper.bootstrap import run_bootstrap
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.detect import detect_features
from ..Helper.newmarker import classify_markers
from ..Helper.cleaneup import cleanup_new_markers
from ..Helper.delete import delete_tracks_by_names
from ..Helper.marker_size import apply_marker_sizes


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


class KAISERLICHTRACKER_OT_detect_cycle(bpy.types.Operator):
    bl_idname = "kaiserlich_tracker.detect_cycle"
    bl_label = "Detect Zyklus (angepasst)"
    bl_description = (
    "Iterativer Zyklus gemäß Vorgabe: Bootstrap -> Detect -> Klassifikation -> ug/og Logik mit tr*2, "
    "Pattern-Reduktion, md-Anpassung, dynamische za/og/ug-Anpassung und Lösch-Strategie."
    )
    bl_options = {"REGISTER", "INTERNAL"}

    max_iterations: bpy.props.IntProperty(  # type: ignore
        name="Max Iterationen",
        default=0,
        min=0,
        soft_max=200,
        description="0 oder kleiner = kein Limit; Sicherheitsbremse für Endlosschleifen"
    )

    def execute(self, context):  # noqa: C901 (Komplexität hier akzeptiert wegen klarer Ablaufabbildung)
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

        # Baseline vor Start
        baseline = snapshot_active_markers(context)
        baseline_start_count = len(baseline)

        print("[Kaiserlich Tracker] ================ Neuer Detect Zyklus Start ================")
        print(f"[Kaiserlich Tracker] ug={ug} og={og} za={za:.2f} | Start md={md:.2f} tr={tr:.3f} pz={pz} sz={sz}")

        iterations = 0
        accepted = False
        total_deleted_cleanup = 0

        while (self.max_iterations <= 0) or (iterations < self.max_iterations):
            iterations += 1
            print(f"[Kaiserlich Tracker] ---- Iteration {iterations} ---- tr={tr:.4f} md={md:.2f} pz={pz} sz={sz} za={za:.2f}")

            # Snapshot vor Detect
            pre_snapshot = snapshot_active_markers(context)

            # Detect mit aktuellen Parametern
            detect_features(
                context,
                placement='FRAME',
                margin=ma,
                threshold=tr,
                min_distance=int(max(1, round(md)))
            )

            # Snapshot nach Detect
            post_snapshot = snapshot_active_markers(context)
            alte_marker, neue_marker = classify_markers(pre_snapshot, post_snapshot)
            am = len(neue_marker)
            print(f"[Kaiserlich Tracker] Neue Marker am={am}")

            # Entscheidungslogik gemäß korrigierter Spezifikation
            if am >= ug:
                if am <= og:
                    print(f"[Kaiserlich Tracker] Korridor: {ug} <= {am} <= {og}")
                    # Cleanup mit neuen & alten Markern
                    cleaned_new, deleted_old = cleanup_new_markers(
                        context,
                        alte_marker,
                        neue_marker,
                        md=md,
                        hz=hz,
                        vc=vc
                    )
                    total_deleted_cleanup += deleted_old
                    print(f"[Kaiserlich Tracker] Cleanup: {deleted_old} alte Tracks gelöscht; verbleibend neue={len(cleaned_new)}")
                    # Threshold verdoppeln
                    tr *= 2.0
                    print(f"[Kaiserlich Tracker] tr -> {tr:.4f} (verdoppelt)")
                    if tr > 1.0:
                        print("[Kaiserlich Tracker] tr > 1 -> Fertig")
                        # Akzeptiere bereinigte neue Marker
                        baseline = pre_snapshot + cleaned_new
                        accepted = True
                        break
                    else:
                        # Neue Vorgabe: za im Korridor bei Fortsetzung reduzieren und og/ug neu berechnen
                        za *= 0.82
                        og = math.ceil(za * 1.1)
                        ug = math.floor(za * 0.9)
                        print(f"[Kaiserlich Tracker] za reduziert (Korridor Fortsetzung): za={za:.4f} -> og={og} ug={ug}")
                        # Pattern Größen reduzieren
                        pz = max(1, int(round(pz * 0.3)))
                        sz = pz * 2
                        apply_marker_sizes(context.space_data.clip if getattr(context, 'space_data', None) else None, pz, sz)
                        print(f"[Kaiserlich Tracker] Pattern/Search reduziert: pz={pz} sz={sz}")
                        # Baseline erweitern um akzeptierte neue Marker
                        baseline = pre_snapshot + cleaned_new
                        continue
                else:
                    # am > og
                    print(f"[Kaiserlich Tracker] Über OG: am={am} > og={og}")
                    # Einheitliche md-Formel (wie vorgegeben)
                    if am > 0:
                        denom = max(0.8, min(1.25, (za / am)))
                    else:
                        denom = 0.8
                    if denom == 0:
                        denom = 0.0001
                    md = md / denom
                    print(f"[Kaiserlich Tracker] md angepasst (über OG): {md:.4f} (denom={denom:.4f})")
                    # Neue Marker löschen
                    if neue_marker:
                        names = [m['track'] for m in neue_marker]
                        removed = delete_tracks_by_names(context, names)
                        print(f"[Kaiserlich Tracker] {removed} neue Tracks gelöscht (über OG)")
                    # Baseline bleibt pre_snapshot (da neue verworfen)
                    baseline = pre_snapshot
                    continue
            else:
                # am < ug
                print(f"[Kaiserlich Tracker] Unter UG: am={am} < ug={ug}")
                if am > 0:
                    denom = max(0.8, min(1.25, (za / am)))
                else:
                    denom = 0.8
                if denom == 0:
                    denom = 0.0001
                md = md / denom
                print(f"[Kaiserlich Tracker] md angepasst (unter UG): {md:.4f} (denom={denom:.4f})")
                if neue_marker:
                    names = [m['track'] for m in neue_marker]
                    removed = delete_tracks_by_names(context, names)
                    print(f"[Kaiserlich Tracker] {removed} neue Tracks gelöscht (unter UG)")
                baseline = pre_snapshot
                continue

            # Sicherheits-Fall
            print("[Kaiserlich Tracker] Warnung: Kein Regelpfad aktiv – Abbruch.")
            break

        else:
            # while-end (Iterationslimit erreicht)
            if self.max_iterations > 0:
                print(f"[Kaiserlich Tracker] Iterationslimit ({self.max_iterations}) erreicht – Abbruch.")

        final_snapshot = snapshot_active_markers(context)
        final_total = len(final_snapshot)
        added_effective = final_total - baseline_start_count
        status = "Abgeschlossen" if accepted else ("Limit erreicht" if (self.max_iterations > 0 and iterations >= self.max_iterations) else "Abbruch")
        self.report({'INFO'}, (
            f"{status}: Iterationen={iterations} | Effektiv hinzugefügt={added_effective} | md={md:.2f} | tr={tr:.4f} | pz={pz} | Gelöschte alte Tracks im Cleanup={total_deleted_cleanup} | Gesamt Marker (Ende)={final_total}"
        ))
        print("[Kaiserlich Tracker] ================ Detect Zyklus Ende ==================")
        return {'FINISHED'}
