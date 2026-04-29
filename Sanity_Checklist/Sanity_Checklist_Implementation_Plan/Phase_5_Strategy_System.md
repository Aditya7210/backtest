# Phase 5 - Strategy System Audit Plan

## 1. Phase Title

Strategy System: Discovery, Editing, Validation, Safe Loading, Versioning, Runtime Contract, and Lifecycle Integrity

## 2. Scope

This phase audits all dynamically discovered modules responsible for user strategies and strategy lifecycle management.

Runtime discovery must identify and audit:

- Strategy source directories and all strategy files.
- Strategy selector, scanner, editor, saver, versioner, naming, display, and dirty-state logic.
- Strategy class discovery and validation.
- Dynamic import and module loading logic.
- Safety checks for strategy source code.
- Strategy metadata stored in UI state, task payloads, task stores, and subprocess rehydration.
- Strategy examples/templates and generated strategy files.

Why this layer matters:

- Strategies are user-authored executable code.
- A weak strategy lifecycle can run the wrong class, stale code, unsafe code, or unvalidated logic.

Dependencies with other layers:

- Depends on Phase 1 discovery and Phase 3 execution contract.
- Feeds Phase 4 task serialization.
- Feeds Phase 7 UI editing workflow.
- Feeds Phase 8 persistence for versioned files.

## 3. Audit Objectives

Correctness means:

- The UI lists the same strategy classes that execution can load.
- Saving and versioning never lose user code.
- Dirty-state indicators match actual file content.
- Dynamic loading uses validated paths and safe module names.
- Task execution always runs the selected strategy file/class pair.
- Strategy errors are surfaced clearly.

Failure looks like:

- UI displays a class that execution cannot load.
- Execution runs stale class after edit.
- Saving overwrites wrong file.
- Versioning creates invalid file or loses selection.
- Unsafe strategy source bypasses validation.
- Subprocess cannot rehydrate selected strategy.

Production-grade means:

- Explicit strategy source contract.
- Safe path boundaries.
- Deterministic class discovery.
- No stale editor-to-execution state.
- Recoverable save/version operations.
- Clear user-facing errors.

## 4. Deep Audit Checklist

### A. Bug Detection

- Discover all strategy roots dynamically.
- Verify scanner excludes generated caches and non-strategy files.
- Verify class discovery matches execution loader.
- Verify syntax errors are reported with file and line.
- Verify invalid classes are excluded or clearly reported.
- Verify dynamic import does not leak modules or use stale `sys.modules`.
- Verify path traversal protections.
- Verify strategy source safety checks cover disallowed dynamic execution.
- Verify editor state tracks selected file accurately.
- Verify dirty indicator matches file content.
- Verify save writes atomically or safely.
- Verify versioned save cannot overwrite base unintentionally.
- Verify task payload includes enough metadata to rehydrate strategy in subprocess.
- Verify renamed/deleted selected strategy is handled gracefully.
- Verify strategy templates produce valid classes.

### B. Root Cause Analysis Template

- Issue: discovery, edit, save, version, validation, loading, or runtime strategy contract defect.
- Why it happens: stale cache, weak path validation, dynamic import behavior, UI state drift, non-atomic write, mismatch between selector and loader.
- Where it originates: scanner, editor, saver, loader, versioner, execution task builder.
- When it triggers: file change, save, version save, selection change, execution, subprocess rehydration.

### C. Fix Design Template

- Exact fix approach: unify scanner/loader rules, strengthen path validation, add source hash binding, atomic save, cache invalidation, explicit syntax reporting.
- Alternatives: static registry, metadata sidecar, sandboxed strategy API, stricter class base type.
- Tradeoffs: flexibility versus safety, compatibility with existing strategies, editor responsiveness.

### D. Pre-Fix Validation

- Confirm expected strategy directory rules.
- Confirm strategy naming/class conventions.
- Confirm allowed imports and dynamic behavior.
- Confirm whether old strategies must remain executable.
- Confirm save/version UX requirements.

### E. Edge Cases

- Syntax error in selected strategy.
- File deleted after selection.
- Class renamed after selection.
- Multiple classes in one file.
- Duplicate class names in different files.
- Save interrupted.
- Versioning enabled with invalid display name.
- Strategy imports unavailable dependency.
- Strategy mutates global state.
- Strategy uses unsupported order API.

### F. Post-Fix Sanity Checks

- Create strategy, save, select, execute.
- Edit selected strategy and verify execution uses latest saved version.
- Version-save and execute version.
- Run invalid syntax strategy and verify clear error.
- Delete selected file and verify UI recovery.
- Subprocess rehydration test.

### G. Dead Code Detection

- Identify unused strategy scanning functions.
- Identify obsolete editor state keys.
- Identify unused versioning helpers.
- Identify duplicate class discovery logic.
- Identify abandoned templates.

### H. Cleanup After Fix

- Centralize strategy metadata schema.
- Document strategy API.
- Remove obsolete caches.
- Normalize version naming.

## 5. Invariants & Contracts

- Strategy path must resolve inside approved strategy root.
- Selected strategy is `(file, class, source identity)`.
- UI selection and task payload must agree.
- Strategy source must parse before execution.
- Dynamic execution primitives are rejected if policy forbids them.
- Save/version operations never silently lose code.
- Execution errors from strategy code include class name and stage.

## 6. Failure Injection Strategy

- Inject syntax error.
- Rename selected class.
- Delete selected file.
- Add disallowed call.
- Create duplicate class names.
- Interrupt save in disposable environment.
- Modify file between queue creation and subprocess execution.

Expected behavior:

- UI and terminal explain exact strategy issue.
- Execution does not run stale or unsafe strategy.
- User code remains recoverable.

## 7. Observability Requirements

- Strategy file selected.
- Strategy class selected.
- Source validation result.
- Save/version action result.
- Dirty-state reason.
- Loader errors with file and line.
- Subprocess rehydration failures.

## 8. Production Hardening Checklist

- Atomic strategy writes.
- Path traversal prevention.
- Source validation before task build.
- Class rehydration in child process.
- Cache invalidation on file change.
- Versioned backups.
- Clear terminal errors for strategy failures.

## 9. Regression Protection Strategy

- Strategy scanner/loader parity tests.
- Save/version lifecycle tests.
- Invalid source tests.
- Path safety tests.
- Subprocess rehydration tests.
- Golden template compilation tests.

## 10. Exit Criteria

- All strategy lifecycle modules are discovered.
- Scanner and loader contracts match.
- Save/version workflows are validated.
- Strategy runtime contract is documented.
- No Critical or High strategy system issues remain open.
- Result file `Phase_5_Strategy_System_Result.md` is complete with final verdict.

## Result File Mapping

Write findings to:

`Sanity_Checklist/Sanity_Checklist_Result/Phase_5_Strategy_System_Result.md`

Mapping rules:

- Lifecycle and safety defects map to Issue Log Table.
- Injected invalid strategy scenarios map to Edge Case Failures Observed.
- Stale strategy or editor risks map to Regression Risks Identified.
- Unused strategy helpers map to Dead Code Identified.
- Save/load/execution validation maps to Fix Validation Results.
