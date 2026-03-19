# Known Limitations

## Goal Import Variability

Goal import behavior varies across Matomo instances.

Current expected behavior:

- goal import is best-effort
- traffic/content import should continue even if goal endpoints are unavailable
- goal-related failures should degrade to warnings and partial sync where possible

## Matomo API Payload Variability

Different Matomo environments may return:

- missing report sections
- empty report payloads
- different goal payload shapes
- per-report errors inside bulk responses

The addon already tolerates part of this variability, but not all real-world
shapes have been hardened yet.

## Warning Visibility

Warnings are stored clearly in sync logs, but they may still be more visible in
the logs UI than in the primary dashboard or connection views.

This is a current UX limitation, not a data-loss issue.

## Monorepo Integration Is Not Canonical

The `addons-curq` monorepo is an integration workspace only.

It must not be used as the primary product baseline because:

- it is intentionally dirty
- it contains repaired historical state
- it now embeds this addon as a nested repo rather than as the canonical source

## Packaging / Distribution

The addon is now portable and runnable as a standalone repo, but full release
packaging and distribution policy is still minimal.

At this stage, the repo should be treated as a validated, shippable prototype
baseline rather than a finalized packaged product line.
