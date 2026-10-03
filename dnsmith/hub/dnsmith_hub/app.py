"""Entry point: build the hub from the environment and serve it.

Everything configurable arrives as an environment variable rather than as an
add-on option, because every add-on option is YAML the user has to write — and
the whole point of DNSmith is that they never have to. The variables here are
set by the container, not by the user.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .api import BadRequest, bad_request_handler, build_routes
from .publicip import AddressSources, PublicIPResolver, SupervisorClient
from .redact import ValueRedactor, install, install_everywhere
from .registry import Registry
from .scheduler import Scheduler, parse_duration
from .secrets import SecretStore
from .service import Service
from .store import ConfigStore

logger = logging.getLogger("dnsmith.hub")

DEFAULTS = {
    "DNSMITH_DATA_DIR": "/config/dnsmith",
    "DNSMITH_PROVIDERS_DIR": "/app/providers",
    "DNSMITH_FRONTEND_DIR": "/app/frontend",
    "DNSMITH_HOST": "0.0.0.0",  # noqa: S104 - the container is the boundary
    "DNSMITH_PORT": "8099",
    "DNSMITH_LOG_LEVEL": "info",
}


def setting(name: str) -> str:
    return os.environ.get(name) or DEFAULTS[name]


def build_service() -> Service:
    data_dir = Path(setting("DNSMITH_DATA_DIR"))
    data_dir.mkdir(parents=True, exist_ok=True)

    registry = Registry(
        Path(setting("DNSMITH_PROVIDERS_DIR")),
        logo_dir=Path(setting("DNSMITH_FRONTEND_DIR")) / "assets" / "logos",
    )
    registry.load()
    logger.info("loaded %d providers", len(registry))

    secret_store = SecretStore(data_dir / "secrets.json")
    secret_store.load()

    store = ConfigStore(data_dir / "config.json", secret_store, registry)
    store.load()
    if store.load_error:
        # Loud, because nothing else will be: the add-on comes up, the
        # interface says the same thing, and neither is a reason to hide it
        # from the log.
        logger.error("%s", store.load_error)

    # The Supervisor token arrives in the environment because config.yaml
    # asks for hassio_api. Without it the entity modes cannot work, and
    # AddressSources says so instead of failing obscurely.
    supervisor = SupervisorClient()
    if not supervisor.available:
        logger.info(
            "no Supervisor token: reading addresses from Home Assistant entities "
            "is unavailable in this environment"
        )

    scheduler = Scheduler(
        registry=registry,
        store=store,
        secrets=secret_store,
        sources=AddressSources(http=PublicIPResolver(), supervisor=supervisor),
    )

    redactor = ValueRedactor()
    service = Service(
        registry=registry,
        store=store,
        secrets=secret_store,
        scheduler=scheduler,
        redactor=redactor,
    )

    # Installed before anything else can log, so no credential can slip out
    # during start-up. install_everywhere() is the one that actually covers
    # this add-on: every module logs on "dnsmith.hub", a child logger, and a
    # filter on the parent never sees those records - only the handlers do.
    install_everywhere(redactor)
    install(logging.getLogger("dnsmith"), redactor)
    install(logging.getLogger("uvicorn.error"), redactor)

    orphans = store.prune_orphaned_secrets()
    if orphans:
        logger.info("removed %d orphaned credential set(s)", len(orphans))

    return service


def create_app(service: Service | None = None) -> Starlette:
    service = service or build_service()
    frontend = Path(setting("DNSMITH_FRONTEND_DIR"))

    routes = list(build_routes(service))

    if frontend.is_dir():
        index = frontend / "index.html"

        async def serve_index(request: Request) -> Response:
            # Every view is rendered client-side, so any path that is not the
            # API returns the same document. Ingress mounts the add-on under a
            # generated prefix, which is why the page uses relative URLs
            # throughout and never an absolute /api/... path.
            return FileResponse(index, headers={"Cache-Control": "no-store"})

        routes.append(Mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets"))
        routes.append(Route("/", serve_index))
        routes.append(Route("/{path:path}", serve_index))
    else:  # pragma: no cover - only when the image was built wrong
        logger.warning("frontend directory %s not found; serving the API only", frontend)

    @asynccontextmanager
    async def lifespan(_app: Starlette):
        """Run the update loop for as long as the hub is serving.

        The loop is a task rather than a thread of its own so that shutdown is
        ordinary cancellation. Each pass runs in a worker thread, because the
        scheduler is deliberately synchronous — its decisions are worth being
        able to test without an event loop.

        A failure inside a pass is logged and the loop continues. The one
        thing that must not happen is the UI going away because an update
        went wrong.
        """
        service.apply()
        task = asyncio.create_task(_update_loop(service), name="dnsmith-scheduler")
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    return Starlette(
        routes=routes,
        lifespan=lifespan,
        exception_handlers={BadRequest: bad_request_handler},
    )


async def _update_loop(service: Service) -> None:
    # A first pass shortly after start-up rather than immediately: the
    # container's network is not always up the moment the process is.
    await asyncio.sleep(10)

    while True:
        try:
            await asyncio.to_thread(service.scheduler.tick)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001
            logger.warning("update pass failed: %s", error)

        # The pass itself decides per record when that record is next due;
        # this only controls how often the question gets asked, and it must
        # never be longer than the shortest interval a record could have.
        interval = parse_duration(service.store.config.settings.poll_interval, 300.0)
        await asyncio.sleep(max(30.0, min(interval, 300.0)))


UVICORN_LEVELS = frozenset({"critical", "error", "warning", "info", "debug", "trace"})


# What the standard library accepts but uvicorn does not. Without this map a
# DNSMITH_LOG_LEVEL=warn would silently become "info" here, while it used to
# mean WARNING - quieter settings would have turned chattier, which is the
# opposite of what the person asked for.
LEVEL_ALIASES = {"warn": "warning", "fatal": "critical", "notset": "debug"}


def log_level() -> str:
    """The configured level, or "info" when it is not one uvicorn accepts.

    uvicorn takes the name as a lowercase string and raises on anything else,
    which would turn a typo into a service that never starts and is restarted
    forever. configure_logging() already shrugs off a bad value; this makes
    the uvicorn side just as forgiving, without quietly changing what a valid
    setting means.
    """
    value = setting("DNSMITH_LOG_LEVEL").strip().lower()
    value = LEVEL_ALIASES.get(value, value)
    return value if value in UVICORN_LEVELS else "info"


def configure_logging() -> None:
    level = log_level().upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        stream=sys.stdout,
    )


def main() -> int:
    configure_logging()

    import uvicorn

    try:
        application = create_app()
    except Exception as error:  # noqa: BLE001
        logger.error("start-up failed: %s", error)
        return 1

    uvicorn.run(
        application,
        host=setting("DNSMITH_HOST"),
        port=int(setting("DNSMITH_PORT")),
        log_level=log_level(),
        access_log=False,
        # Ingress terminates in front of us and adds its own headers; trusting
        # them lets the app see the real client, and nothing else can reach
        # this port.
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
