# v4.3.0 — Paris Timezone Fix + Cross-City Table Alignment

**Status:** Draft (S6 — spec phase)
**Author:** Deepan Mehta
**Date:** 2026-05-21
**Target version:** v4.3.0
**Predecessor:** v4.2.0 (Seoul training data refresh, OA-15182 + Open-Meteo)
**Session shape:** S6 (this — spec + plan) / S7 (execute) / S8 (close-out)
**Trigger memory:** [[session-shape-token-efficiency]] · [[premortem-includes-context-loss]] · [[portfolio-scaling-judgment]]

---

## 1. Executive Summary

Fix the timezone misalignment in `data/fetch_paris_weather.py` that bakes a 1-2 hour offset into the joined trips+weather training data. Mirror the Seoul precedent (commit `176e182`) by aligning trips to Paris-local time instead of UTC. Bundle two tracked cosmetic follow-ups (`train.py` stdout cp1252 sweep + MAE rows in NYC/DC RF tables) into the same release to empty the post-v4.2.0 tracked-follow-ups block to zero.

**Critical scope correction from initial framing:** The original v4.3.0 thread was titled "4-city analogous timezone bug fix (Paris/Chicago/NYC/DC)" based on a pre-mortem note in workflow_status.md. Code inspection during brainstorming surfaced that **only Paris has the bug**. NYC, DC, and Chicago all handle trip + weather datetimes as naive local time (no `tz_convert` calls), so both sides of their joins are already aligned. v4.3.0 scope shrinks accordingly from 4 cities to 1.

---

## 2. Context & Problem Framing

### The Paris timezone bug

`data/fetch_paris_weather.py` fetches Open-Meteo weather with `timezone="Europe/Paris"` (line 64) — weather DATE+HOUR is in Paris wall-clock time.

Trip timestamps (lines 112-125) are parsed to UTC across 3 source formats:
- 2022: naive strings (`'2022-01-01T00:00:00'`) → `tz_localize("Europe/Paris")` then `tz_convert("UTC")`
- 2023: ISO with offset (`'2023-01-01T07:00:00+01:00'`) → parsed with `utc=True` (lands in UTC)
- 2024: space-separated with offset (`'2024-01-02 19:00:00.000 +0100'`) → same

After this block, trips DATE+HOUR is extracted from UTC datetimes. The downstream `(DATE, HOUR)` inner-join silently aligns UTC trips with Paris-local weather — a 1-2 hour misalignment that varies by DST (Paris is UTC+1 winter, UTC+2 summer).

### Verification of the bug (already done in brainstorming)

`Grep` for `tz_convert|tz_localize|timezone=` across all 4 fetch scripts (`paris`, `chicago`, `nyc`, `dc`) returned matches only in Paris. The other three scripts:
- **NYC** ([data/fetch_nyc_weather.py:55-58](data/fetch_nyc_weather.py#L55-L58)): trips come from BigQuery as `DATE + HOUR` directly (no Python tz handling); weather Open-Meteo `timezone="America/New_York"` → both naive local; no mismatch
- **DC** ([data/fetch_dc_weather.py:79-87](data/fetch_dc_weather.py#L79-L87)): trip timestamps parsed via `pd.to_datetime()` with no tz info, then `strftime`'d directly; weather Open-Meteo `timezone="America/New_York"` → both naive local; no mismatch
- **Chicago** ([data/fetch_chicago_weather.py:89-92](data/fetch_chicago_weather.py#L89-L92)): same pattern as DC; weather `timezone="America/Chicago"` → both naive local; no mismatch

The original "4-city analogous bug" framing in `workflow_status.md` was based on the pre-mortem author's `"by inspection of data/raw/README.md"` reasoning, which turned out not to match the actual code. **The bug is Paris-only.**

### Why the cosmetic items bundle into v4.3.0

Per the brainstorming cost-benefit analysis, Option B (Paris fix + cosmetic batch) was selected because:
1. Closes the post-v4.2.0 tracked-follow-up list to zero in one release
2. ~10% more session time vs Paris-only Option A; ~50% less release ceremony vs splitting into separate v4.3.0 / v4.4.0
3. Coherent theme: "data-layer + training-pipeline hygiene"
4. Portfolio repo pattern is x.y minor bumps (not x.y.z patch); v4.2.1 patch route was rejected

---

## 3. Scope

### In scope (v4.3.0)

1. **Paris timezone fix** — Drop `tz_convert("UTC")` and restructure mixed-format datetime parser at [data/fetch_paris_weather.py:112-125](data/fetch_paris_weather.py#L112-L125) so all 3 input formats land in naive Europe/Paris local time. Re-fetch + retrain + threshold calibration + README updates.

2. **`train.py` stdout cp1252 sweep** — Replace `→` (and any other non-ASCII chars surfacing during grep) in `print()` statements with ASCII equivalents. Same minimal-fix pattern as `fetch_seoul_weather.py` commit `3467af6`.

3. **NYC + DC MAE rows in README** — Both cities' per-city RF metric tables in [README.md](README.md) predate the `train.py` MAE addition (shipped v4.0.0); add MAE row to align with Seoul's post-v4.2.0 format (RMSE / MAE / MSE / train rows / test rows). Pure docs work — no retraining required for the metric value (re-run `train.py` once per city to capture MAE from stdout).

### Out of scope (deferred / never)

- **Schema changes** — No new columns (e.g. `HOUR_local` vs `HOUR_utc` split). Would be a v5.0.0-class change propagating through `prepare_city_data.py`, `predict.py` schema alignment, every other city's feature engineering.
- **Other-city retraining** — NYC / DC / Chicago do not have the timezone bug; not touched.
- **Reframing v1.4.0 Paris release notes** — Historical, untouched.
- **External cross-validation of Paris timestamps** — e.g. Vélib' Métropole Bastille Day ridership reports. 30+ min investigation; low-probability risk; out of scope unless verification gate is ambiguous.

### Success criteria

| Criterion | Measurable gate |
|---|---|
| Paris RMSE aspirational target | `NEW_PARIS_RMSE < 23.30` (current chronological-split RMSE — expected to drop since cleaner diurnal signal improves fit) |
| Paris RMSE hard ship gate | `NEW_PARIS_RMSE ≤ 30` (do NOT ship if exceeded — investigate; ~30% degradation cap relative to current 23.30). At `23.30 ≤ NEW ≤ 30`: ship after explanation captured in commit message + release notes. |
| All CI green | 7 jobs PASS on the final S7 commit |
| Test threshold recalibrated | `tests/test_model_accuracy.py:20` Paris threshold = `ceil(NEW_PARIS_RMSE × 1.5 / 10) × 10` |
| README Paris row updated | RMSE + top feature in per-city table reflect post-fix values |
| NYC + DC MAE rows present | Both tables have a `MAE` row between `RMSE` and `MSE` |
| `train.py` stdout clean | No `�` cp1252 replacement char on Windows stdout during training |
| Cross-repo Shiny sync | `bike_demand_prediction/PROJECT-STATUS.md` Python hash bumped; Paris RMSE row updated |
| v4.3.0 GitHub release | Published per Rule 11 canonical format |
| Tracked follow-ups block | Empty for first time since pre-v4.2.0 |

---

## 4. Architecture (Files Touched)

| Sub-feature | File | Change |
|---|---|---|
| Paris tz fix | [data/fetch_paris_weather.py:112-125](data/fetch_paris_weather.py#L112-L125) | Restructure mixed-format parser; ~10 lines changed; no new imports |
| Paris tz fix | `data/raw/paris/paris_{trips_hourly,weather,joined}.csv` | Re-aggregated (overwrites in-place) |
| Paris tz fix | `data/processed/paris_bike_sharing.csv` | Re-derived from joined CSV (no code change in `prepare_paris_from_joined()`) |
| Paris tz fix | `models/artifacts/paris/{random_forest_model,feature_columns}.pkl` | Retrained on tz-corrected data |
| Paris tz fix | [tests/test_model_accuracy.py:20](tests/test_model_accuracy.py#L20) | Paris threshold: `50` → `ceil(NEW_RMSE × 1.5 / 10) × 10` |
| train.py stdout | [models/train.py](models/train.py) | Replace any non-ASCII chars in `print()` statements with ASCII equivalents |
| NYC/DC MAE rows | [README.md](README.md) | Add MAE row to NYC RF metric table + DC RF metric table |
| Paris README updates | [README.md](README.md) | Paris row in per-city RMSE table + Paris RF metric table + Paris key-insight prose (if it references old RMSE) |
| PROJECT-STATUS | [PROJECT-STATUS.md](PROJECT-STATUS.md) | Last Commit bump; Paris Trained-Cities row updated; new Phase 14 block; Next Step rewrite |
| Cross-repo | `bike_demand_prediction/PROJECT-STATUS.md` | Python hash bump + Paris RMSE row + Next move rewrite |
| Cross-repo | `bike_demand_prediction/README.md` | Per-city table Paris row update (if present) |

**No new files. No schema changes. No new dependencies.** All edits target existing files.

---

## 5. Data Flow — Paris Fix Detail

### Current logic (BUG) — produces UTC-anchored timestamps

```python
# data/fetch_paris_weather.py:112-125
raw_dates  = pd.to_datetime(frame[DATE_COL], utc=True, errors="coerce")    # AWARE → UTC
naive_mask = raw_dates.isna() & frame[DATE_COL].notna()                    # which rows failed?
if naive_mask.any():
    naive_parsed = pd.to_datetime(frame.loc[naive_mask, DATE_COL], errors="coerce")
    naive_utc = (
        naive_parsed
        .dt.tz_localize("Europe/Paris", ambiguous="infer", nonexistent="shift_forward")
        .dt.tz_convert("UTC")                                              # ← BUG: aligns to UTC
    )
    raw_dates = raw_dates.copy()
    raw_dates[naive_mask] = naive_utc
frame[DATE_COL] = raw_dates                                                # all UTC Timestamps
```

After this, DATE+HOUR is extracted from a UTC datetime, but weather is fetched with `timezone="Europe/Paris"` → join misaligns by 1-2 hours.

### Fixed logic — produces naive Paris-local timestamps

```python
# Replacement for data/fetch_paris_weather.py:112-125
# AWARE rows (2023/2024 ISO with offset): parse → convert to Paris → strip tz
raw_dates  = pd.to_datetime(frame[DATE_COL], utc=True, errors="coerce")
aware_paris = raw_dates.dt.tz_convert("Europe/Paris").dt.tz_localize(None) # naive Paris-local

# NAIVE rows (2022): parse without tz_localize — already Paris-local by convention
naive_mask = raw_dates.isna() & frame[DATE_COL].notna()
if naive_mask.any():
    naive_paris = pd.to_datetime(
        frame.loc[naive_mask, DATE_COL], errors="coerce"
    )                                                                       # naive, assumed Paris-local

    aware_paris = aware_paris.copy()
    aware_paris[naive_mask] = naive_paris

frame[DATE_COL] = aware_paris
```

### Net change vs current

- **Remove:** `.dt.tz_localize("Europe/Paris", ambiguous="infer", nonexistent="shift_forward").dt.tz_convert("UTC")` on naive rows
- **Add:** `.dt.tz_convert("Europe/Paris").dt.tz_localize(None)` on aware rows
- **Result:** Both branches produce naive datetimes in Europe/Paris wall-clock time

### Why this works for all 3 input formats

| Year | Source format | After fix |
|---|---|---|
| 2022 | `'2022-01-01T00:00:00'` (naive) | Treated as Paris-local (opendata.paris.fr convention) |
| 2023 | `'2023-01-01T07:00:00+01:00'` (aware) | Parsed to UTC → converted to Paris → tz-stripped → naive Paris-local |
| 2024 | `'2024-01-02 19:00:00.000 +0100'` (aware) | Same as 2023 |

### Downstream alignment

- Trips DATE+HOUR (Paris-local) ✓ joins with weather DATE+HOUR (Paris-local from `timezone="Europe/Paris"`)
- HOUR feature interpretable as Paris wall-clock hour → cross-city HOUR comparison story preserved

### Diurnal sanity check (post-fetch, pre-retrain)

```python
df.groupby('HOUR')['RENTED_BIKE_COUNT'].mean()
# Should show peak around HOUR=17-19 (Paris evening commute)
# Trough around HOUR=3-5
```

If inverted or shifted by 1-2 hours, the fix is incorrect — halt before retraining.

---

## 6. Risk Mitigation — Paris Fix Specific

### The 2022 naive-rows assumption

**Assumption:** opendata.paris.fr stores 2022 timestamps in Paris-local wall-clock time (not UTC). The fix relies on this.

**If wrong:** the fix flips the bug for 2022 instead of fixing it. 2022 portion of dataset gets 1-2 hour shift in the opposite direction.

### Layer 1 — Documentation check (S6 spec phase, BEFORE coding)

Browse the opendata.paris.fr dataset metadata page (URL at [data/fetch_paris_weather.py:88](data/fetch_paris_weather.py#L88)):
```
https://opendata.paris.fr/explore/dataset/comptage-velo-historique-donnees-compteurs/information/
```

Read the "Schéma de données" / fields description for timezone declaration. If explicitly stated for 2022, the empirical verification (Layer 2) becomes confirmation rather than discovery.

### Layer 2 — Empirical verification gate (S7 mid-execution, AFTER re-fetch, BEFORE retrain)

**HARD GATE — DO NOT SKIP.** Two diagnostic probes against the new `data/processed/paris_bike_sharing.csv`:

**Probe A — Cross-year peak HOUR comparison:**
```python
df_2022 = df[df['DATE'].str.endswith('/2022')]
df_2023 = df[df['DATE'].str.endswith('/2023')]
print('2022 peak HOUR:', df_2022.groupby('HOUR')['RENTED_BIKE_COUNT'].mean().idxmax())
print('2023 peak HOUR:', df_2023.groupby('HOUR')['RENTED_BIKE_COUNT'].mean().idxmax())
```

Expected: both years peak at HOUR=17/18/19 (Paris evening commute). 2023 is unambiguously Paris-local (had explicit `+01:00` offset). If 2022 matches, naive-as-Paris-local assumption holds. If 2022 peaks one hour earlier than 2023, 2022 is actually UTC.

**Probe B — DST transition detector (independent confirmation):**
```python
df_jan22 = df[df['DATE'].str.contains('/01/2022')]   # winter, Paris=UTC+1
df_jul22 = df[df['DATE'].str.contains('/07/2022')]   # summer, Paris=UTC+2
print('Jan 2022 peak HOUR:', df_jan22.groupby('HOUR')['RENTED_BIKE_COUNT'].mean().idxmax())
print('Jul 2022 peak HOUR:', df_jul22.groupby('HOUR')['RENTED_BIKE_COUNT'].mean().idxmax())
```

Expected: both same wall-clock hour (Paris-local commuter pattern is anchored to wall time, not UTC). If they differ by 1 hour, 2022 is UTC-encoded and the "shift" is DST.

### Layer 2 — Decision matrix (post-probes)

| Probe A result | Probe B result | Diagnosis | Action |
|---|---|---|---|
| 2022 peak ≈ 2023 peak | Jan/Jul same | 2022 IS Paris-local | ✅ Proceed to retrain |
| 2022 peak = 2023 peak − 1 | Jan/Jul differ by 1 | 2022 IS UTC | Apply Layer 3 fallback patch + re-fetch (~10 min) + re-verify |
| Both years peak at HOUR 3-5 | — | Fix made it worse, inverted | Halt; deep-dive; do not commit |
| Probes disagree | — | Confounding factor (e.g. holiday seasonality) | Pull more years' peak comparisons; defer commit until clear |

### Layer 3 — Fallback patch (pre-written, ready to apply)

If Probes flag 2022-as-UTC, replace the NAIVE branch with:

```python
# Naive-string branch — IF 2022 turns out to be UTC-encoded
naive_paris = (
    pd.to_datetime(frame.loc[naive_mask, DATE_COL], errors="coerce")
    .dt.tz_localize("UTC")              # treat as UTC instead of Paris-local
    .dt.tz_convert("Europe/Paris")      # convert to Paris-local
    .dt.tz_localize(None)               # strip tz → naive Paris-local
)
```

Re-fetch takes ~5-15 min; no commit boundary disturbed because fix commit hasn't shipped yet.

### Cost vs comprehensiveness

A heavier alternative (cross-validation against Vélib' Métropole Bastille Day ridership reports, météo-france weather sync timestamps) would add 30+ min for low-probability risk. The 2-probe gate + documentation check + pre-written fallback patch gives ~95% coverage at ~10 min cost. **Accepted.**

---

## 7. Sprint Shape — S6 / S7 / S8 Task Allocation

### S6 — THIS SESSION (spec + plan)

- ✅ Brainstorming (5 design sections approved)
- ⏳ Write this spec doc; commit + push
- ⏳ Invoke `superpowers:writing-plans` → `docs/superpowers/plans/2026-05-21-paris-timezone-fix.md`; commit + push
- **End-state:** spec + plan on main; S7 boots cold via workflow_status.md bridge

### S7 — Execute (2 commits)

**Pre-action:** workflow_status.md `## In Progress` block listing the 2 planned commits.

#### Commit A — Paris timezone fix + retrain + threshold

1. Edit `data/fetch_paris_weather.py:112-125` per §5 fixed logic
2. Re-run `python -u -m data.fetch_paris_weather 2>&1` in background (~5-15 min: counter re-aggregation + Open-Meteo re-fetch + join)
3. **HARD GATE** — run Probes A + B from §6 Layer 2; on FAIL apply Layer 3 fallback + re-fetch + re-verify
4. On PASS: `python -u -m models.train --city paris --data data/processed/paris_bike_sharing.csv`; capture `NEW_PARIS_RMSE`, `NEW_PARIS_MAE`, new top-10 features
5. Edit `tests/test_model_accuracy.py:20` Paris threshold: `50` → `ceil(NEW_PARIS_RMSE × 1.5 / 10) × 10`
6. Run `pytest -m slow tests/test_model_accuracy.py::test_city_rmse_within_threshold -v -k paris` locally to confirm gate passes
7. Stage 8 files: `data/fetch_paris_weather.py`, `data/raw/paris/paris_trips_hourly.csv`, `data/raw/paris/paris_weather.csv`, `data/raw/paris/paris_joined.csv`, `data/processed/paris_bike_sharing.csv`, `models/artifacts/paris/random_forest_model.pkl`, `models/artifacts/paris/feature_columns.pkl`, `tests/test_model_accuracy.py`
8. Commit message: `fix(paris): align trips to Paris-local timezone; retrain on corrected diurnal signal`
9. Push to `origin/main`

#### Commit B — Cosmetic batch (train.py stdout + NYC/DC MAE rows)

1. Grep `models/train.py` for non-ASCII chars in `print(` statements; review matches
2. Replace unambiguous chars with ASCII equivalents (`→` → `->`, em-dash → `--`); skip semantically loaded chars
3. `python -u -m models.train --city nyc --data data/processed/nyc_bike_sharing.csv`; capture `NYC_MAE` from stdout
4. Same for DC; capture `DC_MAE`
5. Edit `README.md` NYC RF metric table + DC RF metric table: add MAE row between RMSE and MSE rows
6. **R4 audit step** — while in those tables, re-verify RMSE values against current measured RMSE (catch any predating v4.0.0 chronological-split correction)
7. Stage `models/train.py`, `README.md`
8. Commit message: `chore(train): ASCII stdout + add MAE rows to NYC + DC RF tables`
9. Push to `origin/main`
10. **NYC/DC `.pkl` artifacts not committed** — mtime-only change, no model drift (random_state + data + hyperparams unchanged)

**Post-action:** Update workflow_status.md; tick S7 checkboxes; set Next action to S8.

### S8 — Close-out (smoke + docs + release + cross-repo)

**Pre-action:** workflow_status.md `## In Progress` block.

1. **CI verification** — `gh run list` confirm both S7 commits green; if accuracy gate failed in cloud, bump threshold in patch commit
2. **T7 FastAPI smoke** — `uvicorn api.app:app`; POST a Paris prediction (sample: HOUR=18, TEMPERATURE=24, SEASONS=Summer, city="Paris"); verify response in plausible range; POST unchanged Seoul winter 8AM (1570.26) as cross-city sanity check
3. **T9 README staleness sweep** — explicit grep: `grep -rni "Paris.*23\.30\|HOUR (0\.634)" .`; verify only `docs/superpowers/` matches remain; update Paris row in per-city RMSE table + Paris RF metric table + Paris key-insight prose if present
4. **PROJECT-STATUS.md (Python)** — Last Commit bump; Paris row in Trained City Models updated with `NEW_PARIS_RMSE`; new Phase 14 block under Roadmap describing v4.3.0; Next Step rewritten v4.2.0 SHIPPED → v4.3.0 SHIPPED; new priority slot for next-thread candidate
5. **Bundled docs commit** (Python repo): README hunks + PROJECT-STATUS.md
6. **T9b cross-repo Shiny sync** — `bike_demand_prediction/PROJECT-STATUS.md` Python hash bump + Paris RMSE row + Next move rewrite; `bike_demand_prediction/README.md` per-city table Paris row update (if present); bundled docs commit
7. **T10 v4.3.0 GitHub release** — title `v4.3.0 — Paris Timezone Fix + Cross-City Table Alignment`; What's-included tables (Paris old vs new metrics, 2 commits, cosmetic items closed); Roadmap section
8. **Close out workflow_status.md** — Status header dated; Last Session block; **Tracked follow-ups block → empty**; Next action set to next-thread candidate

---

## 8. Risk Register / Pre-Mortem

### Approach risks (in-session execution)

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| **R1** | Verification gate probes give ambiguous result (e.g. 2022 peak HOUR differs by 0.5 from 2023 due to holiday seasonality, not timezone) | Low | Medium | 3rd probe in spec: total daily trip counts on Bastille Day 2022 sanity-checked against any public Vélib reference. Decision matrix §6 covers ambiguity → defer commit until clear. |
| **R2** | `NEW_PARIS_RMSE` *increases* post-fix (>23.30) | Low | High | Hard threshold: do not ship if `NEW_RMSE > 30` (~30% degradation cap). If 23.30 ≤ NEW ≤ 30, investigate before shipping. Fix conceptually improves alignment — rising RMSE suggests something else broken. |
| **R3** | `train.py` stdout sweep finds more non-ASCII chars than known `→` and bloats Commit B | Low | Low | Grep `print(` calls first; only swap unambiguous ASCII equivalents (`→` → `->`, em-dash → `--`); skip semantically loaded chars. |
| **R4** | NYC/DC MAE row addition surfaces stale RMSE values predating v4.0.0 chronological-split correction | Medium | Low | While editing MAE rows, re-verify RMSE values against current measured RMSE. Update if drift; fold into Commit B. |
| **R5** | Cosmetic Commit B after Paris Commit A creates transient stale-state on main between pushes | Negligible | Negligible | Single-user portfolio; commits seconds apart; no clone-window risk. Could bundle into single commit if preferred. |
| **R6** | Verification gate passes locally but CI accuracy gate fails on cloud (random_state cloud-vs-local drift) | Very Low | Medium | `train.py` pins `random_state=42`; sklearn version pinned in `requirements.txt`. If it happens, threshold bump in patch commit (same as Seoul v4.2.0). |

### Cross-session context-loss risks (S6→S7→S8)

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| **CL1** | S7 cold-boot via workflow_status.md doesn't capture all design decisions | High if status is only bridge | High | **Spec is authoritative**, not workflow_status. Plan file has every step verbatim with checkboxes. S7 re-entry command names the plan file path explicitly. |
| **CL2** | S7 cold-boot Claude skips the verification gate after re-fetch | Medium | High | Plan file lists gate as explicit numbered task with own checkbox + bold "HARD GATE — do not skip" prefix. Spec §6 dedicates a callout. workflow_status.md S7 Next action names the gate. |
| **CL3** | S7→S8 boundary loses `NEW_PARIS_RMSE`, `NEW_PARIS_MAE`, top-10 features | High if not explicitly written | Medium | S7 close-out writes these into workflow_status.md "Last Session" block. S8 boots with values in scope; README hunks reference them directly. |
| **CL4** | S8 docs sweep skips train.py stdout fix or NYC/DC MAE rows | Medium | Medium | workflow_status.md "Tracked follow-ups" block stays populated through S7; S8 release notes template enumerates all 3 sub-features. Pre-mortem note in plan: "track each follow-up to zero before closing v4.3.0". |
| **CL5** | S8 release notes get commit hashes wrong (pulled from memory not git log) | Medium | Low | S8 process includes `git log --oneline -10 main` before drafting release notes; release notes commit table populated from git log output, not session recall. |

### Out-of-scope risks (acknowledged, deferred)

- **OOS1** — Post-fix Paris RMSE drop reveals other data-quality issues (counter outages, missing days). Defer to v4.4.0+.
- **OOS2** — Future audit finds analogous timezone issue elsewhere. Separate fix.
- **OOS3** — Schema additions (`HOUR_local` vs `HOUR_utc`). v5.0.0 if ever justified.

---

## 9. Re-Entry Commands (Cold-Restart Bridges)

| Boundary | Re-entry command |
|---|---|
| After S6 | `"resume bike-demand-ml-system — start v4.3.0 S7: execute Paris timezone fix per the plan at docs/superpowers/plans/2026-05-21-paris-timezone-fix.md"` |
| After S7 | `"resume bike-demand-ml-system — start v4.3.0 S8: smoke + docs + release"` |
| After S8 | workflow_status.md re-entry command rolls forward to next thread (currently undefined) |

---

## 10. Reference Files

- **Predecessor spec:** [docs/superpowers/specs/2026-05-20-seoul-data-refresh-design.md](docs/superpowers/specs/2026-05-20-seoul-data-refresh-design.md)
- **Predecessor plan:** [docs/superpowers/plans/2026-05-20-seoul-data-refresh.md](docs/superpowers/plans/2026-05-20-seoul-data-refresh.md)
- **Seoul tz fix commit (precedent):** `176e182`
- **train.py stdout cp1252 precedent fix:** `3467af6` (Seoul fetch script)
- **Workflow status (live):** `~/.claude/projects/d--OneDrive-Developer-Data-Engineering-bike-demand-ml-system/memory/workflow_status.md`
