# Phase 9 - End-to-End Workflow Validation Audit Plan

## 1. Phase Title

End-to-End Workflow Validation: Operator Journeys, Cross-Layer Contracts, Data-to-Result Traceability, and Regression Gates

## 2. Scope

This phase audits complete user workflows across all discovered layers. It does not replace earlier layer audits; it validates that the full system works as an integrated product.

Runtime discovery must identify and audit:

- All UI workflows that lead to execution.
- All supported data-source workflows discovered in earlier phases.
- All strategy creation/selection/execution workflows.
- All API authentication-to-execution workflows.
- All live collector-to-backtest workflows.
- All result display, artifact, and terminal workflows.
- All startup/shutdown/restart workflows.

Why this layer matters:

- Most production defects occur at integration boundaries.
- A layer can pass alone and fail when combined with UI state, persistence, API state, and execution orchestration.

Dependencies with other layers:

- Requires Phase 1 through Phase 8 outputs.
- Produces cross-layer regression evidence.
- Feeds Phase 10 production hardening.

## 3. Audit Objectives

Correctness means:

- Every supported operator journey can be run from a fresh start to a validated result.
- Every artifact generated during the workflow is traceable.
- Every failure scenario has a clear terminal/UI explanation.
- Data identity, strategy identity, execution identity, and result identity are consistent across the journey.
- Restart/rerun does not corrupt workflow state.

Failure looks like:

- UI allows invalid workflow to reach execution.
- Result cannot be traced to data and strategy.
- Terminal omits root cause.
- Collector produces data but backtest cannot consume it.
- Auth succeeds but execution uses stale token.
- Strategy save succeeds but execution uses old code.
- Artifacts missing or stale.

Production-grade means:

- Repeatable journey scripts.
- Cross-layer trace IDs or equivalent.
- Deterministic validation artifacts.
- Clear pass/fail gates.
- No hidden manual steps.

## 4. Deep Audit Checklist

### A. Bug Detection

- Define all discovered workflows dynamically from UI controls and execution modes.
- Validate CSV workflow from file selection to result artifact.
- Validate API workflow from auth/session to fetched data to result artifact.
- Validate Live Market workflow from collector status to selected instrument to extracted CSV to result artifact.
- Validate VIX workflow if VIX is supported.
- Validate strategy creation, save, select, execute.
- Validate strategy versioning if enabled.
- Validate invalid workflow handling: missing data, missing strategy, stale token, missing timeframe, stale collector, corrupt file.
- Validate terminal contains a full chronological narrative.
- Validate result displayed in UI matches persisted artifact.
- Validate task store result matches UI result.
- Validate data row counts are traceable from source to execution.
- Validate restart/reload behavior before and after execution.

### B. Root Cause Analysis Template

- Issue: cross-layer workflow defect.
- Why it happens: contract mismatch, stale state, wrong artifact, missing validation, inconsistent identity, incomplete error propagation.
- Where it originates: source layer and receiving layer boundary.
- When it triggers: specific operator journey step.
- Cross-layer dependency: data, strategy, execution, persistence, API, UI.

### C. Fix Design Template

- Exact fix approach: align boundary contract, add workflow validation, add traceability, update readiness predicate, expose terminal diagnostics.
- Alternatives: orchestration service, workflow manifest, integration test harness, explicit workflow state machine.
- Tradeoffs: implementation effort, user friction, runtime cost, maintenance.

### D. Pre-Fix Validation

- Confirm workflow is officially supported.
- Confirm required test data and credentials can be safely used.
- Confirm expected result criteria.
- Confirm whether failure is layer-specific or boundary-specific.
- Confirm artifact retention for comparison.

### E. Edge Cases

- Fresh install with no data.
- Existing stale data.
- Token expired mid-workflow.
- Collector running but no ticks.
- Calculator missing higher timeframe.
- User changes strategy after selecting data.
- User changes data after selecting strategy.
- Browser refresh during execution.
- Docker/container restart between steps.
- Multiple workflows run sequentially.
- Multiple workflows run concurrently if supported.

### F. Post-Fix Sanity Checks

- Replay failing workflow.
- Replay all adjacent workflows.
- Verify artifacts and terminal logs.
- Verify state reset between workflows.
- Verify no regression in prior phase checks.

### G. Dead Code Detection

- Identify UI workflows that no longer lead to any execution path.
- Identify execution modes no longer reachable from UI.
- Identify data source selectors that cannot produce valid tasks.
- Identify result panels not fed by current result schema.

### H. Cleanup After Fix

- Document supported workflows.
- Remove obsolete modes or mark disabled.
- Add workflow-level smoke tests.
- Consolidate traceability fields.

## 5. Invariants & Contracts

- Every execution result is traceable to selected data, strategy file, strategy class, config, task ID, and timestamp.
- Every supported workflow has a documented success criterion.
- Every failed workflow identifies the failing layer.
- UI state and persisted task state agree after workflow completion.
- Restart does not convert failed/unknown workflow state into success.

## 6. Failure Injection Strategy

- Execute with missing strategy.
- Execute with missing data.
- Execute with stale token.
- Execute Live Market with missing timeframe.
- Kill collector mid-workflow.
- Corrupt selected CSV.
- Refresh UI during execution.
- Restart app after queue creation.

Expected behavior:

- Workflow fails at earliest valid gate.
- Terminal identifies exact failing step.
- No partial result is shown as success.
- State remains recoverable.

## 7. Observability Requirements

- Workflow name.
- Data identity.
- Strategy identity.
- Task ID.
- Config.
- Source row count.
- Execution row count.
- Result artifact path.
- Failure stage.
- Terminal narrative.

## 8. Production Hardening Checklist

- Workflow smoke suite.
- Boundary contract assertions.
- Traceability in result artifacts.
- Clear failure gates.
- No hidden prerequisites.
- Restart-safe state.
- Operator instructions embedded in error messages where appropriate.

## 9. Regression Protection Strategy

- Golden end-to-end workflows.
- Workflow matrix by data source and strategy type.
- Artifact comparison.
- Terminal narrative checks.
- Restart/rerun checks.
- Cross-layer contract diff.

## 10. Exit Criteria

- All supported workflows are discovered and classified.
- Every workflow has pass/fail evidence.
- Every failed workflow has layer-attributed root cause.
- No Critical or High cross-layer issues remain open.
- Result file `Phase_9_End_To_End_Workflow_Validation_Result.md` is complete with final verdict.

## Result File Mapping

Write findings to:

`Sanity_Checklist/Sanity_Checklist_Result/Phase_9_End_To_End_Workflow_Validation_Result.md`

Mapping rules:

- Workflow failures map to Issue Log Table.
- Injected journey failures map to Edge Case Failures Observed.
- Boundary contract risks map to Regression Risks Identified.
- Unreachable workflows map to Dead Code Identified.
- End-to-end replay checks map to Fix Validation Results.
