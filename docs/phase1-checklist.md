# Phase 1 — PLAN: Setup Checklist

## Step 1 — Push these files to GitHub
```powershell
cd c:\Users\Aditya\ai-log-anomaly-devops
git add requirements.md docs/ scripts/
git commit -m "Phase 1: requirements and architecture docs (#1,#2)"
git push origin main
```

## Step 2 — Generate architecture.png
Easiest: open https://mermaid.live, paste the mermaid block from
`docs/architecture.md`, and export PNG as `architecture.png` at the repo root.
Then:
```powershell
git add architecture.png
git commit -m "Phase 1: add architecture diagram (#2)"
git push
```

## Step 3 — Create the 15 issues
```powershell
gh auth login   # if not authenticated
powershell -ExecutionPolicy Bypass -File scripts/create_issues.ps1
```

## Step 4 — Create the Project board
1. Go to https://github.com/users/adi45264/projects → **New project**
2. Name it `ai-log-anomaly-devops`, template: **Basic kanban**
3. Columns: **Backlog | In Progress | Done**
4. Add all 15 issues; move #1 and #2 to **Done**, #3 to **In Progress**
   (shows the lifecycle in motion — good evidence for the Plan stage).

## Evidence checklist (Plan stage)
- [x] requirements.md (issue #1)
- [ ] architecture.png (issue #2) — export from docs/architecture.md
- [ ] 15 GitHub issues — run scripts/create_issues.ps1
- [ ] Project board with issues tracked
