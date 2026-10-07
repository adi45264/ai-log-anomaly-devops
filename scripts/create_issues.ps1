# Creates GitHub Issues #1-#15 for ai-log-anomaly-devops
# Prereq: gh CLI installed and authenticated (gh auth login), repo pushed to GitHub.
# Run from repo root:  powershell -ExecutionPolicy Bypass -File scripts/create_issues.ps1

$repo = "adi45264/ai-log-anomaly-devops"

# Create labels first (ignore errors if they exist)
gh label create "phase:plan" --repo $repo --color 0E8A16 --description "Planning phase" 2>$null
gh label create "phase:build" --repo $repo --color 5319E7 --description "Build/deploy phase" 2>$null
gh label create "phase:operate" --repo $repo --color D93F0B --description "Operations phase" 2>$null

$issues = @(
    @{ Title = "Project requirements"; Body = "Define functional + non-functional requirements, tech stack, deliverables and acceptance criteria. Deliverable: requirements.md"; Labels = "phase:plan" },
    @{ Title = "System architecture"; Body = "Design high-level architecture (FastAPI app, anomaly engine, incident summarizer, centralized logging, dashboard). Deliverable: architecture.png"; Labels = "phase:plan" },
    @{ Title = "Create FastAPI application"; Body = "Build FastAPI app with /health and /logs endpoints. Deliverable: app/ + running server"; Labels = "phase:build" },
    @{ Title = "Implement structured logging"; Body = "Emit structured JSON logs for every request and internal event. Deliverable: logging middleware/config"; Labels = "phase:build" },
    @{ Title = "Dockerize application"; Body = "Write Dockerfile + docker-compose for local stack. Deliverable: working container build"; Labels = "phase:build" },
    @{ Title = "Create automated tests"; Body = "pytest unit + API tests covering endpoints and anomaly logic. Deliverable: green test suite"; Labels = "phase:build" },
    @{ Title = "Create CI pipeline"; Body = "GitHub Actions: lint, test, build Docker image on push/PR. Deliverable: green CI on main"; Labels = "phase:build" },
    @{ Title = "Deploy application to Kubernetes"; Body = "K8s manifests (Deployment, Service, ConfigMap); deploy to minikube/kind. Deliverable: running pods + screenshot"; Labels = "phase:operate" },
    @{ Title = "Configure centralized logging"; Body = "Ship container logs to Loki/ELK; query from Grafana. Deliverable: aggregated logs visible"; Labels = "phase:operate" },
    @{ Title = "Implement anomaly detection"; Body = "Rule-based + statistical detection on ingested logs; GET /anomalies endpoint. Deliverable: anomalies reported"; Labels = "phase:operate" },
    @{ Title = "Implement incident summarization"; Body = "Group correlated anomalies into incidents with AI/templated summary. Deliverable: incident report endpoint"; Labels = "phase:operate" },
    @{ Title = "Monitoring dashboard"; Body = "Grafana dashboard: log volume, error rate, anomaly count, pod health. Deliverable: dashboard screenshot"; Labels = "phase:operate" },
    @{ Title = "Failure simulation"; Body = "Script/endpoint to generate synthetic error floods for validating detection. Deliverable: reproducible failure"; Labels = "phase:operate" },
    @{ Title = "End-to-end testing"; Body = "E2E test: log ingestion -> anomaly detected -> incident summarized under simulated failure. Deliverable: passing E2E run"; Labels = "phase:operate" },
    @{ Title = "Documentation"; Body = "README with setup, architecture, lifecycle mapping, screenshots, and runbook. Deliverable: complete docs"; Labels = "phase:plan" }
)

foreach ($i in $issues) {
    Write-Host "Creating: $($i.Title)"
    gh issue create --repo $repo --title $i.Title --body $i.Body --label $i.Labels
}

# Set up a Project board (v2) and add all issues
Write-Host "`nCreating Project board..."
gh project create --title "ai-log-anomaly-devops" --owner adi45264 --format json
Write-Host "Add issues to the board at: https://github.com/users/adi45264/projects"
Write-Host "Suggested columns: Backlog | In Progress | Done"
