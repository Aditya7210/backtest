# Phase 6 - API Layer Audit Plan

## 1. Phase Title

API Layer: Broker Authentication, REST Data Access, WebSocket Collection, Rate Limits, Token Lifecycle, and External Failure Handling

## 2. Scope

This phase audits all dynamically discovered modules that communicate with external APIs, broker SDKs, websocket services, authentication providers, or live market collection processes.

Runtime discovery must identify and audit:

- All imports of broker SDKs, websocket clients, HTTP clients, dotenv/env loaders, and credential consumers.
- All authentication/token generation, token persistence, token validation, and token refresh flows.
- All API data fetchers, quote fetchers, instrument mappers, instrument updaters, collectors, and live data subprocess entrypoints.
- All websocket subscription logic, reconnect logic, status file writes, process controllers, and rate-limit handling.
- All API error classifiers and user/developer observability surfaces.

Why this layer matters:

- External API failures are common and must not corrupt backtests or live data.
- Token staleness, subscription limits, rate limits, and reconnect behavior directly affect data availability.

Dependencies with other layers:

- Depends on Phase 1 environment contract.
- Feeds Phase 2 data layer.
- Feeds Phase 7 UI status and terminal.
- Feeds Phase 9 live/API workflows.

## 3. Audit Objectives

Correctness means:

- Credentials are loaded from a single documented precedence order.
- Token refresh is visible and effective without stale runtime state.
- API calls use valid request parameters.
- WebSocket subscription universe is bounded and explainable.
- External failures surface actionable messages.
- Status files reflect real health, not only process existence.

Failure looks like:

- New token written but old token used.
- API errors swallowed and replaced with generic failures.
- WebSocket process alive but not receiving ticks.
- Subscription exceeds broker limits.
- Rate-limit failures create partial or stale data without warning.
- Instrument metadata stale or incompatible.

Production-grade means:

- Explicit credential lifecycle.
- Bounded external calls.
- Retry/backoff for transient failures.
- No silent degraded mode.
- Real health checks.
- Clear distinction between process alive, API connected, and data flowing.

## 4. Deep Audit Checklist

### A. Bug Detection

- Discover all credential reads and writes.
- Verify token date/time policy.
- Verify `.env`, process env, Streamlit state, and status files do not conflict.
- Verify token refresh updates all runtime consumers or consumers reread source of truth.
- Verify API request parameters are validated before call.
- Verify API cache fallback is explicitly logged.
- Verify instrument mapper update behavior and metadata freshness.
- Verify quote batching respects broker limits.
- Verify websocket subscription count is below configured hard limit.
- Verify websocket mode selection matches instrument type.
- Verify reconnect events update status.
- Verify `last_tick_at`, `last_error`, and `bars_written` are reliable health signals.
- Verify process controllers launch modules safely.
- Verify old logs do not masquerade as current failures.
- Verify all API exceptions are classified and visible.

### B. Root Cause Analysis Template

- Issue: auth, token, REST API, websocket, rate limit, instrument metadata, process health, or observability defect.
- Why it happens: stale env, invalid precedence, missing retry, subscription oversize, weak health check, stale status, swallowed SDK exception.
- Where it originates: auth page, credential loader, API fetcher, collector, controller, mapper, status reader.
- When it triggers: login, date rollover, container restart, market open, reconnect, rate limit, missing instruments, API outage.

### C. Fix Design Template

- Exact fix approach: central credential source, token invalidation, bounded subscriptions, retry/backoff, status health contract, error surfacing.
- Alternatives: per-process reload, token service, supervisor, persistent health monitor.
- Tradeoffs: complexity, latency, API usage, operational clarity.

### D. Pre-Fix Validation

- Confirm broker documented limits.
- Confirm current credential sources and runtime environment.
- Confirm token validity window.
- Confirm supported exchanges/instruments.
- Confirm acceptable fallback behavior when API unavailable.

### E. Edge Cases

- Expired token.
- Fresh token but stale process env.
- Invalid API secret.
- Request token reused.
- API rate limit.
- Network outage.
- Broker returns partial data.
- Market closed.
- Non-trading day.
- Instrument token missing.
- WebSocket connects but no ticks.
- Subscription count above limit.
- Collector subprocess dies immediately.
- Status file stale.

### F. Post-Fix Sanity Checks

- Login without container restart.
- Fetch API historical data.
- Start collector and verify tick flow.
- Force invalid token and verify error.
- Force oversized subscription and verify pre-connect rejection.
- Simulate stale status and verify health false.
- Verify all failures appear in UI/terminal/status.

### G. Dead Code Detection

- Identify obsolete auth helpers.
- Identify unused instrument update scripts.
- Identify duplicate credential loaders.
- Identify abandoned collector entrypoints.
- Identify unreachable API fallback logic.

### H. Cleanup After Fix

- Centralize credential access.
- Document broker limits and subscription policy.
- Rotate stale logs or add timestamped log sessions.
- Remove old direct-script launch paths.

## 5. Invariants & Contracts

- One effective credential source of truth.
- Token freshness is validated before API use.
- WebSocket health requires process alive, status running, recent update, no active error, and tick or explicit waiting state.
- Subscription count never exceeds configured broker limit.
- API failures never produce silent success.
- Instrument metadata freshness is known.

## 6. Failure Injection Strategy

- Replace token with invalid value in disposable environment.
- Set stale process env token while `.env` is fresh.
- Request too many websocket tokens.
- Block network/API endpoint.
- Corrupt status JSON.
- Kill collector subprocess.
- Simulate broker rate-limit exception.

Expected behavior:

- Errors are specific and actionable.
- Health status becomes unhealthy.
- No stale data is treated as fresh.
- No restart is required unless documented.

## 7. Observability Requirements

- Effective credential source without leaking secrets.
- Token date/freshness.
- API request identity: source, symbol/token, interval, date range.
- Retry attempts.
- Rate-limit events.
- WebSocket connection/reconnect/close.
- Subscription count and categories.
- Tick freshness and bars written.
- Last error with current timestamp.

## 8. Production Hardening Checklist

- Secret redaction.
- Token lifecycle tests.
- Retry/backoff.
- Rate-limit-aware batching.
- Subscription guard.
- Process health separate from data health.
- Crash recovery.
- Stale status detection.
- Network failure handling.

## 9. Regression Protection Strategy

- Credential precedence tests.
- Token refresh tests.
- API failure classification tests.
- WebSocket subscription-limit tests.
- Status health tests.
- Instrument metadata freshness tests.
- Collector launch tests.

## 10. Exit Criteria

- All API-facing modules are discovered.
- Credential and token contracts are documented.
- API and websocket failure modes are tested.
- Health signals are reliable.
- No Critical or High API layer issues remain open.
- Result file `Phase_6_API_Layer_Result.md` is complete with final verdict.

## Result File Mapping

Write findings to:

`Sanity_Checklist/Sanity_Checklist_Result/Phase_6_API_Layer_Result.md`

Mapping rules:

- Auth/API/websocket defects map to Issue Log Table.
- Injected token/network/subscription failures map to Edge Case Failures Observed.
- Stale token/status/data risks map to Regression Risks Identified.
- Obsolete API scripts map to Dead Code Identified.
- Credential and collector validation maps to Fix Validation Results.
