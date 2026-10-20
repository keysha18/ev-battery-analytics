include .env
export

export PATH := $(HOME)/.local/bin:$(PATH)
export HOST_UID := $(shell id -u)
export HOST_GID := $(shell id -g)

COMPOSE := docker compose
DBT     := $(COMPOSE) run --rm dbt
PSQL    := $(COMPOSE) exec postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

.PHONY: help up down ps logs psql reset check download ingest checks test lint dbt-deps dbt-build dbt-docs

help:  ## Liste les commandes
	@grep -hE '^[a-z_]+:.*##' Makefile | awk -F':.*## ' '{printf "  %-9s %s\n", $$1, $$2}'

up:  ## Démarre Postgres et attend qu'il soit prêt
	$(COMPOSE) up -d --wait postgres

down:  ## Arrête les services (garde les données)
	$(COMPOSE) down

ps:  ## État des services
	$(COMPOSE) ps

logs:  ## Logs Postgres
	$(COMPOSE) logs -f postgres

psql:  ## Ouvre un shell psql
	$(PSQL)

check:  ## Smoke test du socle (schémas, droits du rôle API)
	./tests/smoke_db.sh

download:  ## Télécharge et extrait le dataset NASA (vérifié par sha256)
	uv run python -m src.ingest.download

ingest: up  ## Charge les .mat dans raw (rejouable sans doublons)
	uv run python -m src.ingest

dbt-deps:  ## Installe les packages dbt (dbt_utils)
	$(DBT) deps

dbt-build: up dbt-deps  ## Seeds + modèles + tests dbt (raw doit être chargé)
	$(DBT) build

dbt-docs:  ## Génère la doc dbt (dbt/target/)
	$(DBT) docs generate

checks:  ## Contrôles de cohérence du schéma raw (après ingest)
	$(COMPOSE) exec -T postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) < tests/checks_raw.sql

test:  ## Tests unitaires + intégration (Postgres requis)
	uv run pytest -q

lint:  ## Ruff
	uv run ruff check src tests

reset:  ## DÉTRUIT le volume de données et recrée la base
	@read -p "Supprimer toutes les données Postgres ? [y/N] " a; [ "$$a" = "y" ]
	$(COMPOSE) down -v
	$(MAKE) up
