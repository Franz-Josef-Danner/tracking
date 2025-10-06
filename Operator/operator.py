import bpy
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
        "Neuer iterativer Zyklus gemäß Vorgabe: Bootstrap -> Detect -> Klassifikation -> (ug/og) Logik mit tr*2, "
        "Pattern-Reduktion, md-Anpassung und Lösch-Strategie."
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

            # Detect Schritt (mit aktuellen Parametern)
            detect_features(
                context,
                placement='FRAME',
                margin=ma,
                threshold=tr,
                min_distance=int(max(1, round(md)))
            )

            # Snapshot nach Detect
            after = snapshot_active_markers(context)
            alte_marker, neue_marker = classify_markers(baseline, after)
            am = len(neue_marker)
            print(f"[Kaiserlich Tracker] Anzahl neue Marker (roh) am={am}")

            # Entscheidungs-Logik
            if am >= ug:
                if am <= og:
                    print(f"[Kaiserlich Tracker] Korridor erreicht (ug <= am <= og): {ug} <= {am} <= {og}")
                    # Cleanup anwenden (Parameter md, hz, vc)
                    cleaned_new, deleted = cleanup_new_markers(
                        context,
                        alte_marker,
                        neue_marker,
                        md=md,
                        hz=hz,
                        vc=vc
                    )
                    total_deleted_cleanup += deleted
                    am_clean = len(cleaned_new)
                    print(f"[Kaiserlich Tracker] Cleanup: {deleted} alte Tracks entfernt; verbleibende neue Marker = {am_clean}")
                    # Threshold Verdoppeln
                    tr *= 2.0
                    print(f"[Kaiserlich Tracker] tr verdoppelt -> {tr:.4f}")
                    if tr > 1.0:
                        print("[Kaiserlich Tracker] tr > 1 -> Fertig (finished)")
                        # akzeptierte Marker in Baseline übernehmen
                        baseline.extend(cleaned_new)
                        accepted = True
                        break
                    else:
                        # Pattern Size Reduktion gemäß Vorgabe: pz = pz * 0.3
                        pz = max(1, int(round(pz * 0.3)))
                        sz = pz * 2
                        apply_marker_sizes(context.space_data.clip if getattr(context, 'space_data', None) else None, pz, sz)
                        print(f"[Kaiserlich Tracker] Pattern/Search reduziert: pz={pz} sz={sz}")
                        # Übernommene neue Marker zur Baseline hinzufügen, damit sie im nächsten Durchlauf als 'alte' gelten
                        if cleaned_new:
                            baseline.extend(cleaned_new)
                        # Zyklus fortsetzen
                        continue
                else:
                    # am > og (zu viele) -> za reduzieren & md anpassen & neue verwerfen
                    print(f"[Kaiserlich Tracker] Über OG: am={am} > og={og} -> za & md anpassen, neue verwerfen")
                    za *= 0.82  # Skalierung gemäß Vorgabe
                    # Formel (wie vorgegeben – bewusst wörtlich, auch wenn min/max Reihenfolge konstant wird)
                    denom = max(0.75, min(0.15, (za / am)))
                    if denom == 0:
                        denom = 0.0001
                    md = md / denom
                    print(f"[Kaiserlich Tracker] Neues md (über OG): {md:.4f} (denom={denom:.4f})")
                    # Neue Marker löschen (alle neuen Tracks), ohne sie zu behalten
                    if neue_marker:
                        names = [m['track'] for m in neue_marker]
                        removed = delete_tracks_by_names(context, names)
                        print(f"[Kaiserlich Tracker] {removed} neue Tracks gelöscht (über OG)")
                    # Kein Baseline-Update (da verworfen)
                    continue
            else:
                # am < ug (zu wenig) -> md Anpassung mit anderem Clamp-Bereich & neue verwerfen
                print(f"[Kaiserlich Tracker] Unter UG: am={am} < ug={ug} -> md anpassen, neue verwerfen")
                ratio = (za / am) if am > 0 else 1.0
                denom = max(-50.0, min(50.0, ratio))  # clamp [-50, 50]
                if denom == 0:
                    denom = 0.0001
                md = md / denom
                print(f"[Kaiserlich Tracker] Neues md (unter UG): {md:.4f} (ratio={ratio:.4f} denom={denom:.4f})")
                if neue_marker:
                    names = [m['track'] for m in neue_marker]
                    removed = delete_tracks_by_names(context, names)
                    print(f"[Kaiserlich Tracker] {removed} neue Tracks gelöscht (unter UG)")
                continue

            # Falls keiner der Pfade griff (sollte nicht passieren)
            print("[Kaiserlich Tracker] Warnung: Kein Regel-Pfad gegriffen – Abbruch zur Sicherheit.")
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
