# Phase 2 - Data Layer Audit Plan

## 1. Phase Title

Data Layer: Ingestion, Schema, Timezone Normalization, Data Quality, Caching, and Dataset Contracts

## 2. Scope

This phase audits all modules dynamically discovered as data producers, data consumers, data validators, data normalizers, data selectors, cache handlers, resamplers, and dataset extractors.

Runtime discovery must identify and audit:

- All modules that read or write market data, CSV data, API data, live feed data, cached data, snapshot data, or extracted backtest datasets.
- All modules importing data libraries such as pandas, CSV readers/writers, broker SDK data calls, websocket tick handlers, or resampling utilities.
- All schema-defining constants, header lists, rename maps, required-column checks, validation helpers, and dataframe normalizers.
- All date/time parsing, timezone conversion, market-hours filtering, resampling, deduplication, missing-bar detection, and OHLCV/OI transformation paths.
- All UI/data-selection modules that decide which datasets are available for execution.

Why this layer matters:

- Incorrect data silently creates false backtest results.
- Timestamp drift, schema drift, duplicate bars, stale caches, and missing rows directly affect trading decisions.

Dependencies with other layers:

- Depends on Phase 1 discovery inventory.
- Feeds Phase 3 Execution Core with normalized datasets.
- Feeds Phase 7 UI with data availability state.
- Feeds Phase 8 Persistence with storage contracts.

## 3. Audit Objectives

Correctness means:

- Every supported data source has an explicit schema contract.
- Every timestamp is normalized according to the system timezone policy before execution.
- All data used for backtests is sorted, deduplicated, parseable, market-session aware, and numerically valid.
- Cache use never masks stale or incompatible data.
- Live, API, and CSV datasets converge to the same execution-ready OHLCV contract.

Failure looks like:

- Mixed timezone data.
- Naive timestamps interpreted inconsistently.
- Missing columns accepted silently.
- Live data files with schema drift.
- Resampled bars containing incomplete or duplicate intervals.
- Caches returning stale data without visibility.
- UI allows execution for a dataset/timeframe that does not exist.

Production-grade means:

- Data contracts are explicit, testable, and enforced.
- Rejected datasets produce actionable errors.
- Schema changes are detected before execution.
- Data quality statistics are visible.
- No hidden data fallback occurs without terminal/status disclosure.

## 4. Deep Audit Checklist

### A. Bug Detection

- Dynamically list all data source modules and classify source type: local CSV, broker API, live websocket, generated snapshot, extracted dataset, cache.
- Extract every required-column check and compare with actual produced schemas.
- Verify every data path has deterministic timestamp normalization.
- Verify aware timestamps are converted to the system timezone.
- Verify naive timestamps have one documented interpretation.
- Verify no module filters by `date.today()` or `datetime.now()` without explicit timezone.
- Verify all market-hour filtering uses normalized exchange timezone.
- Verify resampling drops incomplete bars intentionally and documents the rule.
- Verify volume and OI semantics are consistent by instrument type.
- Verify VIX or non-volume assets are handled under explicit schema rules.
- Verify duplicate rows and duplicate timestamps are detected or deduplicated deterministically.
- Verify missing bar detection exists where required.
- Verify cache keys include all parameters affecting data identity.
- Verify cached files include enough metadata to prove compatibility.
- Verify file readers handle empty files, partial writes, parser errors, and concurrent writer races.
- Verify UI data availability matches actual filesystem/API availability.

### B. Root Cause Analysis Template

- Issue: schema, timestamp, data quality, cache, or availability defect.
- Why it happens: missing contract, inconsistent parser, stale cache, producer/consumer drift, timezone ambiguity, partial write, or silent fallback.
- Where it originates: data producer, normalizer, selector, cache reader, resampler, or execution handoff.
- When it triggers: collection, selection, extraction, normalization, resampling, cache hit, execution.

### C. Fix Design Template

- Exact fix approach: strengthen schema check, centralize timestamp helper, add metadata, reject stale cache, expose terminal error, or align producer/consumer contract.
- Alternatives: local validation, shared schema registry, typed dataframe adapter, contract tests.
- Tradeoffs: strictness versus backwards compatibility, runtime cost, migration effort, storage churn.

### D. Pre-Fix Validation

- Inventory all current data files and generated schemas.
- Confirm all supported source types.
- Confirm consumer expectations for each source type.
- Confirm historical data compatibility requirements.
- Confirm whether existing cached data should be migrated, invalidated, or quarantined.

### E. Edge Cases

- Empty CSV.
- Header-only CSV.
- Partial row written while reader reads.
- Duplicate timestamp for same instrument.
- Same timestamp for multiple instruments.
- Mixed timezone rows.
- Naive timestamp rows.
- DST-like timezone library behavior even if exchange timezone does not use DST.
- Non-trading day.
- Market open partial first bar.
- Instrument with zero volume.
- Option OI missing.
- VIX without volume.
- API returns no rows.
- Cache partially covers request.

### F. Post-Fix Sanity Checks

- Run schema validation against every current data file.
- Run timestamp normalization audit and confirm timezone.
- Run duplicate and missing-bar audit.
- Run sample extraction for each data type.
- Run normalization into execution contract.
- Verify terminal/logs show rejected data reasons.
- Verify no stale cache is used after source schema change.

### G. Dead Code Detection

- Identify data loaders no longer reachable from UI, API, or execution paths.
- Identify obsolete schema maps.
- Identify unused cache directories and stale generated files.
- Identify duplicate normalizers or timestamp helpers.

### H. Cleanup After Fix

- Consolidate schemas into a documented registry.
- Remove obsolete cache formats after migration.
- Delete abandoned data adapters.
- Add clear naming conventions for generated data files.

## 5. Invariants & Contracts

- Execution-ready data has `Date` index or column convertible to DatetimeIndex plus `Open`, `High`, `Low`, `Close`, `Volume`.
- Live raw equities schema is stable.
- Live raw options schema is stable and includes option metadata.
- Live raw VIX schema is explicitly special-cased.
- All execution timestamps are normalized before Backtrader ingestion.
- Data sorted ascending by timestamp before execution.
- No duplicate execution timestamps remain for a single-instrument dataset.
- Market-hour filtering is deterministic.
- Cache identity includes symbol, instrument token, interval, date range, data type, and source mode.

## 6. Failure Injection Strategy

- Corrupt timestamps in a copied dataset.
- Remove one required column.
- Add duplicate bars.
- Add mixed timezone rows.
- Add rows outside market hours.
- Create empty files for expected datasets.
- Simulate partial CSV writes.
- Rename or remove cache metadata.
- Force stale cache hit.

Expected behavior:

- Invalid data is rejected before execution.
- Errors identify file, column, row category, and validation stage.
- No invalid dataset reaches execution core.

## 7. Observability Requirements

- Data source selected.
- File/API endpoint used.
- Row counts before and after each transform.
- Timestamp timezone detected.
- Rows dropped for NaN, duplicates, outside-hours, parser failures.
- Cache hit/miss/stale reason.
- Schema version or inferred schema.
- Extraction output path and row count.

## 8. Production Hardening Checklist

- Atomic writes for generated datasets.
- Readers tolerate concurrent writes safely.
- Cache invalidation on schema/version change.
- Strict source-to-execution schema adapter.
- Explicit handling for non-trading days.
- Data quality thresholds before execution.
- Idempotent resampling.
- Bounded file sizes.

## 9. Regression Protection Strategy

- Maintain golden mini-datasets for each source type.
- Contract-test every producer against every consumer.
- Snapshot schemas from current generated files.
- Enforce no new data path without schema validation.
- Run timestamp audit on every generated file.

## 10. Exit Criteria

- All data producers and consumers are discovered.
- All schemas are documented and validated.
- All timestamp paths comply with timezone contract.
- No Critical or High data integrity issues remain open.
- Data extraction works for every supported executable data type.
- Result file `Phase_2_Data_Layer_Result.md` is complete with final verdict.

## Result File Mapping

Write findings to:

`Sanity_Checklist/Sanity_Checklist_Result/Phase_2_Data_Layer_Result.md`

Mapping rules:

- Schema and timestamp failures map to Issue Log Table.
- Data quality and edge-case test outcomes map to Edge Case Failures Observed.
- Cache and stale-data risks map to Regression Risks Identified.
- Unreachable loaders and obsolete adapters map to Dead Code Identified.
- Normalization/extraction validation maps to Fix Validation Results.
