# Phase 1 - Core Foundations Audit Plan

## 1. Phase Title

Core Foundations: Runtime Discovery, Repository Integrity, Dependency Surface, Configuration, and Global Contracts

## 2. Scope

This phase audits the foundation on which every later audit depends. The scope is built dynamically at runtime and must not rely on historical architecture notes.

Runtime discovery must identify and audit:

- All repository root configuration files discovered by filesystem scan: dependency manifests, Docker files, launcher scripts, environment templates, CI files, lint/test/type-check configuration, package metadata, `.gitattributes`, `.gitignore`, documentation that declares system architecture, and startup entrypoints.
- All Python packages and import roots discovered by scanning for `__init__.py`, executable scripts, Streamlit entrypoints, CLI entrypoints, and modules referenced by launchers or containers.
- All dependency imports discovered through AST parsing and import graph generation.
- All global constants, project-root resolvers, path resolvers, environment-variable loaders, timezone helpers, logging helpers, and process bootstrap code discovered through static search and import graph traversal.
- All safety primitives used across layers: atomic write helpers, path validation helpers, subprocess launch helpers, exception classifiers, and terminal/logging adapters.

Why this layer matters:

- Every later phase depends on accurate module discovery, import resolution, dependency health, environment correctness, path safety, and reproducible execution.
- If discovery is wrong, the audit framework will miss files, misclassify layers, or audit stale assumptions.

Dependencies with other layers:

- Feeds Phase 2 through Phase 10 with the current module inventory, import graph, runtime entrypoint list, dependency graph, and global contract registry.
- Does not validate business behavior yet; it establishes trustworthy discovery and foundational guarantees.

## 3. Audit Objectives

Correctness means:

- The audit runner can discover the current project structure without hardcoded file maps.
- All executable entrypoints are identified.
- All Python modules can be categorized by responsibility.
- All dependency sources are identified and internally consistent.
- All global path, environment, timezone, logging, and serialization contracts are catalogued.
- The repository can be started and inspected repeatably in the intended runtime environment.

Failure looks like:

- A module is omitted from discovery.
- Import graph generation fails silently.
- Startup commands differ between local, Docker, and documented launchers.
- Dependency manifests disagree with imported libraries.
- Environment variables are read from inconsistent sources.
- Global constants drift between modules.
- Foundational errors are only visible in external logs and not surfaced to users/developers.

Production-grade means:

- Deterministic discovery.
- Explicit environment contract.
- No hidden import failures.
- No unclassified entrypoints.
- No implicit reliance on current working directory.
- No ambiguous project root resolution.
- No stale docs treated as truth.

## 4. Deep Audit Checklist

### A. Bug Detection

- Build a complete file inventory using runtime filesystem scan.
- Build an import graph using AST imports, dynamic import patterns, subprocess module invocations, Streamlit imports, and launcher commands.
- Detect import cycles that cross logical layers.
- Detect modules imported by runtime but absent from dependency manifests.
- Detect dependencies in manifests that are no longer imported anywhere.
- Detect path resolution based on fragile current working directory assumptions.
- Detect environment variables read under multiple key names without a single contract.
- Detect startup paths that differ between local scripts, Docker, and UI controller subprocesses.
- Detect broad `except Exception` blocks in foundational modules that suppress bootstrap errors.
- Detect logs written only to files where user-facing terminal/status surfaces should also show failures.
- Detect files with line-ending or encoding risks that can affect cross-platform execution.
- Detect timezone helpers using naive local time.
- Detect global mutable state used before initialization.
- Detect unsafe path joins that can escape intended project roots.
- Detect stale generated files committed or mixed with source files.

### B. Root Cause Analysis Template

For each issue, record:

- Issue: the observable foundation-level defect.
- Why it happens: missing contract, inconsistent startup mode, implicit runtime assumption, stale dependency, unsafe path primitive, or suppressed exception.
- Where it originates: root file, module, import edge, launcher command, dependency manifest, or environment variable access.
- When it triggers: startup, import, subprocess launch, Docker restart, Streamlit rerun, path resolution, or dependency install.
- Blast radius: which later phases inherit the risk.

### C. Fix Design Template

For each issue, design:

- Exact fix approach: define the contract, centralize helper, update launch path, align dependency declaration, expose error, or add validation.
- Alternatives: minimal local fix, shared abstraction, explicit runtime assertion, CI guard.
- Tradeoffs: simplicity, coupling, migration effort, runtime overhead, operator visibility.
- Rollback plan: how to revert without losing observability.

### D. Pre-Fix Validation

- Confirm current entrypoints and launch modes.
- Confirm which modules are production code, generated code, tests, artifacts, or docs.
- Confirm dependency installation path used by real runtime.
- Confirm environment variable source precedence.
- Confirm Docker mount behavior and local execution behavior.
- Confirm whether changing root/path/env helpers affects all layers.

### E. Edge Cases

- Running from repo root versus package subdirectory.
- Running inside Docker versus host shell.
- Streamlit rerun after partial initialization.
- Missing `.env`.
- Duplicate environment variables with different names.
- Windows path separators and Linux container paths.
- UTF-8 BOM files.
- Circular imports that only fail under subprocess spawn.
- Generated files that shadow source modules.
- Dependency version drift.

### F. Post-Fix Sanity Checks

- Re-run dynamic discovery and compare inventory before/after.
- Import every discovered production module in isolated subprocess where safe.
- Run startup command in the same mode used by production.
- Verify dependency manifests match imports.
- Verify logs/errors appear in the intended user/developer surfaces.
- Verify no new import cycles or layer violations are introduced.

### G. Dead Code Detection

- Identify modules with no imports, no entrypoint reference, no dynamic reference, and no documented runtime role.
- Identify helper functions unused outside tests or obsolete modules.
- Identify duplicate root/path/env/time/log helpers.
- Identify dead launch scripts or old Docker commands.
- Identify configuration files not read by any runtime or tool.

### H. Cleanup After Fix

- Consolidate duplicate helpers only after tests confirm behavior.
- Remove stale docs or mark them historical.
- Remove obsolete launch commands.
- Remove unused dependencies after dependency graph verification.
- Normalize file encodings and line endings where appropriate.

## 5. Invariants & Contracts

- Every production file has a classified layer and owner role.
- Every executable entrypoint is discoverable.
- Every runtime module imports successfully in its intended environment.
- Every path resolver returns an absolute path inside an approved root unless explicitly documented.
- Environment variable names and precedence are centrally documented.
- Timezone policy is centrally documented.
- Logging policy states which errors must reach terminal, file logs, status JSON, or UI.
- Dependency manifests are sufficient to import all production modules.

## 6. Failure Injection Strategy

- Remove or rename `.env` in a disposable test copy.
- Run startup from a non-root current working directory.
- Run module startup using both file path and `python -m` where applicable.
- Temporarily corrupt a config file.
- Simulate missing dependency by running import checks in a minimal environment.
- Inject invalid project root into path resolver tests.
- Add a fake duplicate module name under generated/artifact folders and verify discovery classification.

Expected behavior:

- Failures are explicit, classified, and visible.
- No silent fallback to unsafe roots.
- Discovery result clearly marks unavailable dependencies and skipped files.

## 7. Observability Requirements

- Discovery inventory file.
- Import graph report.
- Entrypoint report.
- Dependency mismatch report.
- Environment contract report.
- Root/path safety report.
- All foundational errors must include file, line, command, current working directory, and environment source.

## 8. Production Hardening Checklist

- Startup validates critical dependencies before user workflows.
- Startup validates writable directories.
- Startup reports environment source and effective configuration.
- Entrypoints use module-safe invocation where packages are imported by package name.
- Global helpers fail loudly with actionable messages.
- No foundational initialization depends on Streamlit session state unless classified as UI-only.

## 9. Regression Protection Strategy

- Snapshot discovery inventory and import graph.
- Compare module count and layer classifications between audits.
- Enforce no unclassified production modules.
- Enforce no new dependency mismatch.
- Enforce no new broad exception suppression in foundational helpers.
- Enforce startup smoke test in intended runtime.

## 10. Exit Criteria

- All production files are discovered and classified.
- All entrypoints are identified.
- Import graph is generated without unhandled failures.
- Dependency manifests and imports are reconciled.
- Environment, path, logging, and timezone contracts are documented.
- No Critical or High foundation issues remain open.
- Result file `Phase_1_Core_Foundations_Result.md` is complete with final verdict.

## Result File Mapping

Write findings to:

`Sanity_Checklist/Sanity_Checklist_Result/Phase_1_Core_Foundations_Result.md`

Mapping rules:

- Bug Detection findings map to Issue Log Table.
- Root Cause Analysis maps to Root Cause column and issue detail notes.
- Fix Design maps to Fix Strategy column.
- Edge Cases map to Edge Case Failures Observed.
- Dead Code Detection maps to Dead Code Identified.
- Post-Fix Sanity Checks map to Fix Validation Results.
- Invariants, Observability, Hardening, and Regression gaps map to Issue Log Table with appropriate severity.
