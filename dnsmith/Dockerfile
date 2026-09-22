# syntax=docker/dockerfile:1

# The build context is THIS folder. Home Assistant builds a local add-on with
# the add-on directory as the context, so every path a COPY names has to live
# inside it — which is why the hub, the frontend and the provider manifests
# all sit here rather than at the repository root.
#
# One stage, one process. The Go engine and its build stage are gone: DNSmith
# performs the updates itself now, so there is nothing to compile and no
# second binary to ship.

ARG BUILD_FROM

FROM ${BUILD_FROM}

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DNSMITH_DATA_DIR=/config/dnsmith \
    DNSMITH_PROVIDERS_DIR=/app/providers \
    DNSMITH_FRONTEND_DIR=/app/frontend \
    DNSMITH_PORT=8099

WORKDIR /app

COPY hub/requirements.txt /app/requirements.txt

# The dependency install, written so that a failure actually fails the build.
#
# The previous version ended in "|| true". That trailing clause applies to the
# whole "A && B" chain, not just to the cleanup it was meant for — so when pip
# did not install anything, the RUN step still reported success, the image was
# built, and the first sign of trouble was the hub crash-looping at runtime
# with ModuleNotFoundError: No module named 'starlette'. An error that only
# surfaces on the user's device is the expensive kind.
#
# --break-system-packages is needed on the newer base images, which mark the
# system interpreter as externally managed (PEP 668). Older pip does not know
# the flag, hence the fallback; the import check below is what decides whether
# either attempt actually worked.
RUN set -eux; \
    python3 -m pip install --no-cache-dir --break-system-packages -r /app/requirements.txt \
      || python3 -m pip install --no-cache-dir -r /app/requirements.txt; \
    python3 -c 'import starlette, uvicorn, httpx, pydantic, yaml, cryptography; print("hub dependencies present")'

# Cosmetic only, and allowed to fail.
RUN find /usr/lib/python3*/site-packages -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

COPY hub/dnsmith_hub/ /app/dnsmith_hub/
COPY providers/*.yaml /app/providers/
COPY frontend/ /app/frontend/

COPY rootfs/ /

RUN chmod +x /etc/s6-overlay/s6-rc.d/dnsmith-hub/run

# Replaces config.yaml's "watchdog" key, which the Supervisor now considers
# obsolete in favour of the native Docker directive. Uses python3 rather than
# curl, since the base image guarantees the former (it's a Python base image)
# but not the latter.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import os,sys,urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ[\"DNSMITH_PORT\"]}/healthz', timeout=3)" || exit 1

LABEL io.hass.type="addon" io.hass.name="DNSmith"
