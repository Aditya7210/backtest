# Phase 3 - Execution Core Audit Plan

## 1. Phase Title

Execution Core: Backtest Engine, Broker Simulation, Data Feed Binding, Result Integrity, and Error Classification

## 2. Scope

This phase audits the core logic that turns validated data and strategy classes into backtest results. Scope is resolved dynamically.

Runtime discovery must identify and audit:

- All modules that instantiate or call the backtesting framework discovered in Phase 1.
- All modules that bind dataframes or files into execution feeds.
- All broker/capital/commission/slippage/order-guard logic.
- All analyzers, result builders, trade log writers, failure result builders, and execution error classifiers.
- All execution adapters that route API, CSV, live-extracted, or generated data into the same engine contract.
- All modules that transform strategy output into result artifacts.

Why this layer matters:

- It is the numerical correctness boundary.
- Any defect here can produce plausible but wrong performance, trade, P&L, or risk output.

Dependencies with other layers:

- Depends on Phase 2 data contracts.
- Feeds Phase 4 Execution Manager with deterministic task result semantics.
- Feeds Phase 8 Persistence with result artifacts.
- Feeds Phase 7 UI with displayed execution results.

## 3. Audit Objectives

Correctness means:

- Execution receives a validated, deterministic dataset.
- Broker state is isolated per run.
- Strategy class is validated before execution.
- Orders, fills, portfolio value, and analyzers are internally consistent.
- Every failure returns a structured failed result with stage, severity context, and actionable message.
- Success cannot occur without valid final value and artifacts.

Failure looks like:

- Backtest succeeds with empty, duplicate, unsorted, or wrong-timezone data.
- Broker state leaks between tasks.
- Strategy exceptions are hidden or collapsed into generic messages.
- Result reports disagree with executed bars.
- Trade logs are missing or inconsistent with final portfolio value.
- Order guard changes behavior silently.

Production-grade means:

- Deterministic execution.
- Isolated broker and strategy instances.
- Complete terminal visibility.
- Consistent result schema.
- No hidden partial success.
- Defensive checks around row counts, bars processed, and result validity.

## 4. Deep Audit Checklist

### A. Bug Detection

- Identify every execution entrypoint and supported execution mode.
- Verify unsupported modes fail explicitly.
- Verify input task validation is strict and stage-classified.
- Verify data feed receives only execution-normalized data.
- Verify row count before/after engine preparation is logged and sanity-checked.
- Verify broker cash, commission, and internal state reset each run.
- Verify strategy class is not reused with mutable leaked state.
- Verify analyzers are attached and failure-safe.
- Verify strategy exceptions are trapped with type and message.
- Verify warnings are surfaced.
- Verify final value is numeric and finite.
- Verify result artifact write failure behavior.
- Verify trade logs and closed-trade summaries align with analyzer output.
- Verify short-selling/order-guard behavior is explicit and testable.
- Verify execution does not mutate source dataframe unexpectedly.
- Verify failure classifications distinguish validation, data fetch, execution, timeout, strategy, API, and system errors.

### B. Root Cause Analysis Template

- Issue: numerical, data-feed, strategy execution, broker, analyzer, artifact, or classification defect.
- Why it happens: weak validation, shared mutable state, framework misuse, implicit default, missing exception path, or result schema drift.
- Where it originates: execution router, core engine, framework adapter, broker setup, analyzer, result builder.
- When it triggers: validation, feed creation, broker setup, strategy run, analyzer extraction, result generation, artifact write.

### C. Fix Design Template

- Exact fix approach: add invariant check, isolate state, strengthen result builder, expose error, adjust framework adapter, or add contract test.
- Alternatives: local guard, shared execution contract, dedicated engine adapter, stricter task schema.
- Tradeoffs: strict validation versus compatibility, runtime overhead, framework-specific coupling.

### D. Pre-Fix Validation

- Confirm expected execution result schema.
- Confirm supported strategy API.
- Confirm broker assumptions and commission model.
- Confirm allowed order semantics.
- Confirm artifact requirements.
- Confirm whether existing strategies rely on undocumented behavior.

### E. Edge Cases

- Empty dataset.
- Dataset with exactly minimum row count.
- Constant prices.
- NaN values after normalization.
- Strategy raises in initialization.
- Strategy raises mid-bar.
- Strategy never trades.
- Strategy submits invalid order size.
- Sell order while flat.
- Final value is NaN or infinite.
- Analyzer returns unexpected structure.
- Artifact directory unwritable.
- Extremely large dataset.

### F. Post-Fix Sanity Checks

- Run minimal deterministic strategies.
- Run no-trade strategy.
- Run single-buy-hold strategy.
- Run strategy that intentionally raises.
- Run short-disabled sell scenario.
- Verify row/bar sanity checks.
- Verify result schema and artifact paths.
- Verify terminal shows exact failure stage.

### G. Dead Code Detection

- Identify legacy execution entrypoints not reachable from manager or UI.
- Identify duplicate result builders.
- Identify unused analyzers.
- Identify unused strategy guards.
- Identify stale error classification helpers.

### H. Cleanup After Fix

- Consolidate result schemas.
- Remove obsolete adapters.
- Move framework-specific assumptions into one boundary.
- Document strategy execution contract.

## 5. Invariants & Contracts

- Every execution task returns exactly one structured result.
- Result status is only `SUCCESS` or `FAILED`.
- Success includes numeric final value and artifact path.
- Failure includes non-empty error message.
- Execution dataset must be sorted and deduplicated.
- Broker state is reset per task.
- Prepared rows must equal bars processed unless a documented framework exception exists.
- Terminal receives validation, normalization, execution start, execution end, and failure logs.

## 6. Failure Injection Strategy

- Use strategies that raise at different lifecycle points.
- Use malformed datasets.
- Make artifact directory read-only in a disposable environment.
- Force analyzer failure.
- Force unsupported task mode.
- Use data with invalid timestamps and NaNs.

Expected behavior:

- Engine fails explicitly with structured result.
- No false success.
- Terminal contains enough context to diagnose.

## 7. Observability Requirements

- Task ID and symbol on every execution log.
- Rows loaded, rows normalized, rows passed to framework.
- Broker initial state and final value.
- Strategy class identity.
- Error type and stage.
- Artifact path.
- Warning capture.
- Runtime duration.

## 8. Production Hardening Checklist

- Hard validation before framework call.
- Framework run isolated from prior tasks.
- Bounded warnings/log output.
- Structured failure result for every exception path.
- Artifact writes are atomic or failure-visible.
- No unchecked NaN/inf result values.
- Engine-level deterministic smoke tests.

## 9. Regression Protection Strategy

- Golden strategy fixtures.
- Golden result schema checks.
- Row/bar invariant tests.
- Failure classification tests.
- Broker isolation tests.
- Artifact generation tests.
- No new execution mode without contract test.

## 10. Exit Criteria

- All execution core modules are discovered.
- All execution modes are contract-tested.
- Core numerical invariants are verified.
- All failure paths produce structured, observable results.
- No Critical or High execution core issues remain open.
- Result file `Phase_3_Execution_Core_Result.md` is complete with final verdict.

## Result File Mapping

Write findings to:

`Sanity_Checklist/Sanity_Checklist_Result/Phase_3_Execution_Core_Result.md`

Mapping rules:

- Engine correctness defects map to Issue Log Table.
- Deliberate strategy/data failures map to Edge Case Failures Observed.
- Numerical or result-schema risks map to Regression Risks Identified.
- Unreachable engine helpers map to Dead Code Identified.
- Golden execution checks map to Fix Validation Results.
