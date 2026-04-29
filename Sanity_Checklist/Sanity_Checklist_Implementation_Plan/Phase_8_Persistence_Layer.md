# Phase 8 - Persistence Layer Audit Plan

## 1. Phase Title

Persistence Layer: Filesystem Storage, Atomicity, Logs, Snapshots, Caches, Artifacts, and Recovery

## 2. Scope

This phase audits all dynamically discovered persistence mechanisms and storage contracts.

Runtime discovery must identify and audit:

- All file reads and writes.
- All JSON, CSV, log, cache, snapshot, strategy, result, task-store, status, metadata, and environment file persistence.
- All atomic write helpers and temp-file replacement logic.
- All directories created at runtime.
- All path validation boundaries.
- All cleanup, archival, corruption handling, and recovery behavior.
- All generated artifacts consumed by UI or execution.

Why this layer matters:

- Trading systems depend on durable, accurate, and recoverable state.
- Partial writes, stale files, or unsafe paths can corrupt workflows and diagnostics.

Dependencies with other layers:

- Receives artifacts from all phases.
- Feeds Phase 2 data, Phase 4 task recovery, Phase 5 strategies, Phase 7 UI, Phase 9 workflows.

## 3. Audit Objectives

Correctness means:

- Every persisted file has an owner, schema, writer, reader, lifecycle, and corruption policy.
- Critical writes are atomic.
- Readers tolerate partial/corrupt files safely.
- File paths cannot escape approved roots.
- Logs are current, interpretable, and not misleading.
- Generated artifacts are discoverable and cleanly separated from source.

Failure looks like:

- Corrupt JSON breaks startup.
- Partial CSV read causes false data.
- Old error log appears current.
- Temp files accumulate.
- Result artifacts missing after success.
- Strategy save loses code.
- Path traversal writes outside project.

Production-grade means:

- Atomicity for critical state.
- Clear schema/lifecycle for every artifact.
- Corruption quarantine.
- Safe directory creation.
- Retention and cleanup policy.
- No hidden persistence failures.

## 4. Deep Audit Checklist

### A. Bug Detection

- Inventory every runtime write path.
- Inventory every runtime read path.
- Map writer-to-reader contracts.
- Verify atomic writes for status, task store, snapshots, env updates, and critical metadata.
- Verify CSV concurrent writer/reader behavior.
- Verify corrupt JSON handling.
- Verify temp file cleanup.
- Verify log rotation or timestamp boundaries.
- Verify generated files are not imported as code.
- Verify path resolvers restrict user-controlled paths.
- Verify result artifacts are created on success and failure.
- Verify missing directories are created intentionally.
- Verify old caches are invalidated by schema changes.
- Verify status files include enough freshness metadata.

### B. Root Cause Analysis Template

- Issue: atomicity, corruption, path safety, stale artifact, log, cache, status, or lifecycle defect.
- Why it happens: direct write, missing schema, missing freshness, weak path validation, shared file without lock, stale generated file.
- Where it originates: writer, reader, resolver, cleanup, status panel, cache loader.
- When it triggers: crash during write, concurrent read, rerun, restart, old artifact, invalid input path.

### C. Fix Design Template

- Exact fix approach: atomic write, schema version, corruption quarantine, path boundary check, retention policy, log session markers.
- Alternatives: database, append-only logs, file locks, manifest registry.
- Tradeoffs: complexity, portability, performance, migration.

### D. Pre-Fix Validation

- Confirm which files are user data versus generated data.
- Confirm retention requirements.
- Confirm compatibility with existing artifacts.
- Confirm cross-platform path requirements.
- Confirm whether concurrent writers exist.

### E. Edge Cases

- Disk full.
- Permission denied.
- Partial JSON.
- Partial CSV line.
- Concurrent status write.
- Temp file remains.
- Log grows unbounded.
- Source file deleted during read.
- Path contains spaces or Unicode.
- Windows/Linux path conversion.

### F. Post-Fix Sanity Checks

- Force corrupt file and verify quarantine/recovery.
- Interrupt write in disposable environment.
- Run concurrent read while writer appends.
- Verify paths stay inside approved roots.
- Verify artifact generation and UI discovery.
- Verify stale logs are distinguishable.

### G. Dead Code Detection

- Identify unused storage directories.
- Identify obsolete cache formats.
- Identify unreferenced logs.
- Identify unused atomic helpers.
- Identify stale generated artifacts checked into source.

### H. Cleanup After Fix

- Define storage manifest.
- Remove obsolete artifacts after backup.
- Add retention policy.
- Centralize atomic JSON writes.
- Centralize safe path resolution.

## 5. Invariants & Contracts

- Every persisted artifact has schema and owner.
- Critical JSON writes are atomic.
- Corrupt persistence never crashes whole app without actionable message.
- User-controlled paths stay inside allowed roots.
- Status files include freshness.
- Result artifacts are immutable after creation.
- Generated data is separated from source.

## 6. Failure Injection Strategy

- Corrupt JSON files.
- Truncate CSV files.
- Make directory read-only.
- Leave temp file beside target.
- Inject path traversal strings.
- Delete artifact during UI read.
- Create stale status file.

Expected behavior:

- Failures are visible and recoverable.
- Unsafe paths are rejected.
- No corrupted artifact is treated as valid.

## 7. Observability Requirements

- Artifact path.
- Writer module.
- Write timestamp.
- Schema/version where applicable.
- Corruption handling action.
- Cache hit/miss/stale.
- Log session markers.
- Persistence error surfaced in terminal/UI.

## 8. Production Hardening Checklist

- Atomic writes.
- Corruption quarantine.
- Retention policy.
- Safe path validation.
- Size limits.
- File locks or tolerant readers where concurrent access exists.
- Backup before destructive cleanup.
- Clear generated/source separation.

## 9. Regression Protection Strategy

- Persistence contract tests.
- Corrupt file tests.
- Atomic write tests.
- Path traversal tests.
- Artifact lifecycle tests.
- Cache invalidation tests.
- Log freshness tests.

## 10. Exit Criteria

- All persisted artifacts are inventoried.
- Writer/reader contracts are mapped.
- Critical writes are atomic or risk-accepted.
- Corruption recovery is validated.
- No Critical or High persistence issues remain open.
- Result file `Phase_8_Persistence_Layer_Result.md` is complete with final verdict.

## Result File Mapping

Write findings to:

`Sanity_Checklist/Sanity_Checklist_Result/Phase_8_Persistence_Layer_Result.md`

Mapping rules:

- Storage contract defects map to Issue Log Table.
- Corruption/concurrency tests map to Edge Case Failures Observed.
- Artifact lifecycle risks map to Regression Risks Identified.
- Obsolete files/helpers map to Dead Code Identified.
- Recovery and atomicity checks map to Fix Validation Results.
