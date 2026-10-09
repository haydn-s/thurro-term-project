# syntax=docker/dockerfile:1
#
# The deliverable: the model, its feature snapshot and an HTTP server, in one
# image that runs on any Docker manager.
#
# BUILD CONTEXT IS THE REPOSITORY ROOT, not this directory, because the image
# bakes in the panel that scripts/build_panel.py produces under data/. Build it
# as:
#
#     docker build -f final-deliverable/Dockerfile -t ev-capex-signal:0.1.0 .
#
# from the repo root, or just use `make build` / `docker compose build`, both of
# which set the context correctly. Building with this directory as the context
# fails on the data COPY, which is the intended failure -- an image without its
# feature snapshot has nothing to serve.

# ---------------------------------------------------------------- builder ----
# 3.14 matches the Python the repo's notebooks and build scripts are pinned to
# (3.14.7), so a model fitted in that environment deserialises here.
# Pin this by digest before anything is deployed for real; a floating tag means
# the image is not actually reproducible.
FROM python:3.14-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# A venv, so the runtime stage can take the dependencies as one directory and
# leave pip, its caches and any build toolchain behind in this stage.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Requirements before source: this layer is then cached across every change to
# app/, which is most changes.
COPY final-deliverable/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

# ---------------------------------------------------------------- runtime ----
FROM python:3.14-slim AS runtime

LABEL org.opencontainers.image.title="EV capex signal service" \
      org.opencontainers.image.description="Per-company automotive capex expansion signals over HTTP/SSE." \
      org.opencontainers.image.source="https://github.com/haydn-s/thurro-term-project" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FEATURE_STORE=/app/feature-store \
    SIGNAL_PORT=8000

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

# The feature snapshot. Baked in rather than mounted so the image is
# self-contained and a given tag always serves the same numbers -- that is what
# makes a result reproducible months later. Mount over it to refresh without a
# rebuild (see docker-compose.yml) and POST /signals/refresh.
COPY data/processed/*.csv            /app/feature-store/
COPY data/manual/target_companies.csv /app/feature-store/

COPY final-deliverable/app /app/app

# Non-root, and the application tree is not writable by the account that runs
# it. Nothing here needs to write to disk; a compromised request handler should
# not be able to alter the model, the panel or the code it is running.
# An explicit high uid/gid rather than --system: a system account is expected to
# sit below SYS_UID_MAX (999), and useradd warns when it does not. 10001 is
# deliberate -- it stays clear of host accounts, so a mounted volume's
# ownership means the same thing inside and out.
RUN groupadd --gid 10001 signal \
 && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin signal \
 && chown -R root:root /app \
 && chmod -R a-w /app
USER 10001

# Documentation only -- it publishes nothing. The port the server actually binds
# comes from SIGNAL_PORT, so override both together if you change it.
EXPOSE 8000

# Tuned against a measurement, not a guess: these settings surface a container
# that can never become ready in ~35s. The panel loads in milliseconds and the
# probe is a loopback GET, so a short interval costs nothing. Raise start-period
# if a fitted model ever makes startup slow.
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD ["python", "-m", "app.healthcheck", "/ready"]

# Exec form: uvicorn receives SIGTERM directly as PID 1 and shuts down cleanly,
# instead of a shell swallowing it and leaving the manager to SIGKILL after its
# grace period.
CMD ["python", "-m", "app"]
