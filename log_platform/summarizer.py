"""Incident summarizer for the log platform.

Groups currently detected anomalies into a single human-readable incident
report. v1 uses a deterministic template (no LLM / network calls) so the
endpoint works offline and tests stay deterministic.
"""

from __future__ import annotations

from typing import Any

_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2}


def build_incident(incident_id: int, anomalies: list[dict[str, Any]], created_at: str) -> dict[str, Any]:
    """Build one incident dict from a list of anomaly dicts.

    Severity is the worst severity among the grouped anomalies.
    """
    types = sorted({a.get("anomaly_type", "unknown") for a in anomalies})
    worst = "low"
    for a in anomalies:
        sev = a.get("severity", "low")
        if _SEVERITY_RANK.get(sev, 0) > _SEVERITY_RANK.get(worst, 0):
            worst = sev
    summary = (
        f"Incident #{incident_id}: {len(anomalies)} anomal"
        f"{'y' if len(anomalies) == 1 else 'ies'} detected "
        f"({', '.join(types)}). Severity: {worst}."
    )
    return {
        "id": incident_id,
        "title": f"Incident #{incident_id} ({', '.join(types)})",
        "severity": worst,
        "summary": summary,
        "anomaly_count": len(anomalies),
        "anomaly_types": types,
        "created_at": created_at,
        "anomalies": anomalies,
    }
