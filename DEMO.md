# DEMO script — AI Log Anomaly DevOps (≈10 minutes)

Audience: anyone watching the demo. Prep: finish `SETUP.md` steps 1–4
(or step 5 for the Docker version). Open these side by side:
shop `http://localhost:8000/`, platform `http://localhost:8001/`,
Grafana `http://localhost:3000` (Docker run only).

## Act 1 — healthy shopping (2 min)

Say: "This is SwiftCart, a normal online store."
1. Search "mouse", filter Audio, sort by price — catalog reacts.
2. Add Laptop + Headphones → cart badge counts, free-shipping bar moves.
3. Checkout → name + email → Pay → success screen with `SWC-000xx` reference.
4. Orders tab → click the row → timeline shows Placed → Paid.
5. Platform tab → "no anomalies — traffic is healthy." Grafana error-rate flat.

Point: every click is a real API call emitting structured JSON logs.

## Act 2 — break it (4 min)

Say: "Now I simulate a database outage, like a real on-call scenario."
1. Shop → expand Test controls → **Database outage** (red badge).
2. Checkout → Pay → red **DECLINED**, `database timeout`. Repeat ~5–6 times
   (the shop auto-forwards each failure to the platform — no manual step).
3. Platform → anomalies table fills with **`error_spike`** (high severity)
   and **`high_latency`** entries, with evidence metrics.
4. Platform → **Snapshot into incident** → Incident #1 card with severity
   and plain-English summary. Expand Evidence to show raw anomalies.
5. Grafana → error-rate panel spikes, incident counter increments.

Point: failure → detection → human-readable incident, all in seconds.

## Act 3 — recover + tour (2 min)

1. Shop → **Recover** → checkout → approved fast. Order flips to PAID.
2. Show a 402: start **Payment outage**, pay → instantly declined "card
   declined". Show a slow approval: **Latency spike**, pay → approved
   after ~3–5s with big latency number → platform `high_latency`.
3. Cancel an unpaid order from its detail drawer (paid orders correctly
   refuse with 409). Toggle dark mode (◐) for effect.

## If something misbehaves live

- Stale page showing old UI → hard-refresh (Ctrl+Shift+R); if the API
  itself is old, restart that server/container (see SETUP.md).
- Payment approvals feel instant in tests but slow live → expected:
  tests patch `time.sleep`; live latency simulation is real seconds.
- Grafana empty → generate traffic first, widen time range to 1h.
- Port already in use → old stack still up: `docker-compose down` or use
  alternate local ports for port-forwarding.

## One-line proof (no browser)

```powershell
pytest -v   # 66 passed: shop, platform, and the full failure→incident E2E
```
