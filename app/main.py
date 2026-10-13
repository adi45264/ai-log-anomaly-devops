"""ai-log-app ΓÇö FastAPI application with structured JSON logging.

Endpoints:
    GET  /api/health          -> 200 service health
    POST /api/orders          -> 201 create an order
    GET  /api/orders          -> 200 list orders
    POST /api/payment         -> 200 process a payment
    GET  /api/users           -> 200 list users
    POST /api/failure/{kind}  -> 500 simulate a failure (database|payment|latency)
    POST /api/failure/stop    -> 200 stop failure simulation

Every request emits structured JSON logs to stdout (event, status_code,
latency_ms, request_id) so downstream log aggregation and the AI analyzer
can consume machine-parseable data.
"""
import json
import logging
import os
import random
import time
import urllib.request
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from app.logger import (
    get_logger,
    monotonic_ms,
    new_request_id,
    request_id_var,
    setup_logging,
)

setup_logging(os.getenv("LOG_LEVEL", "INFO"))
logger = get_logger("app")

app = FastAPI(title="ai-log-app", version="1.0.0")

# In-memory stores (v1: no external database dependency)
orders: list[dict] = []
users = [
    {"id": 1, "name": "alice", "email": "alice@example.com"},
    {"id": 2, "name": "bob", "email": "bob@example.com"},
]

# Failure simulation state (set by /api/failure/{kind})
failure_state: dict = {"active": False, "kind": None, "started_at": None}


def _ship_to_platform(record: dict) -> None:
    """Best-effort forward of notable shop events to the log platform.

    The shop must keep working standalone, so every error is swallowed.
    Set LOG_PLATFORM_URL="" to disable. Defaults to the local platform.
    """
    base = os.getenv("LOG_PLATFORM_URL", "http://localhost:8001")
    if not base:
        return
    try:
        req = urllib.request.Request(
            base.rstrip("/") + "/logs",
            data=json.dumps(record).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=0.5):
            pass
    except Exception:
        pass


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
    """Demo shop UI for placing orders and simulating failures."""
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/api/health")
def health():
    logger.info("health check", extra={"event": "health_check", "status": "healthy"})
    return {"status": "healthy", "service": "ai-log-app", "version": app.version}


@app.post("/api/orders", status_code=201)
def create_order(order: dict):
    order_id = len(orders) + 1
    record = {
        "order_id": order_id,
        "item": order.get("item", "unknown"),
        "quantity": order.get("quantity", 1),
        "amount": order.get("amount", 0.0),
        "status": "created",
    }
    orders.append(record)
    logger.info("order created", extra={"event": "order_created", "order_id": order_id})
    return record


@app.get("/api/orders")
def list_orders():
    return {"count": len(orders), "orders": orders}


@app.post("/api/payment")
def process_payment(payment: dict):
    order_id = payment.get("order_id")
    amount = payment.get("amount", 0.0)

    if failure_state["active"] and failure_state["kind"] == "database":
        latency_ms = random.randint(7000, 9000)
        time.sleep(latency_ms / 1000)
        logger.error(
            "payment failed",
            extra={
                "event": "database_timeout",
                "order_id": order_id,
                "status_code": 500,
                "latency_ms": latency_ms,
                "error_type": "timeout",
            },
        )
        _ship_to_platform(
            {
                "service": "demo-app",
                "level": "ERROR",
                "message": "database timeout while processing payment",
                "method": "POST",
                "path": "/api/payment",
                "status_code": 500,
                "latency_ms": latency_ms,
            }
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "database timeout while processing payment"},
        )

    if failure_state["active"] and failure_state["kind"] == "payment":
        latency_ms = random.randint(80, 250)
        time.sleep(latency_ms / 1000)
        logger.warning(
            "payment declined",
            extra={
                "event": "payment_declined",
                "order_id": order_id,
                "status_code": 402,
                "latency_ms": latency_ms,
                "error_type": "card_declined",
            },
        )
        _ship_to_platform(
            {
                "service": "demo-app",
                "level": "WARNING",
                "message": "card declined by issuer (simulated payment outage)",
                "method": "POST",
                "path": "/api/payment",
                "status_code": 402,
                "latency_ms": latency_ms,
            }
        )
        return JSONResponse(
            status_code=402,
            content={"detail": "card declined by issuer (simulated payment outage)"},
        )

    if failure_state["active"] and failure_state["kind"] == "latency":
        latency_ms = random.randint(3000, 5000)
        time.sleep(latency_ms / 1000)
        logger.warning(
            "payment slow",
            extra={
                "event": "payment_slow",
                "order_id": order_id,
                "status_code": 200,
                "latency_ms": latency_ms,
            },
        )
        for o in orders:
            if o.get("order_id") == order_id:
                o["status"] = "paid"
        if failure_state["active"] and failure_state["kind"] == "latency":
            _ship_to_platform(
                {
                    "service": "demo-app",
                    "level": "WARNING",
                    "message": "slow payment approved (simulated latency spike)",
                    "method": "POST",
                    "path": "/api/payment",
                    "status_code": 200,
                    "latency_ms": latency_ms,
                }
            )
        return {"status": "approved", "order_id": order_id, "amount": amount, "latency_ms": latency_ms}

    latency_ms = random.randint(80, 250)
    time.sleep(latency_ms / 1000)
    logger.info(
        "payment processed",
        extra={
            "event": "payment_processed",
            "order_id": order_id,
            "amount": amount,
            "status_code": 200,
            "latency_ms": latency_ms,
        },
    )
    for o in orders:
        if o.get("order_id") == order_id:
            o["status"] = "paid"
    return {"status": "approved", "order_id": order_id, "amount": amount, "latency_ms": latency_ms}


@app.delete("/api/orders/{order_id}")
def cancel_order(order_id: int):
    """Cancel an unpaid order."""
    for i, o in enumerate(orders):
        if o.get("order_id") == order_id:
            if o.get("status") == "paid":
                raise HTTPException(status_code=409, detail="paid orders cannot be cancelled")
            del orders[i]
            logger.info("order cancelled", extra={"event": "order_cancelled", "order_id": order_id})
            return {"status": "cancelled", "order_id": order_id}
    raise HTTPException(status_code=404, detail=f"unknown order: {order_id}")


@app.get("/api/users")
def list_users():
    logger.info("users listed", extra={"event": "users_listed", "count": len(users)})
    return {"count": len(users), "users": users}


@app.post("/api/failure/stop")
def stop_failure():
    kind = failure_state["kind"]
    failure_state.update(active=False, kind=None, started_at=None)
    logger.warning(
        f"failure simulation stopped: {kind}",
        extra={"event": "failure_stopped", "failure_kind": kind},
    )
    _ship_to_platform(
        {
            "service": "demo-app",
            "level": "WARNING",
            "message": f"failure simulation stopped: {kind}",
            "method": "POST",
            "path": "/api/failure/stop",
            "status_code": 200,
            "latency_ms": 0,
        }
    )
    return {"status": "failure simulation stopped", "previous_kind": kind}


@app.post("/api/failure/{kind}")
def start_failure(kind: str):
    """Simulate failures: database (timeouts + HTTP 500), payment (declines),
    latency (slow responses)."""
    if kind not in ("database", "payment", "latency"):
        raise HTTPException(status_code=404, detail=f"unknown failure kind: {kind}")
    failure_state.update(active=True, kind=kind, started_at=time.time())
    logger.warning(
        f"failure simulation started: {kind}",
        extra={"event": "failure_started", "failure_kind": kind},
    )
    _ship_to_platform(
        {
            "service": "demo-app",
            "level": "WARNING",
            "message": f"failure simulation started: {kind}",
            "method": "POST",
            "path": f"/api/failure/{kind}",
            "status_code": 200,
            "latency_ms": 0,
        }
    )
    return {"status": "failure simulation started", "kind": kind}
