# Roadmap

## Current Baseline

The validated prototype baseline is tagged as:

- `v0.1.0`

This tag represents:

- standalone repo is canonical
- portable Docker-based local setup exists
- automated addon test flow exists
- clean Odoo 18 validation has been proven
- sync logging and partial-success semantics exist
- dashboard bounce rate is session-weighted

## Next Engineering Work

Continue work in this order.

### 1. Sync Observability

Goal:

- make sync outcomes understandable without opening raw logs first

Target changes:

- surface last sync state more prominently on the connection form
- surface warning count and short warning summary on the connection/dashboard
- add a direct path to the most recent sync log

### 2. Goal Import Robustness

Goal:

- tolerate more Matomo goal-report variability without harming non-goal imports

Target changes:

- expand supported goal payload shapes where new real-world variants are found
- strengthen tests for empty, malformed, and summary-only goal cases

### 3. Report UX Polish

Goal:

- make dashboard and reporting views easier to trust

Target changes:

- show partial-sync context more clearly
- improve wording and report framing
- keep report filters and date scoping intuitive

### 4. API Variability and Re-Sync Test Hardening

Goal:

- cover real instability points in automated tests

Target changes:

- bulk-response variability tests
- per-report error tests
- malformed payload tests
- deterministic re-sync tests
- weighted bounce-rate regression tests

## Monorepo Integration Policy

Treat `addons-curq` as downstream integration only.

Rules:

- do not develop new product behavior there first
- do not use repaired monorepo database state as proof of correctness
- implement product changes in the standalone repo first
- validate CURQ integration afterwards

## Release Direction

Short term:

- continue feature and hardening work on standalone `main`
- use tags for prototype and release baselines

Do not create a maintenance branch until there is a real need to support
parallel release lines.
