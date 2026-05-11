# SporeDB Self-Hosted Deployment Makefile
# ----------------------------------------
# Provides one-command workflows for build, deploy, air-gapped transfer,
# key generation, and compliance validation.

.PHONY: build up down logs save-airgap load-airgap generate-keys validate-compliance status

IMAGE_TAG ?= 0.1.0
COMPOSE_FILES := -f docker-compose.yml -f docker-compose.selfhosted.yml

# --- Build & Deploy ---

build:
	docker compose build

up: generate-keys
	docker compose $(COMPOSE_FILES) up -d

down:
	docker compose $(COMPOSE_FILES) down

logs:
	docker compose $(COMPOSE_FILES) logs -f

status:
	docker compose $(COMPOSE_FILES) ps

# --- Air-Gapped Deployment ---

save-airgap: build
	docker save sporedb:$(IMAGE_TAG) postgres:16-alpine minio/minio:latest -o sporedb-airgap-$(IMAGE_TAG).tar
	@echo "Saved air-gapped bundle to sporedb-airgap-$(IMAGE_TAG).tar"
	@echo "Transfer this file to the air-gapped server."

load-airgap:
	docker load -i sporedb-airgap-$(IMAGE_TAG).tar
	@echo "Loaded air-gapped images. Run 'make up' to start."

# --- Key Management ---

generate-keys:
	@if [ ! -f keys/cloud_private.pem ]; then \
		bash scripts/generate-keys.sh; \
	else \
		echo "Keys already exist in keys/. Skipping generation."; \
	fi

# --- Compliance ---

validate-compliance:
	docker compose $(COMPOSE_FILES) exec sporedb python -m sporedb.compliance.validator --check
	@echo "Compliance validation complete."
