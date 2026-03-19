# Operations

## Purpose

This document defines the standalone local development and validation flow for
the `matomo_analytics` addon. This repository is the canonical product repo.

## Local Development

### 1. Prepare the environment

```bash
cp .env.example .env
```

Review `.env` if you want to change local ports or database names.

### 2. Start local services

```bash
make up
```

This starts:

- `db`: PostgreSQL
- `odoo`: Odoo 18

### 3. Initialize the development database

```bash
make init
```

This creates the local development database and installs `base` plus
`matomo_analytics`.

### 4. Open Odoo

Open:

```text
http://localhost:8069
```

## Updating After Code Changes

Reload addon changes into the development database:

```bash
make update
```

Use this after Python, XML, security, or menu/view changes.

## Running Tests

Run the standalone automated addon tests:

```bash
make test
```

Behavior:

- uses an isolated test database
- installs `base` and `matomo_analytics`
- runs only addon tests with `--test-tags /matomo_analytics`
- forces `--workers=0`

## Validation Flow

Use this repeatable standalone validation path:

1. `cp .env.example .env`
2. `make up`
3. `make init`
4. open `http://localhost:8069`
5. confirm login works
6. confirm `Matomo Analytics` is visible
7. create or open a connection
8. run `Test Connection`
9. run `Sync Now`
10. open `Overview`
11. open `Sync Logs`
12. run `make test`

## Runtime Utilities

Follow logs:

```bash
make logs
```

Open a shell in the Odoo container:

```bash
make shell
```

Validate the Docker Compose setup:

```bash
make config
```

## Stopping and Cleaning

Stop the stack:

```bash
make down
```

Stop the stack and remove data volumes:

```bash
make clean
```

## Expected Container State After `make test`

`make test` uses `docker compose run --rm odoo ...`.

Expected result:

- the temporary Odoo test container is removed when the test run finishes
- the dependent Postgres container may remain running

This is expected Compose behavior and does not mean an extra Odoo instance is
still running.
