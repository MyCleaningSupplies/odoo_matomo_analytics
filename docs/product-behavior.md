# Product Behavior

## Connection Setup

Users create a Matomo connection from `Configuration -> Connections`.

Required configuration:

- name
- base URL
- site ID
- API token
- sync window days
- page limit

The addon validates that:

- the Matomo base URL includes scheme and host
- the site ID is positive
- sync window days is greater than zero
- page limit is greater than zero

## `Test Connection`

`Test Connection` calls Matomo and verifies that:

- the server responds with a valid Matomo version
- the configured site exists

If successful:

- the connection is marked as tested
- the UI shows a success notification

## `Sync Now`

`Sync Now` creates a sync log and imports analytics day by day across the
configured sync window.

Imported report families:

- daily summary
- traffic channels
- countries
- referrers
- page metrics
- goal metrics

## Cron Sync

The addon provides a scheduled sync entrypoint that runs the same sync pipeline
for active Matomo instances.

The cron behavior should be treated as functionally equivalent to manual sync,
except for the trigger source and user-facing notification behavior.

## Re-Sync Semantics

Re-sync is deterministic at the day level.

For each imported day, the addon:

1. fetches report payloads from Matomo
2. deletes existing stored facts for that instance and day
3. recreates normalized facts from the fetched payload

This keeps repeated syncs predictable and makes repair/reimport behavior easier
to reason about.

## Sync Outcomes

The addon treats sync outcomes as:

- `success`: all expected report families imported without warnings
- `partial`: at least some days imported, but one or more report families were unavailable or degraded
- `failed`: no useful day import completed or the run failed unrecoverably

## Partial Sync Definition

A partial sync means:

- traffic/content imports may have completed
- one or more report families may be missing, empty, malformed, or unavailable
- warnings are recorded in the sync log

Example:

- goal reporting is unavailable for a specific Matomo instance, but traffic and content still import

## Hard Failure Definition

A hard failure means:

- zero imported days, or
- a fatal error prevents a usable sync result

The log state is `failed`, not `partial`.

## Dashboard and Reporting

The dashboard and report actions operate on stored analytics records, not live
Matomo API calls.

Expected behavior:

- overview metrics aggregate stored daily facts
- report actions open filtered stored analytics views
- date ranges scope the displayed records
- comparison periods operate against stored data

## Bounce Rate Aggregation

Dashboard bounce rate is session-weighted across the selected daily records.

It is not a simple arithmetic average of daily bounce rates.

This is intentional and should be treated as locked product behavior.
