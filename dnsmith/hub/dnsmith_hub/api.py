"""The HTTP API the Ingress UI and the Home Assistant integration both use.

There is one API, not two. Anything the integration may do, the UI may do, and
the other way round — a private back door would be a second surface to secure
and a second place for a bug to hide.

Built on Starlette rather than FastAPI: the manifests already describe every
provider-specific shape, so the schema generation FastAPI is chosen for buys
nothing here, and the add-on image stays smaller.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .adapters.base import AdapterError
from .errors import explain
from .registry import ProviderNotFound, ValidationProblem, build_form
from .store import DuplicateRecord, RecordNotFound

logger = logging.getLogger("dnsmith.hub")


def json_response(payload: Any, status: int = 200) -> JSONResponse:
    return JSONResponse(
        payload,
        status_code=status,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


def error_response(code: str, message: str, status: int, **extra: Any) -> JSONResponse:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    body["error"].update(extra)
    return json_response(body, status)


async def read_json(request: Request) -> dict[str, Any]:
    body = await request.body()
    if not body:
        return {}
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        raise BadRequest(f"Der Anfragekörper ist kein gültiges JSON: {error}") from error
    if not isinstance(payload, dict):
        raise BadRequest("Erwartet wird ein JSON-Objekt.")
    return payload


class BadRequest(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def build_routes(service) -> list[Route]:
    """Wire the routes to a Service.

    `service` carries the store, registry and adapters. Keeping the handlers
    free of construction makes them straightforward to test: build a Service
    over temporary files and a fake engine, and the whole API is exercisable.
    """

    async def list_providers(request: Request) -> Response:
        query = request.query_params.get("q", "")
        category = request.query_params.get("category")

        providers = service.registry.search(query, category)
        return json_response(
            {
                "providers": [
                    summary
                    for summary in service.registry.summaries()
                    if summary["id"] in {provider.id for provider in providers}
                ],
                "categories": service.registry.categories(),
                "total": len(service.registry),
            }
        )

    async def get_provider(request: Request) -> Response:
        provider_id = request.path_params["provider_id"]
        try:
            provider = service.registry.get(provider_id)
        except ProviderNotFound:
            return error_response("provider_not_found", "Diesen Anbieter gibt es nicht.", 404)
        return json_response(build_form(provider))

    async def list_records(request: Request) -> Response:
        return json_response(service.records_payload())

    async def get_record(request: Request) -> Response:
        try:
            record = service.store.record(request.path_params["record_id"])
        except RecordNotFound:
            return error_response("record_not_found", "Diesen Eintrag gibt es nicht.", 404)
        return json_response(service.record_payload(record))

    async def create_record(request: Request) -> Response:
        payload = await read_json(request)
        try:
            record = service.create_record(payload)
        except ProviderNotFound:
            return error_response("provider_not_found", "Diesen Anbieter gibt es nicht.", 404)
        except ValidationProblem as problem:
            return error_response(
                "validation_failed",
                "Bitte die markierten Felder prüfen.",
                422,
                fields=problem.problems,
            )
        except DuplicateRecord as duplicate:
            return error_response("duplicate_record", str(duplicate), 409)
        except KeyError as missing:
            return error_response("field_missing", f"Es fehlt die Angabe {missing}.", 400)

        # Update straight away rather than at the next scheduled pass. Someone
        # who just typed in credentials wants to know whether they work, and
        # making them wait minutes for the answer — or press a button to get
        # it — is the kind of waiting that has no reason behind it. Saving the
        # record is the consent; the probe before it deliberately writes
        # nothing, this deliberately does.
        #
        # In the background, so the answer to this request is not held up by
        # a provider that is slow.
        asyncio.create_task(_update_soon(service, record.id))

        return json_response(service.record_payload(record), 201)

    async def update_record(request: Request) -> Response:
        payload = await read_json(request)
        try:
            record = service.store.update_record(
                request.path_params["record_id"],
                values=payload.get("values"),
                label=payload.get("label"),
                enabled=payload.get("enabled"),
                auth_variant=payload.get("auth_variant"),
            )
            service.apply()
        except RecordNotFound:
            return error_response("record_not_found", "Diesen Eintrag gibt es nicht.", 404)
        except ValidationProblem as problem:
            return error_response(
                "validation_failed",
                "Bitte die markierten Felder prüfen.",
                422,
                fields=problem.problems,
            )
        except AdapterError as error:
            return json_response(
                {"error": explain(error.as_dict(), redactor=service.redactor)}, 502
            )
        return json_response(service.record_payload(record))

    async def delete_record(request: Request) -> Response:
        try:
            service.delete_record(request.path_params["record_id"])
        except RecordNotFound:
            return error_response("record_not_found", "Diesen Eintrag gibt es nicht.", 404)
        except AdapterError as error:
            return json_response(
                {"error": explain(error.as_dict(), redactor=service.redactor)}, 502
            )
        return Response(status_code=204)

    async def test_record(request: Request) -> Response:
        payload = await read_json(request)
        mode = payload.get("mode", "validate")
        if mode not in ("validate", "live"):
            return error_response("bad_request", "mode muss validate oder live sein.", 400)

        try:
            result = await asyncio.to_thread(service.probe, payload, mode)
        except ProviderNotFound:
            return error_response("provider_not_found", "Diesen Anbieter gibt es nicht.", 404)
        except ValidationProblem as problem:
            return error_response(
                "validation_failed",
                "Bitte die markierten Felder prüfen.",
                422,
                fields=problem.problems,
            )
        except AdapterError as error:
            return json_response(
                {"error": explain(error.as_dict(), redactor=service.redactor)}, 502
            )

        return json_response(
            {
                "ok": result.ok,
                "mode": result.mode,
                "duration_ms": result.duration_ms,
                "ip_used": result.ip_used,
                # What was actually checked, so the interface can say it
                # rather than implying more than happened.
                "checked": result.checked,
                "message": result.message,
                "error": explain(result.error, redactor=service.redactor),
            }
        )

    async def force_update(request: Request) -> Response:
        record_id = request.path_params.get("record_id")
        try:
            result = await asyncio.to_thread(service.force_update, record_id)
        except RecordNotFound:
            return error_response("record_not_found", "Diesen Eintrag gibt es nicht.", 404)
        except AdapterError as error:
            return json_response(
                {"error": explain(error.as_dict(), redactor=service.redactor)}, 502
            )
        return json_response(result)

    async def status(request: Request) -> Response:
        return json_response(service.status_payload())

    async def public_ip(request: Request) -> Response:
        refresh = request.query_params.get("refresh") == "true"
        try:
            address = await asyncio.to_thread(service.public_ip, refresh)
        except AdapterError as error:
            return json_response(
                {"error": explain(error.as_dict(), redactor=service.redactor)}, 503
            )
        return json_response(address)

    async def export_config(request: Request) -> Response:
        include = request.query_params.get("include_secrets") == "true"
        return json_response(service.store.export(include_secrets=include))

    async def get_settings(request: Request) -> Response:
        return json_response(service.store.config.settings.model_dump(mode="json"))

    async def put_settings(request: Request) -> Response:
        payload = await read_json(request)
        try:
            service.store.update_settings(payload)
            service.apply()
        except ValueError as error:
            return error_response("validation_failed", str(error), 422)
        except AdapterError as error:
            return json_response(
                {"error": explain(error.as_dict(), redactor=service.redactor)}, 502
            )
        return json_response(service.store.config.settings.model_dump(mode="json"))

    async def healthz(request: Request) -> Response:
        return json_response({"status": "ok", "records": len(service.store.records())})

    async def readyz(request: Request) -> Response:
        return json_response(service.readiness())

    return [
        Route("/api/v1/providers", list_providers),
        Route("/api/v1/providers/{provider_id}", get_provider),
        Route("/api/v1/records", list_records),
        Route("/api/v1/records", create_record, methods=["POST"]),
        Route("/api/v1/records/{record_id}", get_record),
        Route("/api/v1/records/{record_id}", update_record, methods=["PATCH"]),
        Route("/api/v1/records/{record_id}", delete_record, methods=["DELETE"]),
        Route("/api/v1/records/{record_id}/update", force_update, methods=["POST"]),
        Route("/api/v1/records/update-all", force_update, methods=["POST"]),
        Route("/api/v1/test", test_record, methods=["POST"]),
        Route("/api/v1/status", status),
        Route("/api/v1/ip", public_ip),
        Route("/api/v1/settings", get_settings),
        Route("/api/v1/settings", put_settings, methods=["PUT"]),
        Route("/api/v1/config/export", export_config),
        Route("/healthz", healthz),
        Route("/readyz", readyz),
    ]


async def bad_request_handler(request: Request, exc: BadRequest) -> Response:
    return error_response("bad_request", exc.message, 400)


def create_app(service) -> Starlette:
    return Starlette(
        routes=build_routes(service),
        exception_handlers={BadRequest: bad_request_handler},
    )


async def _update_soon(service, record_id: str) -> None:
    """Run one update for a freshly created record, out of band.

    A failure here is not reported back to the request that created the
    record — the record exists either way, and the result shows up in its
    status a moment later, which is where the user is already looking.
    """
    try:
        await asyncio.to_thread(service.scheduler.update, record_id)
    except Exception as error:  # noqa: BLE001 - the status carries the detail
        logger.info("first update for %s did not succeed: %s", record_id, error)
