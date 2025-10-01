# Kaiserlich Tracker

Dieses Add-on ("Kaiserlich Tracker") bietet mehrstufiges Feature-Seeding, Duplikat-/Cluster-Bereinigung und künftige Zielsteuerung (Marker per Frame). Nachfolgend die konzeptionellen Notizen / Roadmap:

0) Governance & KPIs

Seeds & Namespaces: Trial/ROI-Prefix, deterministische Sample-Frames.

Budgets: Zeit-Slice/ROI (Detect/Model-Eval), max. 1 Param-Move/10 Frames/Marker.

KPIs (solve-frei): Survival@10/30f, Corr-Median, Residual-RMS, Coverage (Tiles), Redundanz-Index (1/d_nn), Zeit/Frame.

Zielscore: gewichtet (Qualität vs. Speed), für Vergleiche und Preset-Lernen.

1) STRM (Spatio-Temporal Region Map)

Tiling (z. B. 4×6) → pro ROI: Texture-Score τ, Motion-Score v, Divergenz ϕ, Flicker-Proxy, Coverage-Löcher.

Clustering (optional): DBSCAN/HDBSCAN über (x̄,ȳ,v̄,τ̄,κ̄) → Bewegungsgruppen.

2) Startparameter pro ROI

Pattern p0: round_odd(diag/150) → clamp 9..41.

α (search/pattern): default 3; α↑ bei hoher Motion/Divergenz; α↓ bei stabil/zeitkritisch.
→ search0 = round_even(α·p0), Limit ≤ 0.12·min(width,height).

Channel default: Y (Luma).

3) Channel-Selektion

Pre-Pass (5–7 Frames): TextureScore & Temporal-Stability je Kanal → Shortlist (typ. {Y,G}).

Micro-Trials (30f): Score = 0.5·(1−Survival)+0.3·(1−Corr)+0.2·TimeNorm → Gewinner setzen.

Hysterese: Wechsel erst nach 2 neg. Fenstern, max 1/100f/ROI.

4) Detect-Autotune (Hebel)

Parameter: detect_threshold (log 1e-5…1e-2), min_distance_base≈2.5·pattern, nms_window≈pattern, max_features/ROI, multi-scale 1..3, edge_suppression on/off.

Regeln:
– Low-Texture/Blur → threshold↓, multi-scale on, max_features↑
– Fehlmatches↑ → edge_suppression on, threshold↑
– Clusterbildung → min_distance↑

5) Stufenweises Seeding (mit /5-Logik & Dedup)

Stages: threshold ∈ {1.0, 0.1, 0.01, 0.001, 0.0001}.
Pattern/α pro Stufe: {p0−4,2}, {p0,3}, {p0+4,3}, {p0+8,4}, {p0+8…+12,4} (clamp 9..41).

Marker-Budget: scene["marker_target"] → per_stage = ⌊total/5⌋; Band ±10 % in scene["marker_stage_lo/hi"].

Dedup-Zwischenschritt: KD-Tree gegen (alte + bereits akzeptierte) Marker; Abstand < min_distance ⇒ verwerfen.

Anzahlsteuerung (Feedback):
d ← clamp(d·√(n / per_stage), 2·pattern … 3.5·pattern).
Überfüllung → trim (Qualität zuerst, dann räuml. Diversität); Unterdeckung → refill nur in leeren Tiles.

Micro-Validation (10f): Corr<0.60 oder Jump-Spikes ⇒ raus.

Early-Stop: Stage/ROI überspringen, sobald Coverage/KPIs erfüllt sind oder Zeit-Slice aufgebraucht.

6) One-Frame Tracking Loop (online adaptiv)

Cheap-Move pro Frame: nur Search (α) anpassen.
– Abriss ohne Fehlmatch → α+1 (≤4)
– Fehlmatch/Corr-Crash → α−1 (≥2)
– Stabil & teuer → α−1

Gated-Move (Pattern): nur an Checkpoints bei stabiler Triggerlage (≥3 Frames Erosion von Corr oder Scale/Rot-Indikatoren).
– Apply „next frame“ mit Re-Template (Median-Fenster um t), Lock 1 Frame, Cooldown ≥15 Frames.
– Rollback, wenn 10f-Gain ausbleibt.

Hysterese: Trigger-Zähler, max 1 Param-Move/10 Frames/Marker.

7) Motion-Model-Selektion (Cluster-basiert, rollierend 20–40f)

Model-Hierarchie: Loc → LocRot → LocRotScale → Affine → Perspective.

Fit via RANSAC: RMS, Outlier, Inliers.

Komplexitätsstrafe: S(M)=RMS+λ·κ, κ={1,2,3,4,6}, λ≈0.10–0.15 px.

Promotion:
Loc→LocRot: ΔS≥0.3 px oder σ_rot≥0.5° (3 Fenster)
LocRot→LRS: ΔS≥0.25 px oder σ_scale≥1.5 % (3 Fenster)
LRS→Affine: ΔS≥0.20 px oder ϕ_shear≥0.15 und Outlier↓≥10 %
Affine→Persp.: ΔS≥0.20 px und Parallaxe hoch und Outlier↓≥5 %
Min-Inlier ≥8, Rollback bei fehlendem Benefit (2 Fenster).

8) Peer-Stabilisierung & Reseeding

Peer-Snap: Sprungbegrenzung relativ zur Clustertrajektorie.

Koordiniertes Re-Template bei Cluster-Drift.

Gezieltes Reseeding in Coverage-Löchern (Tiles-Priorisierung), min_distance ∝ pattern.

9) Cleanup-Zyklen (leichtgewichtig)

clean_error_tracks (limit px adaptiv), clean_short_segments, Gap-Handling.

Bei hartnäckigen Fails: refine_high_error(top_k) + Find-Low-Restart.

10) Telemetrie, Presets, Reuse

Logging (CSV/JSON): pro ROI/Cluster/Marker—params_in/out, KPIs, Zeit, Entscheidungen.

Preset-Cache: (Auflösung-Bin, Texture-Bin, Motion-Bin, Quadrant) → Startwerte (pattern, α, detect-Profile, Channel, Model).

Exploration: ε-greedy 10 % vs. Best-Preset; Aging über Median-Score.

11) Sicherheitsnetze

Harte Grenzen: 9 ≤ pattern ≤ 41; α ∈ [2..4]; search ≤ 0.12·minDim.

Early-Exit: Survival@10f<0.4 und Corr<0.6 → lokales Downgrade/Refit.

Zeit-Slicing strikt; keine Mid-Frame-Paramwechsel (apply-next-frame).

Orchestrator-Ablauf (kompakt)

STRM analysieren → ROIs priorisieren.

Startwerte setzen (pattern/search, Channel).

Detect autotunen → staged seeding mit Dedup + /5-Zielband + Micro-Validation.

Frame-Loop: track-1-step → eval → α-Adjust (apply next), ggf. gated pattern-update.

Alle 20–40 Frames/Cluster: Model-Fit & Selection (mit Strafe/Hysterese).

Peer-Snap/Refresh, Reseeding in Löchern, periodische Cleanup-Passes.

KPIs aggregieren, Presets aktualisieren, Summary reporten.

Schnittstellen (Helper-API)

ROI/STRM: analyze_rois()

Init: init_pattern_search(roi), select_channel(roi)

Detect: autotune_detect(roi), staged_detect_with_dedup(roi, pattern, alpha, N_total)

Online: track_one_frame(roi), schedule_param_changes(roi, telem)

Models: cluster_fit_models(roi, window), select_apply_motion_models(roi, fits, feats)

Stabilisierung: peer_snap_and_refresh(roi), reseed_coverage_holes(roi), periodic_cleanup(roi)

Persistence: finalize_metrics(), write_presets()
