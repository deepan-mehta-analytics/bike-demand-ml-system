# v4.4.0 — Drift Monitoring + MLflow 6/6 Promotion

**Status:** Draft (S1 — spec phase)
**Author:** Deepan Mehta
**Date:** 2026-05-23
**Target version:** v4.4.0
**Predecessor:** v4.3.0 (Paris timezone fix + Option B 2022 drop + cross-city table alignment)
**Session shape:** S1 (this — spec + plan) / S2 (MLflow pre-flight) / S3 (drift module + baselines) / S4 (tests + GHA cron + smoke) / S5 (close-out)
**Trigger memory:** [[session-shape-token-efficiency]] · [[premortem-includes-context-loss]] · [[portfolio-scaling-judgment]] · [[gcp-billing]]

---

## 1. Executive Summary

Close the repo's one-way pipeline by adding a **weekly weather-feature drift monitor** for all 6 served cities, and bundle the deferred **MLflow Paris + Chicago promotion** to get the registry to 6/6. Drift surface: PSI per weather feature, computed against the same-season slice of training data, refetched from Open-Meteo on a GitHub Actions cron, with the report committed back to the repo as a rolling markdown file.

**Engineering rationale for the drift target:** the model's input vector is `(weather features) + (temporal features)`. Temporal features (HOUR, dayofweek, month, season) are deterministic — they cannot drift. **Weather features are the only legitimate drift surface for this model.** This makes weather-side PSI the *correct* monitoring target, not a portfolio prop.

**Hard constraints (Rule 12 + portfolio-scaling-judgment):**
- NO Cloud Monitoring custom metrics, Cloud Trace, Grafana, or any paid GCP surface
- NO alerting (email/Slack) — the markdown report committed to git IS the surface
- NO real-time inference monitoring — batch cron only
- NO refactor of `data/fetch_*_weather.py` (off critical path; minor URL duplication acceptable at N=6 cities)
- NO new requirements.txt entries — `requests` + `numpy` + `pandas` already present
- NO concept-drift / ground-truth monitoring — different cities have different data lag; not portable across 6

---

## 2. Context & Problem Framing

### The story-break v4.4.0 closes

A senior reviewer reading the v4.3.0 architecture sees:
- Rigorous **pre-deployment** testing (RMSE accuracy gates, 32 pytest, R 62-test suite)
- Cloud Run service serving 6 city models
- Vertex AI training + MLflow registry (4 of 6 cities)
- ...and **zero feedback loop after a request is served**

The pipeline is one-way: train → serve. v4.4.0 closes the loop with the simplest credible monitoring surface that demonstrates ML-Ops thinking without crossing into vanity infrastructure.

### Why fresh-weather PSI is the right drift target (rejected alternatives)

| Considered approach | Rejected because |
|---|---|
| Real production prediction inputs | Repo's only client is the Shiny app; real traffic volume is too low for statistical drift detection to mean anything — would ship plumbing that never surfaces signal |
| Fresh RMSE on actuals (concept drift) | Most cities have lagged trip data: Seoul monthly ZIPs, NYC quarterly dumps, DC quarterly, Chicago monthly. Only Paris + London have ≤ weekly cadence. Can't ship a uniform monitoring story across 6 cities |
| Prediction-output drift only | Doesn't need labels but is the least interpretable for a non-ML reader; weaker portfolio story than feature drift |

### Why the MLflow promotion bundles cleanly

The deferred follow-up "Paris + Chicago in MLflow Production registry" is a 2-line `Dockerfile.training:38-41` fix to add 2 city CSV copies + a Vertex AI re-run. ~0.5 sprint of work, closes a documented Known Limitation in the same release, and aligns the ML-Ops story (6/6 in registry pairs with 6/6 monitored).

---

## 3. Architecture

### 3.1 File layout

```
monitoring/
├── __init__.py
├── drift_check.py              ← main entry; CLI: python -m monitoring.drift_check
├── city_config.py              ← declarative: {city: {lat, lon, tz, weather_features}}
├── baselines/
│   ├── seoul.parquet           ← precomputed season-sliced feature distributions
│   ├── london.parquet          ← regenerated via --regenerate-baselines flag
│   ├── nyc.parquet
│   ├── dc.parquet
│   ├── paris.parquet
│   └── chicago.parquet
└── reports/
    ├── latest.md               ← rolling snapshot (overwritten weekly)
    └── history.csv             ← append-only audit log

.github/workflows/
└── drift.yml                   ← schedule: cron '0 6 * * 1' + workflow_dispatch

tests/
└── test_drift_check.py         ← 8 unit tests, ~200 LoC
```

### 3.2 Module boundary contract

- `drift_check.py` — orchestrator + PSI math + Open-Meteo client + report writers; pure stdlib + numpy + pandas + requests; **zero GCP imports**
- `city_config.py` — pure data; no logic; thresholds (0.10, 0.25) live here as constants
- `baselines/*.parquet` — schema `[season, feature, value]`; long form; columnar; ~50 KB each

### 3.3 Data flow (weekly tick)

```
┌────────────────────────────────────────────────────────────┐
│ Monday 06:00 UTC — GHA cron fires drift.yml                 │
└─────────────────────────┬──────────────────────────────────┘
                          ▼
       ┌─────────────────────────────────────────┐
       │ python -m monitoring.drift_check         │
       │                                          │
       │ for city in CITY_CONFIG:                 │
       │   1. Open-Meteo fetch last 7 days        │
       │      (LAT/LON/tz from config)            │
       │   2. Identify current season             │
       │      (month → Spring/Summer/Autumn/Winter)│
       │   3. Load baselines/<city>.parquet       │
       │      → same-season slice                 │
       │   4. For each weather feature:           │
       │      PSI(fresh, baseline_same_season)    │
       │   5. Classify: STABLE | MONITOR | DRIFT  │
       │   6. Append row to history.csv           │
       │                                          │
       │ Render latest.md from history.csv        │
       │ (current run per-city tables +           │
       │  week-over-week trend arrow vs prior run)│
       └────────────────┬────────────────────────┘
                        ▼
       ┌─────────────────────────────────────────┐
       │ git add monitoring/reports/              │
       │ git commit -m "chore(drift): weekly      │
       │   report YYYY-MM-DD [skip ci]"           │
       │ git push origin main                     │
       └─────────────────────────────────────────┘
```

The `[skip ci]` tag prevents the bot commit from triggering all 8 CI jobs — keeps free-tier discipline.

---

## 4. Statistical Core

### 4.1 PSI definition

```
PSI = Σᵢ (aᵢ − eᵢ) × ln(aᵢ / eᵢ)

where, for each bin i:
  eᵢ = fraction of BASELINE observations in bin i
  aᵢ = fraction of FRESH observations in bin i
```

**Binning rule:** 10 quantile bins (deciles) computed from the **baseline**. Fresh observations are dropped into those fixed bins. Bins are anchored to the reference distribution, not recomputed per sample.

**Numerical guards:** both `aᵢ` and `eᵢ` are floored at `1e-4` before the log/divide to avoid `log(0)` or division-by-zero when a bin has no observations.

**Implementation:** ~25 LoC using `numpy.quantile` + `numpy.histogram` + `numpy.log`. Pure numpy — no scipy needed.

### 4.2 Thresholds (Siddiqi 2006 / SAS / banking standard)

| PSI range | Status | Action |
|---|---|---|
| `< 0.10` | **STABLE** | No action — distribution effectively unchanged |
| `0.10 ≤ PSI < 0.25` | **MONITOR** | Worth watching; not yet a retraining trigger |
| `≥ 0.25` | **DRIFT** | Retraining candidate — investigate before next training run |

Thresholds are **constants in `monitoring/city_config.py`**, not knobs, so cold-restart sessions cannot drift them.

### 4.3 Same-season baseline slicing (the false-positive killer)

**Problem this solves:** every December, fresh weather has `TEMPERATURE` distribution near 0°C; pooled-year baseline has a mean of ~12°C. Without slicing, **every December would flag drift on TEMPERATURE**.

**Fix:** at check time, derive `current_season` from the calendar month, then PSI-compare fresh weather **only against that season's slice** of the baseline.

**Month → season mapping** (NH; all 6 cities are Northern Hemisphere):

| Months | Season |
|---|---|
| Mar / Apr / May | Spring |
| Jun / Jul / Aug | Summer |
| Sep / Oct / Nov | Autumn |
| Dec / Jan / Feb | Winter |

### 4.4 Baseline parquet schema

`monitoring/baselines/<city>.parquet` is long-form:

```
season   | feature              | value
---------|----------------------|------
Winter   | TEMPERATURE          | -2.4
Winter   | TEMPERATURE          | -1.1
...
Spring   | HUMIDITY             | 56.0
...
```

Load + slice trivially via `pd.read_parquet(path).query("season == @current_season")`. File size: ~50 KB per city × 6 = ~300 KB tracked total.

### 4.5 Baseline regeneration

`python -m monitoring.drift_check --regenerate-baselines` reads `data/processed/<city>_bike_sharing.csv` (the canonical training data, already in repo) and rewrites all 6 parquet files. One-off after each retrain; documented in README; future retrain workflow should call it.

### 4.6 Features monitored

8 numeric weather features (drift-capable):

| Feature | Unit |
|---|---|
| `TEMPERATURE` | °C |
| `HUMIDITY` | % |
| `WIND_SPEED` | m/s |
| `DEW_POINT_TEMPERATURE` | °C |
| `SOLAR_RADIATION` | MJ/m² |
| `RAINFALL` | mm |
| `SNOWFALL` | cm |
| `VISIBILITY` | 10m units |

**Explicitly excluded:**
- Temporal features (`HOUR`, `dayofweek`, `month`, `year`, `day`) — deterministic, cannot drift
- Categorical flags (`SEASONS`, `HOLIDAY`, `FUNCTIONING_DAY`) — derived from calendar / operational facts

Result: **48 PSI values per weekly run** (6 cities × 8 features), all summarized in `latest.md`.

---

## 5. Report Schema

### 5.1 `monitoring/reports/history.csv` (append-only audit log)

```csv
run_date,city,feature,season,psi,status,n_fresh,n_baseline
2026-05-25,seoul,TEMPERATURE,Spring,0.045,STABLE,168,4248
2026-05-25,seoul,HUMIDITY,Spring,0.118,MONITOR,168,4248
2026-05-25,seoul,WIND_SPEED,Spring,0.032,STABLE,168,4248
...
2026-05-25,chicago,SNOWFALL,Spring,0.412,DRIFT,168,3960
```

Each weekly run adds ~48 rows. After 1 year ≈ 2,500 rows ≈ tens of KB. Stays under any GitHub file-size concern.

**Status enum (full set used in `history.csv`):**

| Status | Meaning | Source |
|---|---|---|
| `STABLE` | PSI < 0.10 | normal classification (§4.2) |
| `MONITOR` | 0.10 ≤ PSI < 0.25 | normal classification (§4.2) |
| `DRIFT` | PSI ≥ 0.25 | normal classification (§4.2) |
| `FETCH_FAILED` | Open-Meteo HTTP non-200; `psi=NaN`, `n_fresh=0` | §7 error handling |
| `FETCH_SCHEMA_ERROR` | Open-Meteo 200 but missing expected columns; `psi=NaN` | §7 error handling |
| `BASELINE_EMPTY` | Same-season baseline slice has zero rows (defensive guard) | §7 error handling |
| `LOW_BASELINE` | Baseline slice has `< 100` observations; PSI still computed, but flagged | §10.1 A4 |

### 5.2 `monitoring/reports/latest.md` (rolling human surface)

```markdown
# 📡 Drift Monitor — Latest Report

**Run:** 2026-05-25 06:03 UTC
**Schedule:** weekly (Mondays 06:00 UTC) · [workflow](.github/workflows/drift.yml)
**Summary:** 42 stable · 5 monitor · 1 drift  (across 48 city × feature checks)

---

## Seoul (Spring, n_fresh=168, n_baseline=4248)

| Feature | PSI | Status | Trend (vs last week) |
|---|---:|:---:|:---:|
| TEMPERATURE | 0.045 | 🟢 STABLE | ▼ |
| HUMIDITY | 0.118 | 🟡 MONITOR | ▲ |
| WIND_SPEED | 0.032 | 🟢 STABLE | – |
| ... | | | |

## London (Spring, n_fresh=168, n_baseline=3624)
...

---

## Methodology
- **PSI thresholds:** <0.10 stable · 0.10-0.25 monitor · ≥0.25 drift (Siddiqi 2006)
- **Baseline:** same-season slice of training data (`monitoring/baselines/<city>.parquet`)
- **Fresh window:** last 7 days from Open-Meteo
- **Code:** [`monitoring/drift_check.py`](../drift_check.py)
- **Full history:** [`history.csv`](history.csv)
```

The single rolling URL `monitoring/reports/latest.md` becomes the README badge target.

---

## 6. Sprint Shape — S1–S5

Following [[session-shape-token-efficiency]] + the v4.2.0 / v4.3.0 cadence. Each `/clear` boundary lets the next sprint boot cold from `workflow_status.md`.

| Sprint | Boundary | Goal | Commits | Token shape |
|:---:|---|---|---|---|
| **S1** | this session | Brainstorm → spec → plan; commit both. Terminal action: `workflow_status.md` updated with S2 re-entry command. | 2 `docs(monitoring):` commits (spec + plan) | Moderate — ends here |
| **S2** | `/clear` | MLflow pre-flight only. Edit `Dockerfile.training:38-41` to add Paris + Chicago CSV copies; trigger Vertex AI re-run; verify Paris + Chicago appear in MLflow Production registry. README + PROJECT-STATUS small "6/6 in MLflow" update. | 1 `fix(training):` + 1 `docs:` | Light — single-purpose; finishes fast |
| **S3** | `/clear` | Drift module + baselines (heaviest sprint). Implement `monitoring/city_config.py` + `monitoring/drift_check.py` (PSI math + Open-Meteo fetch + report renderers + `--regenerate-baselines` flag). Run regenerator → 6 `.parquet` files committed. Local smoke: `python -m monitoring.drift_check` produces `latest.md` + `history.csv` correctly. | 1 `feat(monitoring):` commit (module + 6 baselines) | Heavy — most of the design lives here |
| **S4** | `/clear` | Tests + GHA cron + manual smoke. Write `tests/test_drift_check.py` (8 tests per §8). Add `.github/workflows/drift.yml`. Trigger manually via `workflow_dispatch`; verify bot commit lands on `main` with `[skip ci]` and `latest.md` renders correctly on GitHub. | 1 `test(monitoring):` + 1 `ci(monitoring):` | Medium — discrete, testable surface |
| **S5** | `/clear` | Close-out. README `📡 Drift Monitoring` section + Scaling Considerations refresh + ticked Roadmap; PROJECT-STATUS Phase 15 block + Ecosystem row v4.3.0 → v4.4.0; Shiny cross-repo PROJECT-STATUS hash sync; v4.4.0 GitHub release per Rule 11. Run Step 1.5 staleness sweep (per global CLAUDE.md Rule 11/12). | 1 `docs:` (Python) + 1 `docs(cross-repo):` (Shiny) + 1 release | Light–medium |

**Why this split is right:**
- S2 is isolated because MLflow involves the GCP+Vertex+MLflow surface — bundling it with drift implementation would compound contexts
- S3 is the largest because the drift module is one coherent thing; splitting it would leave dirty trees between sessions (the v4.3.0 S7-PARTIAL pattern we want to avoid)
- S4 separates tests + CI from S3 because adding tests after the module exists is the natural order, and GHA workflow smoke needs a clean context to evaluate the commit-back loop
- S5 mirrors v4.2.0 S5 and v4.3.0 S8 exactly — proven docs + release pattern

---

## 7. Error Handling

Pattern: **degrade to one bad row, never a missing report.** The report must always render.

| Failure | Behaviour | Operator sees |
|---|---|---|
| Open-Meteo HTTP non-200 | Log error to stdout; append `status=FETCH_FAILED`, `n_fresh=0`, `psi=NaN` rows for that city; continue to next city | Yellow banner in `latest.md` for that city; row in `history.csv` |
| Open-Meteo 200 but missing weather columns | Same as above (`status=FETCH_SCHEMA_ERROR`); raises in unit test against schema fixture | Yellow banner; alert via CI test on next push |
| Baseline parquet missing for a city | Fail loudly: `FileNotFoundError`; orchestrator exits non-zero; GHA cron job turns red | Red GHA badge; failure stays visible until fixed |
| Same-season slice empty (defensive guard) | Skip that city; log `status=BASELINE_EMPTY`; continue | Yellow banner; should be impossible in practice |
| Git push fails on commit-back | GHA step fails; cron run turns red; bot commit not made | Red GHA badge; previous `latest.md` stays in repo so the surface is never blank |

---

## 8. Testing Strategy

`tests/test_drift_check.py` — 8 tests, target ~200 LoC:

| # | Test | What it asserts |
|---|---|---|
| 1 | `test_psi_identical_distributions_is_zero` | PSI(x, x) ≈ 0 within float tolerance |
| 2 | `test_psi_shifted_distributions_above_drift_threshold` | Synthetic +3σ shift → PSI ≥ 0.25 |
| 3 | `test_psi_handles_empty_bins_via_floor` | Bin with 0 observations → 1e-4 floor; no `log(0)` |
| 4 | `test_season_assignment_month_mapping` | Parametrized: Jan→Winter, Apr→Spring, Jul→Summer, Oct→Autumn |
| 5 | `test_all_six_baselines_exist_and_loadable` | Parametrized across 6 cities; parquet present + schema `[season, feature, value]` |
| 6 | `test_history_writer_appends_not_overwrites` | After 2 runs, history.csv has 2× rows |
| 7 | `test_latest_md_overwrites` | `latest.md` mtime advances on rerun; content reflects most recent run |
| 8 | `test_fetch_failure_does_not_raise` | Mock Open-Meteo 500 → `status=FETCH_FAILED` row; no uncaught exception |

**Not adding:** an opt-in `-m slow` "latest.md mtime < 14 days" freshness gate — too easy to flake when GHA cron is delayed; tracked as backlog instead.

**Test discipline:** these 8 land as one commit in S4; full pytest collection should report **40 tests** (32 existing + 8 new) at v4.4.0.

---

## 9. Success Criteria (v4.4.0 ship gate)

All eight must be true:

- ☐ MLflow Production registry shows **6 of 6** cities (Paris + Chicago promoted)
- ☐ `python -m monitoring.drift_check` runs locally end-to-end; produces both report files
- ☐ Full pytest passes: 32 existing + 8 new drift tests = **40 tests**
- ☐ `.github/workflows/drift.yml` runs cleanly on `workflow_dispatch`; bot commit lands on `main` with `[skip ci]`
- ☐ `monitoring/reports/latest.md` renders cleanly on GitHub (tables + emoji badges + relative links)
- ☐ README has `📡 Drift Monitoring` section between Tests and Results; Roadmap drift item ticked; Known Limitations refreshed (concept drift remains open by design)
- ☐ PROJECT-STATUS has Phase 15 block; Ecosystem row v4.3.0 → v4.4.0
- ☐ Shiny PROJECT-STATUS hash sync committed; v4.4.0 GitHub release published per Rule 11

---

## 10. Risk Register

### 10.1 Approach risks (technical)

| ID | Risk | Mitigation |
|---|---|---|
| A1 | Open-Meteo schema changes between fetch_*_weather.py shipping and drift module shipping | Pin URL params; defensive parsing per Test #8; if shape changes, GHA cron turns red and surface stays visible |
| A2 | Baselines drift stale after a future model retrain | `--regenerate-baselines` flag + README documents it as a post-retrain step; future retrain workflow should call it |
| A3 | GHA bot commit collides with active PR work on `main` | `[skip ci]` + path-scoped to `monitoring/reports/` only; conflict surface is minimal (the bot only touches 2 files) |
| A4 | Seasonal slice has `<100` baseline observations for an under-trained city | Warning row in report when `n_baseline < 100`; PSI still computed (caveat in methodology footer) |
| A5 | Numpy quantile differences across versions affecting CI reproducibility | Numpy already pinned in requirements.txt; tests use synthetic data with tolerance comparisons, not float-equal |

### 10.2 Context-loss risks (cross-session, per [[premortem-includes-context-loss]])

| ID | Risk | Mitigation |
|---|---|---|
| CL1 | S3 cold restart writes baseline regenerator with a different season-mapping than spec | Month→season table in spec §4.3 + plan Task; constants live in `city_config.py`, sourced once |
| CL2 | S4 cold restart writes GHA workflow without `[skip ci]` tag → triggers full 8-job CI on every cron | `workflow_status.md` Next Action explicitly cites `[skip ci]`; plan Task has the exact commit-message string |
| CL3 | S5 cold restart misplaces README section or breaks badge link | Spec §1 + §5 pin section position ("between Tests and Results") and badge URL exactly; plan Task pins line numbers at S5-time grep |
| CL4 | Any sprint loses the "no Cloud Monitoring writes / no paid GCP" rule | Spec §1 leads with it; workflow_status.md Status line carries the discipline; Rule 12 reinforces |
| CL5 | S3 forgets to commit the 6 baseline `.parquet` files (they're ~50 KB each — easy to miss) | Plan Task explicitly lists all 6 paths; smoke step asserts `git status` shows them staged before commit |

---

## 11. Out-of-Scope / Backlog

The following are explicitly NOT in v4.4.0 but tracked here so they don't appear as gaps in a code review:

- **Concept drift monitoring** (fresh RMSE vs baseline) — different cities have different data lag; not portable across 6. Tracked as v4.5+ candidate if Paris + London uniform-cadence subset becomes interesting.
- **Real-time inference monitoring** — repo's only client is Shiny; traffic too low for statistical signal. Would require either traffic generators or extending production log schema; not portfolio-justified.
- **Alerting** (email/Slack/PagerDuty) — markdown report is the surface; alerting adds operational surface area without portfolio value.
- **Dashboard UI** (Streamlit, Grafana, Looker Studio) — explicitly the "vanity zone" called out in `feedback_dashboard_consideration` + `feedback_portfolio_scaling_judgment`. Report-as-markdown is the disciplined choice.
- **Drift-triggered auto-retrain** — couples monitoring with training pipeline; out of scope for v4.4.0 monitoring-only release.
- **Per-city PSI threshold tuning** — locked at industry-standard 0.10 / 0.25 to keep the methodology defensible; tunable in city_config.py if ever needed.

---

## 12. References

- **Siddiqi, N. (2006)**. *Credit Risk Scorecards: Developing and Implementing Intelligent Credit Scoring.* Wiley. — origin of PSI thresholds in production use
- **Predecessor spec:** `docs/superpowers/specs/2026-05-21-paris-timezone-fix-design.md` (v4.3.0)
- **Memory:** `feedback_portfolio_scaling_judgment.md`, `feedback_session_shape_token_efficiency.md`, `feedback_premortem_includes_context_loss.md`, `project_gcp_billing.md`
