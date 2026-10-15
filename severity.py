"""Explainable demonstration-only severity estimation.

This heuristic is not medically, legally, or officially validated. It is a
transparent way to rank a model-detected scene for a college project.
"""

from typing import Any


def _score_range(value: float, maximum: float, weight: float) -> float:
    return min(max(value, 0.0), maximum) / maximum * weight


def estimate_severity(
    vehicle_detections: int,
    person_detections: int,
    collision_indicator: float,
    detection_confidence: float,
) -> dict[str, Any]:
    """Return LOW, MEDIUM, or HIGH using explicit normalized video signals.

    Score = vehicle evidence (0-30) + person evidence (0-15) + visual incident
    indicator (0-35) + YOLO confidence (0-20). Vehicle/person figures are unique
    tracker estimates, not verified identities. ``collision_indicator`` is a
    model or movement-rule signal, not proof of a physical collision.
    """
    if vehicle_detections < 0 or person_detections < 0:
        raise ValueError("Detection counts cannot be negative.")
    if not 0 <= collision_indicator <= 1 or not 0 <= detection_confidence <= 1:
        raise ValueError("Collision indicator and detection confidence must be between 0 and 1.")

    vehicle_score = _score_range(vehicle_detections, maximum=5, weight=30)
    person_score = _score_range(person_detections, maximum=5, weight=15)
    collision_score = collision_indicator * 35
    confidence_score = detection_confidence * 20
    severity_score = round(vehicle_score + person_score + collision_score + confidence_score, 1)
    severity = "LOW" if severity_score < 35 else "MEDIUM" if severity_score < 65 else "HIGH"

    return {
        "severity": severity,
        "severity_score": severity_score,
        "factor_breakdown": {
            "vehicle_evidence": round(vehicle_score, 1),
            "person_evidence": round(person_score, 1),
            "visual_incident_indicator": round(collision_score, 1),
            "detection_confidence": round(confidence_score, 1),
        },
        "explanation": (
            f"{vehicle_detections} vehicle detections, {person_detections} person detections, "
            f"incident signal {collision_indicator:.0%}, and mean YOLO confidence "
            f"{detection_confidence:.0%}. This is a demonstration-only video heuristic, not a "
            "medical or official severity assessment."
        ),
    }
