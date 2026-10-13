# SETUP — run this project on any laptop (Windows)

Takes ~15 minutes. Do the steps in order; stop at the first step that
fails and fix it before continuing.

## 1. Install prerequisites

| Tool | Needed for | Get it |
|---|---|---|
| Git | cloning the repo | https://git-scm.com/download/win |
| Python 3.11+ (tick "Add to PATH") | tests + local run | https://www.python.org/downloads/ |
| Docker Desktop | full stack (Step 4 of demo) | https://www.docker.com/products/docker-desktop (start it after install) |
| minikube + kubectl | Kubernetes demo (optional) | `winget install minikube` / https://kubernetes.io/docs/tasks/tools/ |

Verify (PowerShell):

```powershell
git --version
python --version        # must be 3.11 or newer
docker --version        # only if doing the Docker demo
```

## 2. Get the code and dependencies

```powershell
git clone https://github.com/adi45264/ai-log-anomaly-devops.git
cd ai-log-anomaly-devops
pip install -r app/requirements.txt
```

That one file installs everything both apps need:
`fastapi` (web framework), `uvicorn[standard]` (server),
`pytest` (tests), `httpx` (test HTTP client). No database, no ML
libraries, no other setup. The `log_platform/` app reuses the same
packages (`log_platform/requirements.txt` is identical).

## 3. Prove it works (no Docker needed)

```powershell
pytest -v
# expect: 66 passed (18 shop + 48 platform incl. end-to-end)
```

## 4. Run both apps locally (two terminals)

```powershell
# terminal 1
uvicorn app.main:app --port 8000
# terminal 2
uvicorn log_platform.main:app --port 8001
```

Open `http://localhost:8000/` (shop) and `http://localhost:8001/`
(platform). If a page shows `{"detail":"Not Found"}`, that terminal is
running old code: press Ctrl+C there and rerun its command.

## 5. Full stack with Docker (optional)

```powershell
docker-compose up -d --build
curl.exe http://localhost:8000/api/health
curl.exe http://localhost:8001/health
# Grafana: http://localhost:3000 -> Dashboards -> "AI Log Anomaly DevOps"
docker-compose down   # cleanup
```

Note: PowerShell's `curl` is an alias for `Invoke-WebRequest` — use
`curl.exe` (real curl) or `Invoke-RestMethod` instead.

## 6. Kubernetes with minikube (optional)

```powershell
minikube start --driver=docker
docker build -t ai-log-anomaly-devops:latest .
docker build -f Dockerfile.platform -t ai-log-platform:latest .
minikube image load ai-log-anomaly-devops:latest
minikube image load ai-log-platform:latest
kubectl apply -f k8s/
kubectl get pods -w   # wait for both Running, then Ctrl+C
kubectl port-forward svc/demo-app 8000:8000
# new terminal:
kubectl port-forward svc/log-platform 8001:8001
```

Cleanup: `kubectl delete -f k8s/` then `minikube stop`.

## Troubleshooting

| Symptom | Cause → fix |
|---|---|
| `{"detail":"Not Found"}` on `/` | stale server → restart uvicorn / `docker-compose up -d --build` / `kubectl rollout restart deploy/demo-app deploy/log-platform`, then hard-refresh (Ctrl+Shift+R) |
| `curl -X` errors in PowerShell | `curl` alias → use `curl.exe` or `Invoke-RestMethod` |
| port-forward `bind: Only one usage…` | port already taken (compose still up?) → `docker-compose down` or forward to another local port (`8002:8000`) |
| pods `ErrImagePull`/`ImagePullBackOff` | cluster can't see local images → redo the two `minikube image load` commands, then `kubectl delete pod -l app=demo-app` (+ log-platform) |
| Grafana panels "No data" | no logs in time range → generate traffic first, or widen range to 1h |
| `pytest` fails on a fresh clone | wrong Python or missing deps → `python --version`, re-run the `pip install` from step 2 |
