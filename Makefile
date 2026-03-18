ENV_FILE ?= .env
COMPOSE = docker compose -f docker-compose.dev.yml --env-file $(ENV_FILE)
ODOO = odoo --db_host=db --db_port=5432 --db_user=$${POSTGRES_USER:-odoo} --db_password=$${POSTGRES_PASSWORD:-odoo} --addons-path=/mnt/extra-addons,/usr/lib/python3/dist-packages/odoo/addons --without-demo=all

.PHONY: help env up init update test logs shell down clean config

help:
	@printf "Targets:\n"
	@printf "  make env     # create .env from .env.example if missing\n"
	@printf "  make up      # start postgres and odoo\n"
	@printf "  make init    # create dev DB and install matomo_analytics\n"
	@printf "  make update  # update matomo_analytics in the dev DB\n"
	@printf "  make test    # run addon tests in an isolated DB\n"
	@printf "  make logs    # follow odoo logs\n"
	@printf "  make shell   # open a shell in the odoo container\n"
	@printf "  make down    # stop containers\n"
	@printf "  make clean   # stop containers and remove volumes\n"
	@printf "  make config  # validate docker compose config\n"

env:
	@test -f .env || cp .env.example .env

up: env
	$(COMPOSE) up -d db odoo

init: env
	$(COMPOSE) run --rm odoo bash -lc '$(ODOO) -d $${ODOO_DB:-matomo_dev} -i base,matomo_analytics --stop-after-init'

update: env
	$(COMPOSE) run --rm odoo bash -lc '$(ODOO) -d $${ODOO_DB:-matomo_dev} -u matomo_analytics --stop-after-init'

test: env
	$(COMPOSE) run --rm odoo bash -lc '$(ODOO) -d $${ODOO_TEST_DB:-matomo_test} -i base,matomo_analytics --test-enable --test-tags /matomo_analytics --workers=0 --stop-after-init'

logs: env
	$(COMPOSE) logs -f odoo

shell: env
	$(COMPOSE) run --rm odoo bash

down: env
	$(COMPOSE) down

clean: env
	$(COMPOSE) down -v

config: env
	$(COMPOSE) config
