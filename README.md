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
