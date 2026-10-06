# V11: restored cero and complete CPI development benchmark

Cero is accessible again and disk maintenance freed about 20 GiB. Research resumed on the server. A complete eleven-component CPI development test now shows a promising **+0.1342** numeric-score improvement over deployed V8, with a descriptive paired 95% interval **[+0.1014, +0.1668]**. This is **not** the requested full-track confirmation: CPI has weight 0.10, and model selection used these development outcomes. No CodaBench submission was made; the CPI 2017–2021 confirmation remains unopened.

## Server repair

Disk exhaustion and SSH MaxStartups drops were confirmed in system logs. Cache eviction, log rotation and journal limits left 22 GiB free immediately after maintenance, and 21 GiB at the end of the experiment. The production collector and export worker retained their original PIDs and restart counters. The durable market-data journal, original S3 data, colleague worktrees and Docker images were preserved. Details and installed configuration are in `ops/cero-recovery-20261006/README.md`.

The V10 bundle was transferred to cero and all 198 file hashes verified. Its failed COT confirmation remains failed; restoring access did not change the result or authorize a submission.

## Data and evaluation

- **199 consecutive original releases**, reference months June 2000–December 2016, downloaded from the [FRASER BLS archive](https://fraser.stlouisfed.org/title/consumer-price-index-6838). All eleven official CPI components are present in every release. Each extracted row records its PDF hash, URL, table, line and revision marker. CPI-U and CPI-W tables cannot be mixed by the parser.
- The actual embargo header establishes availability. The September 2013 release used its [rescheduled October 30 publication date](https://www.bls.gov/bls/updated_release_schedule.htm), not the original October 16 announcement. Other ambiguities, such as a nearby seasonal-revision announcement, are rejected rather than guessed.
- Nine preceding component changes are reconstructed from releases available at each month-end. Gasoline uses the EIA regular-gasoline series, with a two-day buffer before cutoff. Targets are the next original publication's reported SA changes.
- **192 usable historical cases** after seven initial months without nine-month histories. Evaluation: **120 months in 2007–2016**, 11 entities per month, 40 equal-weight calendar quarters. Models refit annually using only targets released before January 1; interval calibration uses at most 36 already resolved forecasts. No exclusions depend on forecast error.
- The research baseline matches the actual V8 predictor and table parser on **2,112 entity/case rows**. V8 source and model were not modified. The official scorer 5.2.2 is imported unchanged, with a declared fixed mean3 / ±1 local naive reference.
- Two-quarter circular paired bootstrap, 20,000 draws, seed 10. These are development intervals after comparing alternatives, not independent confirmation or estimates of the competition leaderboard.

## Results

The initial grid contains nine point methods with two interval choices each: short/long means, median, a gasoline bridge, separate Ridge models, Huber models and shallow boosting. Two subsequent routing rules add four variants, for **22 alternatives** in total. The routing follow-up was designed after inspecting the initial development results and is explicitly labeled as such.

| Method | Numeric score | MAE, percentage points | 90% interval coverage | Paired improvement vs V8, 95% interval |
|---|---:|---:|---:|---:|
| Deployed V8 numeric rule | 0.4954 | 0.9765 | 84.4% | — |
| Gasoline bridge, causal intervals | 0.6161 | 0.5068 | 92.6% | [+0.0899, +0.1515] |
| Per-component Huber, V8 widths | 0.6178 | 0.4769 | 86.4% | [+0.0918, +0.1539] |
| Per-component Huber, causal intervals | 0.6263 | 0.4769 | 92.5% | +0.1310 [+0.0995, +0.1630] |
| Guarded component routing, causal intervals | **0.6296** | **0.4709** | **92.9%** | **+0.1342 [+0.1014, +0.1668]** |

The main improvement comes from using contemporaneous gasoline information for gasoline, energy and headline CPI. This agrees with the component-based approach described in the [Cleveland Fed nowcasting methodology](https://www.clevelandfed.org/-/media/project/clevelandfedtenant/clevelandfedsite/indicators-and-data/inflation-nowcasting/nowcasting_faqs.pdf): slow inflation components and volatile gasoline need different forecasting methods.

The first Huber model worsened shelter MAE from 0.0742 to 0.1115. The guarded router chooses a different method only when its mean absolute-error advantage over V8 exceeds one estimated standard error over at least 24 completed origins. It retains V8 for shelter in 75/120 cases; shelter MAE becomes 0.0725. The guard is an engineering selection rule, not a hypothesis-test guarantee.

| Component | V8 MAE | Guarded route MAE |
|---|---:|---:|
| Headline | 0.2926 | 0.1380 |
| Energy | 2.9078 | 1.1700 |
| Gasoline | 5.3726 | 1.8591 |
| Shelter | 0.0742 | 0.0725 |
| Medical care | 0.1735 | 0.1600 |
| Transportation services | 0.3331 | 0.2669 |
| New vehicles | 0.2449 | 0.2517 |

The selected route's average improvement is positive in each of the ten evaluation years, ranging from +0.0567 in 2014 to +0.2219 in 2007. New vehicles still deteriorate slightly; the result is not a uniform win on every component.

## Why this does not authorize a submission

At the fixed CPI weight of 0.10, the best development route contributes only **+0.01342 [ +0.01014, +0.01668 ]** to the full-track analogue if other families stay unchanged. The required lower endpoint is **+0.10**. We do not renormalize the score to the improved family or round a nearly passing interval upward.

Additional limitations:

1. BLS release changes are rounded to 0.1 percentage point; the competition component table/targets use index-derived precision. The reconstructed older history may miss annual seasonal revisions outside the last three reported months. The benchmark is a complete-component diagnostic, not an exact replica of the ALFRED vintage table.
2. The EIA archive is not certified here as original release vintages. The official corpus supplies a similar weekly price series, but that does not certify every historical source row.
3. Routing uses up to 36 completed historical forecast errors. Deployment requires frozen, pre-cutoff calibration state; the task's nine-month table cannot reconstruct that state alone. No V11 runtime/model artifact has been exported or claimed submission-ready.
4. Numeric scores omit the production citation/NLI pass and do not equal leaderboard scores. Docker execution verifies the research environment; it is not submission-image parity.

Keep 2017–2021 unopened until there is a frozen deployable procedure, a stronger input-equivalence audit, and a candidate across enough families to make the full-track gate attainable. The V10 COT confirmation is already consumed and cannot be reused as fresh evidence.

## Reproduction

On cero, `/home/antonnos/agenthon-t4-lab`, run `bash scripts/run_v11_cpi.sh`. The existing EIA development CSV and pinned official scorer clone are required. The runner limits Docker to two CPUs, 2 GiB RAM, 256 processes and one BLAS/OpenMP thread; fitting has no network access.

Research image: `agenthon-t4:v9-lab`, image ID `sha256:d93cc8d85165b34c9580d0b9941c6a5135c98c61341842772dda32e7f1d33455`. Four CPI parsing/date tests pass. The full 199-release parse has zero errors, and all initial numerical predictions were exactly equal after adding saved prequential traces.

Primary artifacts on cero:

- `research/v11/plan.json`: initial design and unchanged full-track gate.
- `lab/v11_cpi_{archive,parse,experiment,router}.py`: source crawl, audited extraction, causal models and component selection.
- `test-output/v11-cpi/download-manifest.json`: source hashes and release dates.
- `test-output/v11-cpi/{parsed-releases,dataset,prequential-predictions}.json`: auditable inputs and predictions.
- `test-output/v11-cpi/{development-initial,development,routing-development}.json`: all results and selection traces, including failed alternatives.
