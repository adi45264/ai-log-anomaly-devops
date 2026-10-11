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

## Phase 4: Anomaly Detection

The application now includes an in-process anomaly detector that continuously
analyses the stream of incoming HTTP requests and exposes its findings via a
dedicated API endpoint.

### How It Works

All HTTP observations (recorded by the existing middleware) are appended to a
**bounded in-memory deque** (`AnomalyDetector._buffer`, default capacity
**1 000** entries). When the buffer is full the oldest entry is evicted
automatically — memory usage is therefore capped regardless of traffic volume.

Each call to `GET /api/anomalies` runs three independent, fully deterministic
detection rules:

| Rule | Trigger | Severity |
|---|---|---|
| `error_spike` | ≥ N HTTP 5xx responses in the last W observations | `medium` (< 50 % error rate) / `high` (≥ 50 %) |
| `high_latency` | Any single request exceeds L ms | `medium` (< 2× threshold) / `high` (≥ 2× threshold) |
| `latency_zscore` | A request's latency is > Z standard deviations above the buffer mean (only when baseline ≥ M observations and std > 0) | `medium` (z < 1.5× threshold) / `high` (z ≥ 1.5× threshold) |

No external APIs, no ML libraries, and no randomness are used.

### Configurable Thresholds

All thresholds are constructor parameters of `AnomalyDetector`
(`app/anomaly_detector.py`). The module-level singleton uses these defaults:

| Parameter | Default | Description |
|---|---|---|
| `buffer_size` | `1000` | Maximum observations retained in memory |
| `error_spike_window` | `50` | Recent observations examined for 5xx spikes |
| `error_spike_threshold` | `5` | Minimum 5xx count to trigger a spike alert |
| `latency_threshold_ms` | `2000` | Per-request latency (ms) above which a slow alert fires |
| `zscore_threshold` | `3.0` | Z-score above which a latency observation is flagged as an outlier |
| `min_baseline_size` | `30` | Minimum buffer size before z-score analysis is activated |

### Endpoint: `GET /api/anomalies`

Returns a JSON object describing currently detected anomalies and supporting
metadata.

**Example response (anomaly detected):**
```json
{
  "anomalies": [
    {
      "anomaly_type": "error_spike",
      "severity": "high",
      "description": "8 HTTP 5xx responses detected in the last 50 observations (16.0% error rate).",
      "detected_at": "2026-10-11T16:05:00.123Z",
      "metrics": {
        "error_count": 8,
        "window_size": 50,
        "error_rate": 0.16,
        "threshold": 5,
        "window_start": "2026-10-11T16:04:55.000Z",
        "window_end": "2026-10-11T16:05:00.000Z"
      }
    }
  ],
  "observation_count": 50,
  "window_size": 50,
  "has_sufficient_baseline": true,
  "thresholds": {
    "error_spike_threshold": 5,
    "error_spike_window": 50,
    "latency_threshold_ms": 2000.0,
    "zscore_threshold": 3.0,
    "min_baseline_size": 30
  }
}
```

**Example response (healthy traffic):**
```json
{
  "anomalies": [],
  "observation_count": 12,
  "window_size": 50,
  "has_sufficient_baseline": false,
  "thresholds": { "..." : "..." }
}
```

**Curl example:**
```bash
curl http://localhost:8000/api/anomalies | python3 -m json.tool
```

### Limitations of In-Memory Observations

* **Restarts reset history** — the buffer is process-local. A container
  restart or rolling deployment discards all observations. Alerts will not
  fire until the buffer is repopulated.
* **Single-process only** — the in-memory buffer is not shared across
  multiple application replicas. Each replica detects anomalies
  independently.
* **No persistence** — observations are not written to Loki or any other
  store. Use the Loki/Grafana stack (Phase 3) for durable log querying and
  alerting across restarts.
* **Z-score warm-up** — z-score detection requires at least
  `min_baseline_size` (default 30) observations before it activates. On
  a fresh start, only the `error_spike` and `high_latency` rules fire.
* **Single-spike vs. sustained spike** — one isolated HTTP 500 will not
  trigger an `error_spike` alert. The count must reach
  `error_spike_threshold` (default 5) within the most recent
  `error_spike_window` (default 50) observations.
