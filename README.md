# Matomo Analytics

Standalone Odoo 18 addon for storing Matomo analytics data inside Odoo.

This repository is the canonical source of truth for the `matomo_analytics`
product. The `addons-curq` monorepo is now an integration workspace only and
must not be treated as the baseline for product behavior, release history, or
documentation.

The validated prototype baseline is tagged as `v0.1.0`.

## Runtime

- Supported Odoo version: 18
- Local runtime: Docker + Docker Compose
- Default local URL: `http://localhost:8069`

## Quickstart

Clone the repository and enter it:

```bash
git clone git@github.com:MyCleaningSupplies/odoo_matomo_analytics.git
cd odoo_matomo_analytics
```

Create a local environment file:

```bash
cp .env.example .env
```

Start the local containers:

```bash
make up
```

Create the development database and install the addon:

```bash
make init
```

Update the addon after code changes:

```bash
make update
```

Run the automated addon tests:

```bash
make test
```

Validate the Docker Compose setup:

```bash
make config
```

## Expected First-Run Flow

1. Open `http://localhost:8069`
2. Log in as admin
3. Open `Matomo Analytics`
4. Create a connection from `Configuration -> Connections`
5. Run `Test Connection`
6. Run `Sync Now`
7. Open `Overview`
8. Review `Sync Logs`

## Day-to-Day Commands

- `make up`: start or restart the local stack
- `make init`: create the dev DB and install the addon
- `make update`: reload Python/XML changes into the dev DB
- `make test`: run addon tests in an isolated DB
- `make logs`: follow Odoo logs
- `make shell`: open a shell in the Odoo container
- `make down`: stop the stack
- `make clean`: stop the stack and remove volumes
- `make config`: render and validate the Compose configuration

## Documentation

- [docs/operations.md](docs/operations.md): local setup, validation, and runtime operations
- [docs/product-behavior.md](docs/product-behavior.md): product behavior and sync semantics
- [docs/known-limitations.md](docs/known-limitations.md): current prototype limits
- [docs/roadmap.md](docs/roadmap.md): next hardening work and integration policy

## Notes

- The addon is mounted into the container from the working tree, so local code edits are immediately available to Odoo.
- `make test` runs the addon's Odoo tests with `--workers=0` to avoid worker-mode test issues.
- A Postgres dependency container may remain running after `make test`; this is expected Compose behavior.
- Syncing against a real Matomo instance still requires valid Matomo credentials and network access from the Odoo container.
