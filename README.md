# Matomo Analytics

Standalone Odoo 18 addon for storing Matomo analytics data inside Odoo.

## Local Dev Setup

This repository includes a minimal Docker-based dev environment so you can
clone the addon on another machine and work on it without the larger CURQ
monorepo.

### Prerequisites

- Docker
- Docker Compose

### First-Time Setup

Clone the repository and enter it:

```bash
git clone git@github.com:MyCleaningSupplies/odoo_matomo_analytics.git
cd odoo_matomo_analytics
```

Create a local environment file:

```bash
cp .env.example .env
```

Start the containers:

```bash
make up
```

Create the development database and install the addon:

```bash
make init
```

Open Odoo at:

```text
http://localhost:8069
```

### Day-to-Day Commands

Start or restart the local stack:

```bash
make up
```

Update the module after code changes:

```bash
make update
```

Run the addon tests in an isolated database:

```bash
make test
```

Follow the Odoo logs:

```bash
make logs
```

Open a shell in the Odoo container:

```bash
make shell
```

Stop the stack:

```bash
make down
```

Remove the stack and database volumes:

```bash
make clean
```

Validate the compose setup:

```bash
make config
```

## Notes

- The addon is mounted into the container from the working tree, so normal
  code edits on your machine are immediately available to Odoo.
- `make update` is the normal way to reload Python/XML changes into the dev
  database.
- `make test` runs the addon's Odoo tests with `--workers=0` to avoid the
  worker-mode test issues seen in this environment.
- Syncing against a real Matomo instance still requires valid Matomo
  connection details and network access from the Odoo container.
