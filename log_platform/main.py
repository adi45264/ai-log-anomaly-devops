"""log-platform — AI log ingestion, anomaly detection and incident summary API.

Sibling of the demo ``app/`` (not nested inside it). Own FastAPI service:

    GET  /health          -> 200 service health
    POST /logs            -> 201 ingest one log record as an observation
    GET  /anomalies       -> 200 detected anomalies from buffered observations
    GET  /incidents       -> 200 incident reports built from current anomalies
    GET  /incidents/{id}  -> 200 single incident report (404 if unknown)

Detection is fully deterministic (rule-based + z-score, no ML deps).
Incident summaries use a deterministic template (no LLM calls in v1).
"""
import logging
import os
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

from log_platform.detector import Observation, detector
from log_platform.logger import (
    get_logger,
    monotonic_ms,
    new_request_id,
    request_id_var,
    setup_logging,
)
from log_platform.summarizer import build_incident

setup_logging(os.getenv("LOG_LEVEL", "INFO"))
logger = get_logger("log-platform")

app = FastAPI(title="log-platform", version="1.0.0")

# In-memory incident store (v1: no external database dependency)
incidents: list[dict] = []


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Attach a request_id and emit one structured log line per request."""
    rid = request.headers.get("x-request-id") or new_request_id()
    token = request_id_var.set(rid)
    start = monotonic_ms()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["x-request-id"] = rid
        return response
    finally:
        latency_ms = monotonic_ms() - start
        level = "ERROR" if status_code >= 500 else ("WARNING" if status_code >= 400 else "INFO")
        logger.log(
            logging.getLevelName(level),
            f"{request.method} {request.url.path} -> {status_code}",
            extra={
                "event": "http_request",
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "latency_ms": latency_ms,
            },
        )
        request_id_var.reset(token)


@app.get("/", include_in_schema=False)
def index():
    """Log platform UI: ingest logs, watch anomalies and incidents."""
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/health")
def health():
    logger.info("health check", extra={"event": "health_check", "status": "healthy"})
    return {"status": "healthy", "service": "log-platform", "version": app.version}


@app.post("/logs", status_code=201)
def ingest_log(record: dict):
    """Ingest one log record and buffer it as a detection observation.

    Required: ``message`` (or ``event``). Optional: ``service``, ``level``,
    ``method``, ``path``, ``status_code``, ``latency_ms``.
    """
    message = record.get("message") or record.get("event")
    if not message:
        raise HTTPException(status_code=422, detail="log record requires 'message' or 'event'")
    obs = Observation(
        timestamp=time.time(),
        method=str(record.get("method", "LOG")),
        path=str(record.get("path", "/logs")),
        status_code=int(record.get("status_code", 200)),
        latency_ms=float(record.get("latency_ms", 0.0)),
    )
    detector.record(obs)
    logger.info(
        "log ingested",
        extra={
            "event": "log_ingested",
            "source_service": record.get("service", "unknown"),
            "level": record.get("level", "INFO"),
        },
    )
    return {"status": "accepted", "observation_count": detector.observation_count}


@app.get("/anomalies")
def get_anomalies():
    """Return detected anomalies from the in-memory observation buffer."""
    result = detector.detect()
    logger.info(
        "anomalies queried",
        extra={
            "event": "anomalies_queried",
            "anomaly_count": len(result["anomalies"]),
            "observation_count": result["observation_count"],
        },
    )
    return result


@app.get("/incidents")
def list_incidents():
    """Build incident report(s) from currently detected anomalies.

    Each call snapshots the current anomalies into a new incident (when any
    are present) and returns the full in-memory incident history.
    """
    result = detector.detect()
    anomalies = result["anomalies"]
    if anomalies:
        incident = build_incident(
            len(incidents) + 1,
            anomalies,
            anomalies[0]["detected_at"],
        )
        incidents.append(incident)
        logger.warning(
            "incident created",
            extra={
                "event": "incident_created",
                "incident_id": incident["id"],
                "anomaly_count": incident["anomaly_count"],
                "severity": incident["severity"],
            },
        )
    return {"count": len(incidents), "incidents": incidents}


@app.get("/incidents/{incident_id}")
def get_incident(incident_id: int):
    for incident in incidents:
        if incident["id"] == incident_id:
            return incident
    raise HTTPException(status_code=404, detail=f"unknown incident id: {incident_id}")
