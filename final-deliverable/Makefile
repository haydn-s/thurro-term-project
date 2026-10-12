# Shortcuts for the deliverable. Run from anywhere; every recipe resolves the
# repo root itself, because the image build needs that as its context.
#
#   make build     build the image
#   make up        run it via compose, in the background
#   make smoke     exercise every endpoint against a running container
#   make test      run the test suite on the host, no Docker needed
#   make down      stop and remove the container

ROOT  := $(shell git rev-parse --show-toplevel)
HERE  := final-deliverable
IMAGE := ev-capex-signal:0.1.0
PORT  ?= 8000
COMPOSE := docker compose -f $(ROOT)/$(HERE)/docker-compose.yml

.PHONY: build up down logs smoke test run shell clean venv

build:
	cd $(ROOT) && docker build -f $(HERE)/Dockerfile -t $(IMAGE) .

up:
	$(COMPOSE) up --build -d
	@echo "signals: http://localhost:$(PORT)/signals"

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f signal

# Plain `docker run`, to prove the image needs no compose file.
run: build
	docker run --rm -p $(PORT):8000 --name ev-capex-signal $(IMAGE)

shell:
	docker run --rm -it --entrypoint /bin/bash $(IMAGE)

smoke:
	PORT=$(PORT) $(ROOT)/$(HERE)/scripts/smoke_test.sh

# The suite runs against the source tree and the repo's own data/processed, so
# it catches breakage without a 30-second image build in the loop.
venv:
	python3 -m venv $(ROOT)/$(HERE)/.venv
	$(ROOT)/$(HERE)/.venv/bin/pip install -q -r $(ROOT)/$(HERE)/requirements-dev.txt

test:
	cd $(ROOT)/$(HERE) && FEATURE_STORE=$(ROOT)/data/processed \
	  .venv/bin/python -m pytest tests -q

clean:
	rm -rf $(ROOT)/$(HERE)/.venv
	find $(ROOT)/$(HERE) -name __pycache__ -type d -exec rm -rf {} +
