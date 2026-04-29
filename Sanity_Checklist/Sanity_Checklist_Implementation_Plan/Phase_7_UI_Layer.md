# Phase 7 - UI Layer Audit Plan

## 1. Phase Title

UI Layer: Streamlit Workflow, Session State, User Controls, Terminal Observability, and Error Surfacing

## 2. Scope

This phase audits all dynamically discovered UI modules, Streamlit pages, widgets, navigation, session-state contracts, visual status panels, and terminal/log display surfaces.

Runtime discovery must identify and audit:

- All modules importing Streamlit or UI component libraries.
- All page render functions and navigation entrypoints.
- All widgets and their session-state keys.
- All data source selectors, strategy selectors, execution controls, terminal panels, status cards, and result displays.
- All `st.error`, `st.warning`, `st.info`, `st.toast`, and terminal logging paths.
- All UI-triggered subprocess or execution actions.

Why this layer matters:

- The UI is the operator control surface.
- A production UI must prevent invalid actions and explain every failure.

Dependencies with other layers:

- Depends on Phase 2 through Phase 6 contracts.
- Displays Phase 4 execution state.
- Displays Phase 8 persisted artifacts.
- Used in Phase 9 end-to-end validation.

## 3. Audit Objectives

Correctness means:

- UI controls reflect actual system state.
- Invalid actions are disabled or fail with clear terminal messages.
- Session state is initialized, synchronized, and never contradictory.
- Terminal receives all execution-relevant errors.
- UI does not hide backend failures.
- Status panels distinguish idle, waiting, running, stale, failed, and healthy.

Failure looks like:

- Button enabled when required data is missing.
- Status says healthy while process is broken.
- Error appears only in browser toast or only in file log.
- Streamlit rerun resets critical state unexpectedly.
- Multiple session-state keys disagree.
- User can execute wrong data/strategy combination.

Production-grade means:

- Operator-safe controls.
- Self-explanatory errors.
- Deterministic session state.
- Clear progress and health.
- No reliance on hidden logs for normal diagnosis.

## 4. Deep Audit Checklist

### A. Bug Detection

- Discover every Streamlit state key and producer/consumer.
- Detect duplicate keys with different meanings.
- Verify default state initialization before use.
- Verify mode changes clear incompatible selections.
- Verify UI readiness conditions match backend validation.
- Verify data source selector cannot create impossible state.
- Verify strategy selection cannot execute missing class/file.
- Verify Live Market selector handles missing timeframes.
- Verify terminal logs every pre-execution and execution failure.
- Verify result display handles missing fields.
- Verify status panels use real health, not only PID or stale files.
- Verify auto-refresh does not trigger infinite rerun loops.
- Verify long-running operations do not block UI without status.
- Verify dangerous actions have clear feedback.

### B. Root Cause Analysis Template

- Issue: session-state, control readiness, status display, terminal visibility, navigation, or rerun defect.
- Why it happens: state drift, duplicated key, stale derived state, backend/UI contract mismatch, swallowed exception, missing health field.
- Where it originates: render function, widget callback, state sync, status reader, execution action.
- When it triggers: rerun, mode switch, selection change, execution click, collector start/stop, failure response.

### C. Fix Design Template

- Exact fix approach: state contract update, readiness predicate alignment, terminal logging, status model refinement, widget key cleanup.
- Alternatives: centralized state model, reducer pattern, page-level validation object, UI health service.
- Tradeoffs: simplicity, backwards compatibility, UI responsiveness.

### D. Pre-Fix Validation

- Inventory state keys.
- Confirm all user workflows.
- Confirm which errors must appear in terminal versus UI banner.
- Confirm status health definitions from backend phases.
- Confirm disabled/enabled conditions for buttons.

### E. Edge Cases

- Streamlit rerun during execution.
- User switches data mode mid-run.
- User changes strategy after queue built.
- Missing selected file.
- Missing selected data.
- Collector running but stale.
- Calculator absent.
- Empty result.
- Corrupt status JSON.
- Multiple browser sessions.
- Manual browser refresh.

### F. Post-Fix Sanity Checks

- Navigate every page.
- Switch every data mode.
- Run invalid execution attempts.
- Run valid execution attempts.
- Start/stop background processes.
- Confirm terminal contains actionable logs.
- Confirm no unhandled Streamlit exception.

### G. Dead Code Detection

- Identify unused UI components.
- Identify obsolete session-state keys.
- Identify callbacks no longer referenced.
- Identify old status panels hidden by navigation.
- Identify duplicate render helpers.

### H. Cleanup After Fix

- Document session-state contract.
- Centralize readiness checks.
- Remove obsolete keys.
- Consolidate terminal/error helpers.

## 5. Invariants & Contracts

- Every widget key has one meaning.
- Every execution button readiness condition matches backend validation.
- Every backend failure visible to user also appears in developer/operator logs.
- Session state cannot represent multiple active data modes simultaneously.
- Terminal persists enough context for the latest execution attempt.
- UI status health uses freshness and error fields where available.

## 6. Failure Injection Strategy

- Delete selected data file before execution.
- Delete selected strategy before execution.
- Corrupt status JSON.
- Force backend validation failure.
- Simulate stale collector status.
- Switch modes repeatedly.
- Open multiple sessions.

Expected behavior:

- UI prevents or explains failure.
- Terminal records exact cause.
- No inconsistent state persists after rerun.

## 7. Observability Requirements

- Current data mode.
- Selected data identity.
- Selected strategy identity.
- Execution readiness reason.
- Background process health reason.
- Terminal entries for all execution decisions.
- User-visible result and developer-visible diagnostic detail.

## 8. Production Hardening Checklist

- Readiness predicates are centralized or audited.
- State sync runs before controls.
- Errors include next action.
- Status panels show stale/failed distinctly.
- Terminal downloadable logs.
- Auto-refresh bounded.
- UI does not require hidden console access for diagnosis.

## 9. Regression Protection Strategy

- UI state contract tests where feasible.
- Streamlit smoke screenshots or scripted checks.
- Widget key inventory diff.
- Readiness predicate tests.
- Terminal logging tests.
- Status panel health tests.

## 10. Exit Criteria

- All UI modules and state keys are discovered.
- All user workflows have readiness validation.
- Terminal receives all relevant failures.
- No Critical or High UI issues remain open.
- Result file `Phase_7_UI_Layer_Result.md` is complete with final verdict.

## Result File Mapping

Write findings to:

`Sanity_Checklist/Sanity_Checklist_Result/Phase_7_UI_Layer_Result.md`

Mapping rules:

- State/control/status defects map to Issue Log Table.
- Rerun/mode-switch failures map to Edge Case Failures Observed.
- UI workflow risks map to Regression Risks Identified.
- Unused UI/state code maps to Dead Code Identified.
- Manual/scripted UI checks map to Fix Validation Results.
