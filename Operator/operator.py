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

        # Annahmen für harte Grenzen der min_distance (md)
        # (User-Spezifikation nannte md_min / md_max nicht; wir leiten sie heuristisch aus Auflösung ab)
        md_min = max(1.0, hz * 0.002)   # ca. 0.2% der horizontalen Auflösung, mindestens 1 Pixel
        md_max = hz * 0.25              # maximal 25% der Breite

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
                        pz = max(1, int(round(pz * 0.875)))
                        sz = pz * 2
                        apply_marker_sizes(context.space_data.clip if getattr(context, 'space_data', None) else None, pz, sz)
                        print(f"[Kaiserlich Tracker] Pattern/Search reduziert: pz={pz} sz={sz}")
                        # Baseline erweitern um akzeptierte neue Marker
                        baseline = pre_snapshot + cleaned_new
                        continue
                else:
                    # am > og -> md-Anpassung über Regelkreis (eps/k/L/U/O/d/beta)
                    print(f"[Kaiserlich Tracker] Über OG: am={am} > og={og}")
                    eps  = 1.0
                    k    = 0.6
                    L    = 1.5
                    Ufac = 1.5  # max down factor per step
                    Ofac = 1.5  # max up factor per step
                    d    = 0.03 # deadband
                    beta = 0.3  # smoothing

                    r = (am + eps) / (za + eps)
                    if abs(r - 1.0) < d:
                        md_next = md
                        reason = "deadband"
                    else:
                        delta = max(-L, min(L, math.log(r)))
                        raw = md * math.exp(k * delta)
                        # Per-step caps
                        raw = max(md / Ufac, min(md * Ofac, raw))
                        # Harte Grenzen
                        raw = max(md_min, min(md_max, raw))
                        # Glättung
                        md_next = (1 - beta) * md + beta * raw
                        reason = f"delta={delta:.3f} raw={raw:.2f}"
                    print(f"[Kaiserlich Tracker] md Regel (über OG): md_alt={md:.2f} md_neu={md_next:.2f} r={r:.3f} ({reason})")
                    md = md_next
                    # Neue Marker verwerfen (löschen)
                    if neue_marker:
                        names = [m['track'] for m in neue_marker]
                        removed = delete_tracks_by_names(context, names)
                        print(f"[Kaiserlich Tracker] {removed} neue Tracks gelöscht (über OG)")
                    baseline = pre_snapshot
                    continue
            else:
                # am < ug -> md-Anpassung über gleiche Regel
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
