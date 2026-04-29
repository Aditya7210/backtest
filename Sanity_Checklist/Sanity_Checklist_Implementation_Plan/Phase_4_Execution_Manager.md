# Phase 4 - Execution Manager Audit Plan

## 1. Phase Title

Execution Manager: Queues, Workers, Subprocess Isolation, Timeouts, Retries, State Machine, and Terminal Propagation

## 2. Scope

This phase audits orchestration around the execution core. Scope is discovered dynamically from modules that manage tasks, workers, queues, subprocesses, status, retries, terminal bridging, and execution persistence.

Runtime discovery must identify and audit:

- All manager classes or functions that accept tasks and dispatch engine execution.
- All queues, worker threads, subprocess launchers, multiprocessing contexts, timeout enforcement, retry loops, and task stores.
- All execution status state machines.
- All terminal/log propagation across process boundaries.
- All serialization/deserialization of tasks, strategy metadata, paths, classes, results, and errors.
- All cleanup, cancellation, crash recovery, and resume logic.

Why this layer matters:

- The execution core can be correct but still fail operationally through lost logs, duplicate task execution, stale status, dead workers, orphan subprocesses, or corrupted stores.

Dependencies with other layers:

- Depends on Phase 3 result contract.
- Feeds Phase 7 UI terminal and progress state.
- Feeds Phase 8 Persistence with task store behavior.
- Used by Phase 9 end-to-end workflows.

## 3. Audit Objectives

Correctness means:

- Every queued task transitions through a valid state sequence.
- No task is lost, duplicated, or left permanently running without detection.
- Timeouts terminate runaway work safely.
- Retries happen only for retryable failures.
- Subprocess failures surface full diagnostic context.
- Task store recovery is deterministic.

Failure looks like:

- Stale running status.
- Worker dies silently.
- Terminal misses subprocess logs.
- Retry loop hides root cause.
- Corrupt task store breaks future runs.
- Duplicate execution after rerun/reload.
- Timeout kills work but leaves bad state.

Production-grade means:

- Explicit state machine.
- Bounded concurrency.
- Recoverable task store.
- Observable worker lifecycle.
- No hidden exceptions.
- Deterministic cancellation and timeout behavior.

## 4. Deep Audit Checklist

### A. Bug Detection

- Discover every task state and valid transition.
- Verify no transition bypasses persistence.
- Verify queue operations are lock-protected where concurrency exists.
- Verify workers cannot pick the same pending task.
- Verify worker crashes are logged and surfaced.
- Verify hard timeouts terminate subprocesses and record failure.
- Verify subprocess logs are replayed to terminal.
- Verify retry count is accurate.
- Verify non-retryable failures do not retry.
- Verify retryable failures preserve original root cause.
- Verify task serialization excludes unsafe/unpickleable objects and rehydrates safely.
- Verify strategy metadata survives subprocess boundary.
- Verify task store load handles corrupt/partial JSON.
- Verify old RUNNING tasks are recovered safely on startup.
- Verify cancellation stops worker and child process.
- Verify progress is calculated from task states.

### B. Root Cause Analysis Template

- Issue: queue, worker, subprocess, retry, timeout, store, state, or observability defect.
- Why it happens: race, missing lock, bad serialization, missing state transition, swallowed exception, stale process, or corrupt store.
- Where it originates: manager method, worker loop, subprocess target, store serializer, UI tick integration.
- When it triggers: start, rerun, retry, timeout, crash, reload, cancel, result collection.

### C. Fix Design Template

- Exact fix approach: state transition guard, lock adjustment, subprocess payload extension, retry classification update, store recovery rule, terminal propagation.
- Alternatives: synchronous execution path, process pool, durable queue, explicit state machine library.
- Tradeoffs: latency, complexity, debuggability, crash safety.

### D. Pre-Fix Validation

- Confirm current concurrency model.
- Confirm maximum worker count.
- Confirm expected timeout semantics.
- Confirm retry policy by error type.
- Confirm UI state assumptions.
- Confirm task persistence requirements.

### E. Edge Cases

- Empty queue.
- Multiple workers.
- Worker process crashes without payload.
- Subprocess returns invalid payload.
- Timeout exactly at result completion.
- Retry succeeds after first failure.
- Retry limit zero.
- Store JSON corrupted.
- Streamlit rerun while tasks running.
- User starts second execution.
- Task contains dynamic class object.
- Strategy file changed between queue and execution.

### F. Post-Fix Sanity Checks

- Run single success task.
- Run multiple tasks with concurrent workers.
- Run forced validation failure.
- Run forced timeout.
- Run forced subprocess crash.
- Restart UI while tasks exist.
- Corrupt task store in disposable copy.
- Verify terminal has lifecycle logs.

### G. Dead Code Detection

- Identify unused manager methods.
- Identify old single-worker paths no longer called.
- Identify duplicate retry logic.
- Identify obsolete serialization branches.
- Identify unused performance tracking hooks.

### H. Cleanup After Fix

- Document state machine.
- Centralize retry classification.
- Separate durable persistence from in-memory queue logic.
- Remove unreachable compatibility methods only after call graph confirmation.

## 5. Invariants & Contracts

- A task state is one of `PENDING`, `RUNNING`, `SUCCESS`, `FAILED`.
- A task cannot be executed by two workers simultaneously.
- Every completed task has a result object.
- Every failed task has error type, stage, and message.
- Retry count never exceeds configured limit.
- Timeout always yields failed result and terminal log.
- Store load never leaves stale `RUNNING` without recovery action.

## 6. Failure Injection Strategy

- Force subprocess crash.
- Force worker exception.
- Force timeout with sleeping strategy.
- Force invalid subprocess payload.
- Corrupt task store.
- Kill parent or child process mid-task in a disposable environment.
- Start duplicate execution request.

Expected behavior:

- State remains recoverable.
- No hidden worker death.
- Terminal explains what happened.
- Store remains parseable or is quarantined.

## 7. Observability Requirements

- Task queued, started, retried, succeeded, failed.
- Worker start/stop.
- Subprocess PID when available.
- Timeout event.
- Retry decision and reason.
- Store load/recovery events.
- Terminal replay from subprocess.
- Performance metrics per task.

## 8. Production Hardening Checklist

- Bounded worker count.
- Hard timeout.
- Graceful child termination.
- Retry only classified transient failures.
- Atomic task store writes.
- Corrupt store quarantine.
- Resume behavior documented.
- Cancellation path tested.

## 9. Regression Protection Strategy

- State transition tests.
- Concurrency tests.
- Timeout tests.
- Retry tests.
- Store recovery tests.
- Terminal propagation tests.
- Serialization/rehydration tests.

## 10. Exit Criteria

- All orchestration modules are discovered.
- State machine is documented and verified.
- Timeout/retry/subprocess behavior is validated.
- No Critical or High manager issues remain open.
- Result file `Phase_4_Execution_Manager_Result.md` is complete with final verdict.

## Result File Mapping

Write findings to:

`Sanity_Checklist/Sanity_Checklist_Result/Phase_4_Execution_Manager_Result.md`

Mapping rules:

- Queue/state defects map to Issue Log Table.
- Injected crash/timeout/retry tests map to Edge Case Failures Observed.
- Store/concurrency risks map to Regression Risks Identified.
- Unused orchestration paths map to Dead Code Identified.
- Worker and subprocess validation maps to Fix Validation Results.
