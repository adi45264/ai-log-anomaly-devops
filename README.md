# AI-Powered Log Analysis DevOps

This repository contains the FastAPI application for AI-Powered Log Analysis, Anomaly Detection and Automated Incident Summarization for Cloud-Native Applications.

## Prerequisites

- **Docker** and **Docker Compose** installed on your machine.
- Optional: Python 3.11+ (if you wish to run the app or tests locally without Docker).

## How to build the image

You can build the Docker image using Docker Compose:

```bash
docker-compose build
```

Or using plain Docker:

```bash
docker build -t ai-log-app .
```

## How to start the application

Start the application using Docker Compose (runs in the background):

```bash
docker-compose up -d
```

The API will be available at `http://localhost:8000`.

## How to test the API

You can test the API endpoints using `curl`.

1. **Check health:**
   ```bash
   curl http://localhost:8000/api/health
   ```

2. **Create an order:**
   ```bash
   curl -X POST http://localhost:8000/api/orders -H "Content-Type: application/json" -d '{"item": "laptop", "quantity": 1, "amount": 1200}'
   ```

3. **Simulate a failure:**
   ```bash
   curl -X POST http://localhost:8000/api/failure/database
   ```

4. **Stop the failure simulation:**
   ```bash
   curl -X POST http://localhost:8000/api/failure/stop
   ```

## How to view container logs

The application is configured to output structured JSON logs directly to standard output (`stdout`), which Docker captures.

To view the logs in real-time using Docker Compose:

```bash
docker-compose logs -f
```

## How to stop the application

To stop and remove the containers created by Docker Compose, run:

```bash
docker-compose down
```


## Continuous Integration (CI)

This project uses GitHub Actions for Continuous Integration. The workflow is defined in `.github/workflows/ci.yml`.

### Workflow Triggers
The CI pipeline automatically runs on:
- Pushes to the `main` branch.
- Pushes to any `feature/*` branch.
- Pull Requests targeting the `main` branch.

### Automated Checks
The CI pipeline performs the following validations:
1. **Linting:** Code quality is enforced using `Ruff`.
2. **Security Checks:** Dependencies are scanned for known vulnerabilities using `pip-audit`.
3. **Automated Tests:** The existing `pytest` suite is executed to ensure application stability.
4. **Docker Validation:** If the tests and linting pass, the pipeline builds the Docker image and tags it as `ai-log-anomaly-devops:ci` to verify the `Dockerfile` builds successfully in a clean environment (the image is not published to any registry).

### How to Inspect Workflow Results
To view the results of the automated CI runs:
1. Navigate to this repository on GitHub.
2. Click on the **Actions** tab at the top.
3. Select the **CI Pipeline** workflow from the left sidebar to view the history and logs of all workflow runs.

## Phase 3: Centralized Logging (Loki & Grafana)

The application has been extended with a centralized logging stack using **Grafana Loki** (log storage) and **Grafana Alloy** (log collector) and **Grafana** (visualization).

### Startup Instructions
The entire stack (API, Loki, Alloy, Grafana) runs together via Docker Compose:

```bash
docker-compose up -d
```

### Local URLs
*   **FastAPI Application:** `http://localhost:8000`
*   **Grafana Dashboard:** `http://localhost:3000` (Anonymous login enabled, no credentials needed)
*   **Loki API:** `http://localhost:3100`

### How to View Application Logs in Grafana
1. Open **Grafana** at `http://localhost:3000`.
2. Navigate to **Explore** (compass icon on the left menu).
3. Select **Loki** from the datasource dropdown at the top left.
4. In the Label browser or Query field, enter `{service="api"}` and click **Run Query**.
5. You will see the structured JSON logs emitted by the FastAPI application.
6. You can expand log lines to see the parsed JSON fields (like `latency_ms`, `event`, etc.).

### Troubleshooting
*   **No logs appearing in Grafana?** Ensure that your Docker daemon permits mounting `/var/run/docker.sock` to the Alloy container so it can discover and collect container logs. This is mapped in `docker-compose.yml`.
*   **Container Restarting:** You can check individual service logs using standard Docker commands: `docker-compose logs alloy` or `docker-compose logs loki` to identify specific errors.
*   **Security Note:** Grafana is configured with anonymous admin access for convenience during local development. Do not expose this configuration to the public internet or use it in production environments.

## Two apps in one repo (sibling folders, not nested)

| Folder | Service | Port | Role | Key endpoints |
|---|---|---|---|---|
| `app/` | demo-app (`ai-log-app`) | 8000 | Demo business app = log producer | `GET /api/health`, `POST /api/orders`, `POST /api/payment`, `GET /api/users`, `POST /api/failure/{kind}`, `POST /api/failure/stop` |
| `log_platform/` | log-platform | 8001 | AI log platform = log consumer | `GET /health`, `POST /logs`, `GET /anomalies`, `GET /incidents`, `GET /incidents/{id}` |

Run locally (two terminals):

```bash
# terminal 1 - demo app
uvicorn app.main:app --port 8000
# terminal 2 - log platform
uvicorn log_platform.main:app --port 8001
```

Or the full stack (both apps + Loki + Alloy + Grafana):

```bash
docker-compose up -d --build
# demo app:      http://localhost:8000
# log platform:  http://localhost:8001
# grafana:       http://localhost:3000
# loki:          http://localhost:3100
```

Ship a demo failure to the platform and watch detection happen:

```bash
curl -X POST http://localhost:8000/api/failure/database
for i in 1 2 3 4 5 6; do
  curl -s -X POST http://localhost:8000/api/payment -H "Content-Type: application/json" -d '{"order_id":1,"amount":10}' > /dev/null
  curl -s -X POST http://localhost:8001/logs -H "Content-Type: application/json" -d '{"service":"demo-app","level":"ERROR","message":"database timeout","method":"POST","path":"/api/payment","status_code":500,"latency_ms":8000}' > /dev/null
done
curl http://localhost:8001/anomalies | python3 -m json.tool
curl http://localhost:8001/incidents | python3 -m json.tool
curl -X POST http://localhost:8000/api/failure/stop
```

## Phase 4: Anomaly Detection + Incident Summarization (log-platform)

Detection lives in the `log_platform/` service, fed by `POST /logs`
records buffered in a bounded in-memory deque (`AnomalyDetector._buffer`,
default capacity 1000 entries). When full, the oldest entry is evicted,
so memory use is capped regardless of traffic volume.

Each call to `GET /anomalies` runs three independent, fully deterministic
detection rules:

| Rule | Trigger | Severity |
|---|---|---|
| `error_spike` | >= N HTTP 5xx in the last W observations | `medium` (< 50% error rate) / `high` (>= 50%) |
| `high_latency` | Any single request exceeds L ms | `medium` (< 2x threshold) / `high` (>= 2x threshold) |
| `latency_zscore` | Latency > Z std-devs above the held-out baseline mean (needs >= M baseline obs, std > 0) | `medium` (z < 1.5x threshold) / `high` (z >= 1.5x threshold) |

No external APIs, no ML libraries, no randomness.

`GET /incidents` groups the currently detected anomalies into one incident
report (`log_platform/summarizer.py`, deterministic template, no LLM calls
in v1): id, title, worst severity, human-readable summary, anomaly types,
and the raw anomalies. `GET /incidents/{id}` fetches one report (404 if
unknown).

### Configurable thresholds

Constructor parameters of `AnomalyDetector` (`log_platform/detector.py`):

| Parameter | Default | Description |
|---|---|---|
| `buffer_size` | `1000` | Maximum observations retained in memory |
| `error_spike_window` | `50` | Recent observations examined for 5xx spikes |
| `error_spike_threshold` | `5` | Minimum 5xx count to trigger a spike alert |
| `latency_threshold_ms` | `2000` | Per-request latency (ms) above which a slow alert fires |
| `zscore_threshold` | `3.0` | Z-score above which latency is flagged as an outlier |
| `min_baseline_size` | `30` | Minimum baseline size before z-score activates |

### Endpoints (port 8001)

```bash
curl -X POST http://localhost:8001/logs -H "Content-Type: application/json" \
  -d '{"service":"demo-app","level":"ERROR","message":"db timeout","status_code":500}'
curl http://localhost:8001/anomalies | python3 -m json.tool
curl http://localhost:8001/incidents | python3 -m json.tool
curl http://localhost:8001/incidents/1 | python3 -m json.tool
```

### Limitations of in-memory state

* **Restarts reset history** - the buffer and incident list are process-local.
* **Single-process only** - each replica detects independently.
* **No persistence** - use the Loki/Grafana stack for durable log querying across restarts.
* **Z-score warm-up** - needs `min_baseline_size` (default 30) baseline
  observations; on a fresh start only `error_spike` and `high_latency` fire.

## Grafana dashboard

A provisioned dashboard `AI Log Anomaly DevOps` loads automatically at
`http://localhost:3000` (see `monitoring/grafana/provisioning/dashboards/`):

* Log volume by service (`api`, `log-platform`)
* Demo-app error rate (`level="ERROR"`)
* Incidents created (`incident_created` events from the platform)
* Latest anomaly count (`anomalies_queried` events)

Raw exploration still works via Explore + Loki datasource with
`{service="api"}` or `{service="log-platform"}`.

## Kubernetes

```bash
docker build -t ai-log-anomaly-devops:latest .
docker build -f Dockerfile.platform -t ai-log-platform:latest .
kubectl apply -f k8s/
kubectl get pods,svc
kubectl port-forward svc/demo-app 8000:8000 &
kubectl port-forward svc/log-platform 8001:8001 &
```

`k8s/configmap.yaml` holds shared config (`LOG_LEVEL`, consumed by both
services via `envFrom`).

## End-to-end test (NFR-6)

`log_platform/tests/test_e2e.py` drives both apps: start demo failure ->
failing payments -> ship each failure via `POST /logs` -> assert
`error_spike` in `GET /anomalies` -> assert incident in `GET /incidents`
-> stop failure -> demo healthy again.

```bash
pytest -v                          # all suites: app + log-platform
pytest log_platform/tests/test_e2e.py -v   # E2E only
```
