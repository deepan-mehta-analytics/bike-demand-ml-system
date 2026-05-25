# Project Status — Bike Demand ML System (Python Backend)

> Re-entry command: `"resume bike-demand-ml-system project"`
> Companion repo: `D:\OneDrive\Developer\DataAnalytics\R_projects\bike_demand_prediction`

---

## 🌐 Ecosystem Snapshot

Both repos form a single portfolio system. Track them together here.

| Repo | Role | Current Phase | Status | Last Commit |
|------|------|--------------|--------|-------------|
| **bike-demand-ml-system** (this repo) | Python FastAPI + ML training | v3.1.0 shipped — Cloud Run GBFS poller (`gbfs-poller` + `gbfs-poller-cron` + BQ 7-day partitions) replacing the v3.0.0 Dataflow path; GCP Stream tab live. (Joint cross-repo work tracked as Shiny v1.6.0 Sprint 1.) v4.3.0 was Paris tz fix; v4.4.0 drift monitoring in design (S1 complete) | ✅ Done | `9f86cb3` |
| **bike_demand_prediction** | R Shiny dashboard | v1.5.0 shipped — testthat suite + CI; v1.6.0 spec written (dashboard truth audit, 3 workstreams A/B/C); Sprint 1 Workstream A now live | ✅ Done | `9d5c70e` |

### Trained City Models

| City | Dataset | Rows | RMSE | Top Feature | Artifacts |
|------|---------|------|------|-------------|-----------|
| Seoul | OA-15182 + Open-Meteo (2022-2024) | 26,303 | **1,503.52** | HOUR (0.468) | `models/artifacts/seoul/` |
| London | Kaggle london_merged.csv | 17,414 | **316.56** | HOUR (0.71) | `models/artifacts/london/` |
| NYC | BigQuery citibike_trips (2014–2018) + Open-Meteo | 34,187 | **470.76** | HOUR (0.52) | `models/artifacts/nyc/` |
| Washington DC | Capital Bikeshare CSVs (2014–2018) + Open-Meteo | 37,663 | **119.31** | HOUR (0.62) | `models/artifacts/dc/` |
| Paris | opendata.paris.fr counter ZIPs (2023–2024; 2022 dropped) + Open-Meteo | 17,539 | **20.51** | HOUR (0.708) | `models/artifacts/paris/` ✅ |
| Chicago | Divvy quarterly CSVs (2019–2022) + Open-Meteo | 32,720 | **202.99** | HOUR + TEMPERATURE (0.39 each) | `models/artifacts/chicago/` ✅ |

### Next Milestones (Both Repos) — Priority Ordered

| Priority | Repo | Phase | Target Version | Dependency |
|----------|------|-------|---------------|------------|
| ~~1~~ | bike-demand-ml-system | ~~Phase 6 — Observability~~ | ~~v2.1.0~~ | **✅ Shipped** |
| ~~1~~ | bike-demand-ml-system | ~~Phase 4 — Pub/Sub + Dataflow~~ | ~~v3.0.0~~ | **✅ Shipped** |
| ~~1~~ | bike_demand_prediction | ~~Phase 7F — GCP Streaming Dashboard~~ | ~~v1.2.0~~ | **✅ Shipped (2026-05-16)** |
| ~~3~~ | bike-demand-ml-system | ~~Phase 5 — Vertex AI + MLflow~~ | ~~v4.0.0~~ | **✅ Shipped (2026-05-17)** |
| ~~3~~ | bike_demand_prediction | ~~Feed Health Alerting — GBFS feed status panel~~ | ~~v1.3.0~~ | **✅ Shipped (2026-05-17)** |
| ~~4~~ | bike_demand_prediction | ~~Backlog — Paris/Chicago models~~ | ~~v1.4.0~~ | **✅ Shipped (2026-05-18)** |
| ~~5~~ | bike-demand-ml-system | ~~Phase 7 — Automated Test Suite (pytest)~~ | ~~—~~ | **✅ Shipped (2026-05-18)** |
| ~~5.5~~ | bike-demand-ml-system | ~~Phase 13 — Seoul training data refresh (OA-15182 + Open-Meteo)~~ | ~~v4.2.0~~ | **✅ Shipped (2026-05-21)** |
| ~~5.6~~ | bike-demand-ml-system | ~~Phase 14 — Paris timezone fix + Option B 2022 drop + cross-city table alignment~~ | ~~v4.3.0~~ | **✅ Shipped (2026-05-21)** |
| ~~6~~ | bike-demand-ml-system | ~~4-city analogous timezone bug fix (Paris/Chicago/NYC/DC)~~ | ~~v4.3.0~~ | **✅ Scope shrunk to Paris-only after code inspection (NYC/DC/Chicago parse datetimes naively; no `tz_convert` calls); shipped as Paris-only in v4.3.0** |
| ~~7~~ | bike_demand_prediction | ~~Backlog — Seoul GBFS~~ | — | **✅ Integration shipped 2026-05-17 on Shiny side (commit `8682242`) on `sample` key; full-coverage upgrade demoted 2026-05-23 to runtime `.Renviron` config — see Shiny README "Optional — Seoul full-coverage upgrade". ML side never needed any key — OA-15182 training data is a public download.** |
| ~~8.0~~ | bike-demand-ml-system + bike_demand_prediction | ~~Sprint 1 — Cloud Run GBFS poller replacing paused Dataflow path~~ | ~~v3.1.0 (ML) / v1.6.0 Sprint 1 (Shiny)~~ | **✅ Shipped 2026-05-25 — `gbfs-poller` Cloud Run + `gbfs-poller-cron` Scheduler (every 5 min) + BQ 7-day partitioned `station_snapshots`. 6,032 rows/window across 4 cities. GCP Stream tab now actually streams. ML commits `6d6e5a2`→`9f86cb3`; ML release v3.1.0; Shiny tracks the same work as Sprint 1 of its v1.6.0 dashboard-truth-and-freshness ship.** |
| **8** | bike_demand_prediction | Backlog — City expansion (SF/Amsterdam) | — | Data sourcing required |

---

## ✅ Completed

### ML Pipeline
* Seoul training data refreshed (v4.2.0): OA-15182 (Seoul Open Data Plaza, 2022-2024) + Open-Meteo, 26,303 hourly rows after join; DD/MM datetime parsing
* Feature engineering: `year`, `month`, `day`, `dayofweek` + one-hot (`SEASONS`, `HOLIDAY`, `FUNCTIONING_DAY`)
* Random Forest baseline: RMSE **1,503.52** bikes/hr (Seoul, chronological 80/20 split, 21,042 train / 5,261 test); scaler removed (RF is scale-invariant)
* Feature schema persisted at training time — no train/serve skew at inference

### API + Service Layer
* `api/app.py` — FastAPI: `GET /` health, `POST /predict` batch endpoint, Pydantic v2 validation
* `services/predictor.py` — per-city lazy-load singleton cache; Seoul fallback for untrained cities
* `models/predict.py` — schema-aligned inference via `reindex(fill_value=0)`

### Multi-City Training (Phase 2)
* `--city` CLI arg in `models/train.py`; per-city artifacts at `models/artifacts/<city>/`
* `city: str = "Seoul"` field on `PredictionRequest`; service layer routes to correct artifact
* **London**: Kaggle CSV prepared via `prepare_london()`; RMSE **316.56** (chronological split); HOUR dominates (0.71)
* **NYC**: BigQuery `new_york_citibike` (2014–2018) + Open-Meteo via `data/fetch_nyc_weather.py`; RMSE **470.76** (chronological split); HOUR (0.52) + year growth trend (0.12)
* `services/predictor.py`: fallback to Seoul for cities without trained artifacts; city slug map routes "new york" → nyc, "washington dc" → dc
* `data/prepare_city_data.py`: `prepare_london()`, `nyc_bigquery_sql()`, `prepare_nyc_from_joined()`, `prepare_dc_from_joined()`
* `data/fetch_dc_weather.py`: Capital Bikeshare trip aggregation + Open-Meteo join + Seoul-schema prepare for DC
* **Washington DC**: Capital Bikeshare CSVs (2014–2018) + Open-Meteo join via `data/fetch_dc_weather.py`; RMSE **119.31** bikes/hr (chronological split); HOUR dominates (0.62); 37,663 hourly rows
* `data/raw/` restructured: per-city subfolders (`seoul/`, `london/`, `nyc/`, `dc/trips/`, `paris/`, `chicago/`); `requests` added to `requirements.txt`

### Infrastructure (containerisation + CI)
* `requirements.txt` — 12 packages pinned (FastAPI / uvicorn / scikit-learn / pandas / joblib / pydantic / pytest / httpx / ruff / anyio / requests / prometheus-fastapi-instrumentator); `pytest.ini` — `pythonpath = .`
* 40 tests: 10 unit (features incl. frozen-set guard) + 6 API integration (incl. city default) + 6 RMSE gates (`-m slow`) + 5 routing + 5 Dataflow pipeline (GBFS/TFL/ParseMessage/DirectRunner; auto-skipped in CI) + 5 v3.1.0 window_agg (5-min aggregator) + 3 v3.1.0 gbfs_poller_service (FastAPI contract)
* `Dockerfile` — `python:3.11-slim`, non-root `appuser`, stdlib health check; inline comments moved to standalone lines (Docker parse fix, commit `1ae284f`)
* `docker-compose.yml` — fastapi service, port 8000, `USE_PUBSUB=false`; volume mount removed (artifacts baked into image)
* `.github/workflows/ci.yml` — 7 jobs: `lint` (ruff), `test` (pytest fast — trains Seoul model as fixture), `docker` (image build), `publish` (push to GHCR), `publish-gar` (push to GAR + redeploy Cloud Run on merge to main), `build-training-container` (push Vertex AI training image to GAR), `accuracy` (RMSE gates across all 6 cities, push to main only); all jobs green on the latest push

---

## ⚠️ Known Limitations

* No API authentication or rate-limiting
* No drift monitoring on inference inputs — feature importances are logged to MLflow each run but no automated alert threshold
* Paris RMSE (20.51 post-v4.3.0; was 23.30 in v1.4.0 baseline) reflects counter MEAN normalisation (~50–500/hr scale), not raw station volume — correct behaviour. 2022 source export dropped as a data-quality gate (peaked 2h later than 2023+2024 in both AM and PM rush across DST seasons; intrinsic to provider's aggregation pipeline; reversible)
* NYC RMSE (470.76) is higher due to larger absolute trip volumes; adding weather data beyond
  temperature/humidity (e.g. actual visibility, not Open-Meteo zeros) would likely reduce it
* ~~Dataflow streaming pipeline has **no always-free tier** (~$0.05/hr on e2-medium) — run only for demos; cancel after verification~~ — **Superseded 2026-05-25 by v3.1.0.** Cloud Run (`gbfs-poller`) + Cloud Scheduler (`gbfs-poller-cron`, every 5 min) replaced Dataflow as the GBFS → BQ streaming path at zero always-free-tier cost. `pipeline/dataflow_job.py` retained intact for potential resurrection.

---

## 🔜 Roadmap

### Phase 3 — Cloud Run Deployment ✅ DONE
* [x] All 6 city models baked into Docker image at build time — `Dockerfile:28-33` runs `python -m models.train` once per city during the image build; no volume mount required
* [x] `docker-compose.yml` — volume section removed; image is self-contained
* [x] CI publish job — `docker/build-push-action` pushes `ghcr.io/deepan-mehta-analytics/bike-demand-ml-system:{latest,sha}` to GHCR on merge to main; uses auto-injected `GITHUB_TOKEN` (no manual secrets required)
* [x] CI Job 5 (`publish-gar`) added — builds and pushes to GAR + redeploys Cloud Run on every merge to main; requires `GCP_SA_KEY` GitHub secret
* [x] README — Option 3 (GHCR pull) + Option 4 (Cloud Run gcloud deploy) documented
* [x] GitHub release `v1.0.0` published on both repos (2026-05-08)
* [x] NotebookLM PKB audit complete — 5 documents in `notebooklm/` (gitignored)
* [x] Cloud Run live: **https://bike-demand-api-246440913351.us-central1.run.app** (2026-05-15) — health check returns `{"message":"Bike Demand Prediction API is running"}`
* [x] Shiny repo `model_prediction.R` — Cloud Run URL documented in `FASTAPI_URL` comment; env var already wired, no code change required
* [x] `GCP_SA_KEY` GitHub secret added — service account `github-ci-sa` (roles/run.developer + roles/artifactregistry.writer + roles/iam.serviceAccountUser); CI Job 5 is fully active

### Phase 6 — Observability ✅ Done (v2.1.0 — commit c6fd1d0)
* [x] Structured JSON logging in `services/predictor.py` — city, inputs_hash, n_records, latency_ms → Cloud Logging (stdout, free)
* [x] `/metrics` Prometheus endpoint via `prometheus-fastapi-instrumentator==7.1.0` — pure HTTP, no GCP cost
* [x] GitHub release v2.1.0 published

### Phase 4 — Pub/Sub + Dataflow Pipeline ✅ Done (v3.0.0 — commit 2f60acb)
* [x] `pipeline/gbfs_to_pubsub.py` — GBFS poller every 60s; `USE_PUBSUB=false` → stdout; TFL adapter for London; 1 JSON array msg per city (4 msgs/cycle)
* [x] `pipeline/dataflow_job.py` — Apache Beam: ParseMessage → 5-min FixedWindows → WindowedAgg → BigQuery sink; WindowsPath pickle fix; worker_zone rename
* [x] `config/gcp_config.yaml` — project ID, Pub/Sub topic/sub, BQ dataset/table, Dataflow config (e2-medium, us-central1-f), GBFS city URLs
* [x] `requirements-pipeline.txt` — apache-beam[gcp]==2.62.0, google-cloud-pubsub==2.26.1, pyyaml==6.0.2
* [x] `tests/test_pipeline.py` — 5 tests (GBFS/TFL schema, ParseMessage, DirectRunner e2e); auto-skipped in CI
* [x] GCP provisioning — Pub/Sub `gbfs-bike-stations` + sub, BigQuery dataset `bike_demand`, GCS bucket `gs://bike-demand-staging`, IAM roles for `github-ci-sa` (2026-05-15)
* [x] End-to-end verify — `bike_demand.station_snapshots`: nyc 6,624 rows, first_window 2026-05-15 13:05:00 UTC ✅ (2026-05-15)
* [x] GitHub release v3.0.0 published (2026-05-15)
* Unlocks R Shiny Phase 7F ✅ — BigQuery table live

### Phase 7 — Automated Test Suite ✅ Done (2026-05-18 — commit ca05b35)
* Spec: `docs/superpowers/specs/2026-05-18-pytest-suite-design.md`
* `pytest.ini` — `slow` marker registered; fast tests (`-m not slow`) run in every CI push; RMSE gates run only on push to main
* `tests/test_features.py` — `test_feature_schema_is_frozen`: frozenset of 21 columns; actionable failure message names all 6 cities + Vertex AI container retrain steps
* `tests/test_model_accuracy.py` — 6 `@pytest.mark.slow` parametrised RMSE gate tests; chronological 80/20 split matches `train.py` exactly
* `tests/test_routing.py` — 5 no-fallback routing tests (paris→paris, chicago→chicago, "new york"→nyc, "washington dc"→dc, unknown→seoul fallback); real sklearn RF + monkeypatch
* `.github/workflows/ci.yml` Job 7 (`accuracy`) — parallel to Job 2, push to main only; ~5 min wall time
* All 7 CI jobs green on push to main ✅

### Phase 13 — Seoul Training Data Refresh ✅ Done (v4.2.0 — commit 64ac1d2)
* **Replaces stale UCI 2017-2018 Seoul training set** with OA-15182 (Seoul 따릉이 rental history, 2022-2024) joined to Open-Meteo historical weather; 26,303 hourly rows; mirrors v1.4.0 Paris pattern
* `data/fetch_seoul_weather.py` — aggregates 36 monthly CSVs (cp949-encoded, ~23 GB) to hourly trip counts; joins to Open-Meteo archive (lat=37.57, lng=126.98, timezone=Asia/Seoul); writes `data/processed/seoul_bike_sharing.csv`
* `data/prepare_city_data.py::prepare_seoul_from_joined()` — Seoul-schema normaliser for the joined CSV
* **Timezone bug caught + fixed mid-sprint (commit `176e182`)** — removed `tz_convert("UTC")` on trips before joining with Asia/Seoul weather; restored proper diurnal signal (HOUR=18 mean RBC 11,716 vs HOUR=4 mean 625)
* **RMSE 1,503.52 bikes/hr** (Seoul, chronological split) vs UCI baseline 328.84 — honest figure on ~7× scale + 3-year window; HOUR feature importance climbed to 0.468 (vs 0.287 UCI)
* `tests/test_model_accuracy.py` — Seoul threshold raised 450 → 2,200 (~46% headroom); 5 path references rewired from `data/raw/seoul/seoul_bike_sharing.csv` → `data/processed/seoul_bike_sharing.csv` (tests, Dockerfile, Dockerfile.training, gcp_config.yaml, models/train.py, data/processed/README.md)
* `Dockerfile.training` — removed standalone `COPY data/raw/seoul/` directive (was about to copy 23 GB raw monthly CSVs into image)
* README + data/raw/README.md staleness sweep — zero remaining "UCI Seoul / 8,760 / 328.84" references outside `docs/superpowers/` historical specs
* 23 GB raw monthly CSVs deleted locally post-train (re-fetchable from data.seoul.go.kr); `.gitignore` updated to catch year-prefixed CSVs
* GitHub release v4.2.0 published

### Phase 14 — Paris Timezone Fix + Cross-City Table Alignment ✅ Done (v4.3.0 — commits f713ae5 + 15312b4)
* **Scope correction from initial v4.3.0 framing:** the original thread "4-city analogous timezone bug fix (Paris/Chicago/NYC/DC)" assumed all 4 cities had Seoul's `tz_convert("UTC")` pattern. Code inspection during the spec phase (Grep across all 4 fetch scripts) confirmed only Paris has the bug — NYC/DC/Chicago parse trip + weather datetimes as naive local time and don't need fixing.
* `data/fetch_paris_weather.py:112-125` — drops `tz_convert("UTC")` and restructures the mixed-format parser so all 3 input formats (naive 2022, ISO-with-offset 2023, space-separated-with-offset 2024) land in naive Europe/Paris local time. Mirrors the Seoul fix in commit `176e182`.
* **Empirical verification gate (HARD GATE in spec §6) revealed a separate 2022 anomaly off the planned decision matrix:** 2022 export peaks at HOUR 20 vs 2023+2024 peak HOUR 18 (wrong direction for a UTC encoding bug); Jan/Jul 2022 internally consistent (rules out timezone-encoding cause); AM rush shifted +2h too; nominal "Europe/Paris" metadata at opendata.paris.fr confirmed. Anomaly is intrinsic to the provider's aggregation pipeline.
* **Option B chosen (drop 2022 from training):** clean signal beats more data when the alternative is 33%-contaminated mean. Reversible single block at `data/fetch_paris_weather.py:135-149` if root cause is ever identified upstream.
* Post-Option-B verification (CLEAN PASS): 2023 peak HOUR 18 (mean 193); 2024 peak HOUR 18 (mean 167); 4-of-4 Jan/Jul × 2023/2024 peak HOUR 18 (DST-consistent); overall diurnal ratio 27× (textbook commuter shape).
* **Paris RMSE 20.51 bikes/hr** (down from 23.30 v1.4.0 baseline, **−12.0%**); MAE 12.00; MSE 420.77; train 14,031 / test 3,508; top feature HOUR 0.708 (up from 0.634 — HOUR dominance sharpened by clean-signal effect).
* `tests/test_model_accuracy.py:20` — Paris threshold tightened 50 → 40 (~95% headroom matching other cities' style). CI RMSE accuracy gates job green at cloud RMSE.
* `models/train.py:129` — em-dash (U+2014) replaced with `--` to prevent cp1252 replacement char on Windows stdout (`Training RF model -- city: paris`).
* `README.md` — NYC RF metric table gained MAE (246.02) + Train/Test rows (27,349/6,838); DC RF metric table gained MAE (67.75) + MSE (14,234.62) + Train/Test rows (30,130/7,533) — DC was missing MSE entirely. Cross-city alignment with Seoul post-v4.2.0 format restored.
* `README.md` Paris hunks: per-city RMSE table row refreshed; key-insight prose appended with v4.3.0 tz-fix + Option B explanation; repo structure annotation updated; dataset table row updated with Option B note inline.
* Tracked follow-ups from v4.2.0 closed (3 of 3 — Paris fix + train.py stdout + NYC/DC MAE rows all shipped in v4.3.0).
* GitHub release v4.3.0 published.

### Phase 5 — Vertex AI + Experiment Tracking ✅ Done (v4.0.0 — commit d5c2a54)
* **Code shipped 2026-05-16** — spec: `docs/superpowers/specs/2026-05-16-phase5-vertex-mlflow-design.md`
* `pipeline/retrain_job.py` — 6-combo hyperparameter sweep per city; SQLite+GCS MLflow tracking; RMSE gate (0.97); DRY_RUN mode
* `pipeline/vertex_trigger.py` — Cloud Run HTTP handler; `aiplatform_v1.JobServiceClient` with proto; server-side billing cap `scheduling.timeout: 1800s`
* `Dockerfile.training` — training + trigger container; `python -m pipeline.retrain_job` CMD (sys.path fix); bakes all 4 city CSVs
* `requirements-vertex.txt` — google-cloud-aiplatform, mlflow (pandas<3 constraint resolved), gcsfs for artifact store
* `models/train.py` — chronological 80/20 split (correctness fix); MAE added to evaluation
* `ci.yml` Job 6 — builds + pushes `bike-demand-training` image to GAR on merge to main — ✅ green (run 25970193112)
* **GCP provisioned (2026-05-17):**
  - Vertex AI API enabled; `vertex-sa` SA with `roles/aiplatform.user` + GCS objectAdmin; Vertex AI service agent `service-246440913351@gcp-sa-aiplatform.iam.gserviceaccount.com` granted `roles/artifactregistry.reader` (post-first-job IAM, applied 2026-05-17)
  - `bike-demand-trigger` Cloud Run deployed at `https://bike-demand-trigger-246440913351.us-central1.run.app`
  - Cloud Scheduler job `bike-demand-weekly-retrain` — every Sunday 02:00 UTC
  - Cloud Monitoring: email channel `deepanmehta@live.com`; log-based alerts for job failure + running state
* **Verification complete (2026-05-17):** Vertex AI job ran ~10 min; **4 of 6 cities** (Seoul / London / NYC / DC) registered in MLflow Production at v4.0.0 cut-off; `gs://bike-demand-staging/mlflow/mlflow.db` uploaded; `gs://bike-demand-staging/mlflow/artifacts/` has 47 model.pkl files across 4 city dirs. **Paris and Chicago** train via the same Vertex AI job but `Dockerfile.training:38-41` only copies 4 city CSVs — promotion to MLflow Production is open candidate (b) in Next Step.
* GitHub release v4.0.0 published (2026-05-17)

---

## 🚀 Next Step

**v4.3.0 shipped (2026-05-21) — Paris timezone fix + Option B 2022 drop + cross-city table alignment.** 2 feature commits: `f713ae5` (Paris fix + retrain + threshold), `15312b4` (train.py ASCII stdout + NYC/DC MAE/MSE rows); plus `430f905` (post-S7 README staleness sweep) and this docs commit. New Paris RMSE 20.51 bikes/hr on 17,539 hourly rows (vs v1.4.0 baseline 23.30 on 26,297 rows; 33% data drop offset by clean-signal effect). All 7 CI jobs green on `f713ae5` including RMSE accuracy gates at cloud (threshold 40); FastAPI smoke test verified Paris evening rush (237.45) + Seoul cross-city sanity (1570.26 — no drift) + HTTP 422 malformed-input rejection. Scope corrected mid-spec from "4-city analogous bug" to Paris-only after code inspection confirmed NYC/DC/Chicago parse datetimes naively.

**Tracked follow-ups block now empty for the first time since pre-v4.2.0.** All 3 v4.2.0 carry-overs (Paris tz fix; `train.py` cp1252 stdout sweep; MAE rows in NYC/DC RF tables) shipped in v4.3.0.

**Next priority — v4.4.0 in design (S1 complete 2026-05-23).** Spec [`docs/superpowers/specs/2026-05-23-drift-monitoring-design.md`](docs/superpowers/specs/2026-05-23-drift-monitoring-design.md) (commit `dac2990`) + plan [`docs/superpowers/plans/2026-05-23-drift-monitoring.md`](docs/superpowers/plans/2026-05-23-drift-monitoring.md) (commit `e8d26bb`) committed + pushed to `main`. v4.4.0 scope:
- **Drift monitoring** — `monitoring/` package: weekly Open-Meteo refetch + PSI per weather feature vs same-season training baseline; GitHub Actions cron commits markdown report back to `main` with `[skip ci]`; zero paid GCP surface
- **MLflow 6/6 promotion** — bundled pre-flight: `Dockerfile.training:38-41` 2-line edit copies Paris + Chicago CSVs; Vertex AI re-run promotes both to MLflow Production registry; closes "4 of 6 cities" Known Limitation

Sprint cadence S1 → S2 (MLflow pre-flight) → S3 (drift module + 6 baselines, TDD) → S4 (GHA cron + manual smoke) → S5 (close-out + release) per [[session-shape-token-efficiency]].

**Other open candidates (not bundled into v4.4.0, available for v4.5+):**
- (a) Shiny Phase 8 / v1.7 — `shinytest2` browser harness (new R tooling, multi-session arc)
- ~~(b) Shiny Priority 6 — upgrade Seoul **live station** feed from the 5-station `sample` key to a registered key~~ — **Demoted 2026-05-23** to runtime `.Renviron` config on the Shiny side (integration already shipped in commit `8682242`); no longer an open candidate. Documented under Shiny README "Optional — Seoul full-coverage upgrade".
- (c) Investigate the Paris 2022 anomaly root cause upstream (opendata.paris.fr) to potentially re-enable that 33% of data; reversible via single block in `data/fetch_paris_weather.py`
- (d) Concept drift on the Paris + London uniform-cadence subset — only cities with weekly trip-data publication; defer until v4.4.0 ships and v4.5+ scope is reviewed
- (e) Any new ML / data-engineering thread

**v3.1.0 shipped 2026-05-25 — Cloud Run GBFS poller live.** Requirements (`6d6e5a2`) → `window_agg.py` TDD (`a83e0a6`) → `gbfs_poller_service.py` TDD (`fbb5ef5`) → `Dockerfile.poller` + smoke test (`9f86cb3`) → SA + IAM + GAR push + Cloud Run deploy + Scheduler + BQ 7-day partition. 6,032 rows/window across nyc/dc/london/chicago confirmed in BQ. GCP Stream tab live within 10 min of scheduler start. ML release tag `v3.1.0`; Shiny tracks the same work as Sprint 1 of its v1.6.0 dashboard-truth-and-freshness ship.

**v1.6.0 Sprint 2 (Shiny Workstream B — forecast freshness + honest demo) is next on the Shiny side.** Requires a separate brainstorming → writing-plans → executing-plans cycle in the Shiny repo; no ML-repo code changes expected.

*v4.4.0 design landed 2026-05-23 — commits dac2990 + e8d26bb. v4.3.0 Paris fix shipped 2026-05-21 — commits f713ae5 + 15312b4. v4.2.0 Seoul refresh shipped 2026-05-21 — commit 64ac1d2. Phase 7 complete 2026-05-18 — commit 8bcdb4c. v1.4.0 Paris + Chicago shipped 2026-05-18 — commit d8ee4e0. Phase 5 (Vertex AI + MLflow) complete — v4.0.0 shipped 2026-05-17.*

Resume with: `"resume bike demand — Sprint 2 Workstream B (Shiny forecast freshness)"`
