"""Training-free movement rules for unverified possible-incident warnings."""

from __future__ import annotations

from typing import Any


VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
PERSON_CLASS = 0


def _center(box: tuple[int, int, int, int]) -> tuple[float, float]:
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def _distance(first: tuple[float, float], second: tuple[float, float]) -> float:
    return ((first[0] - second[0]) ** 2 + (first[1] - second[1]) ** 2) ** 0.5


def _iou(first: tuple[int, int, int, int], second: tuple[int, int, int, int]) -> float:
    x1, y1 = max(first[0], second[0]), max(first[1], second[1])
    x2, y2 = min(first[2], second[2]), min(first[3], second[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    first_area = max(0, first[2] - first[0]) * max(0, first[3] - first[1])
    second_area = max(0, second[2] - second[0]) * max(0, second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union else 0.0


def _nearest_observation(
    history: dict[int, tuple[int, int, int, int]], frame: int, tolerance: int
) -> tuple[int, int, int, int] | None:
    available = [observed for observed in history if abs(observed - frame) <= tolerance]
    if not available:
        return None
    return history[min(available, key=lambda observed: abs(observed - frame))]


def _motion_change(
    history: dict[int, tuple[int, int, int, int]], frame: int, gap: int, tolerance: int, min_motion: float
) -> tuple[bool, float]:
    prior_box = _nearest_observation(history, frame - gap, tolerance)
    contact_box = _nearest_observation(history, frame, tolerance)
    after_box = _nearest_observation(history, frame + gap, tolerance)
    if prior_box is None or contact_box is None or after_box is None:
        return False, 0.0

    prior, contact, after = _center(prior_box), _center(contact_box), _center(after_box)
    before_vector = (contact[0] - prior[0], contact[1] - prior[1])
    after_vector = (after[0] - contact[0], after[1] - contact[1])
    before_speed = _distance((0.0, 0.0), before_vector)
    after_speed = _distance((0.0, 0.0), after_vector)
    if before_speed < min_motion:
        return False, before_speed

    dot = before_vector[0] * after_vector[0] + before_vector[1] * after_vector[1]
    reversal = dot / max(before_speed * after_speed, 1.0) < -0.25
    abrupt_slowdown = after_speed <= before_speed * 0.4
    return abrupt_slowdown or reversal, before_speed


def format_video_timestamp(seconds: float) -> str:
    """Format clip-relative seconds as HH:MM:SS.mmm."""
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"


def assess_possible_incident(
    observations: dict[int, list[tuple[int, int, tuple[int, int, int, int]]]],
    fps: float,
    width: int,
    height: int,
) -> dict[str, Any]:
    """Flag suspicious vehicle motion near another tracked road user.

    A flag requires proximity, a vehicle's abrupt slowdown/reversal, and either
    a decreasing separation before the event or a motion change by both vehicles.
    Box overlap alone is never sufficient.
    """
    no_event = {
        "possible_incident": False,
        "method": "proximity_and_motion_rules",
        "message": "No possible incident signal was flagged. This does not show that the video is accident-free.",
        "signals": [],
        "track_ids": [],
        "involved_objects": [],
    }
    if width < 1 or height < 1 or not observations:
        return no_event

    histories: dict[int, dict[int, tuple[int, int, int, int]]] = {}
    classes: dict[int, int] = {}
    for track_id, items in observations.items():
        if not items:
            continue
        classes[track_id] = items[0][1]
        histories[track_id] = {frame: box for frame, _class_id, box in items}

    diagonal = max((width * width + height * height) ** 0.5, 1.0)
    gap = max(3, round(max(fps, 1.0) * 0.35))
    tolerance = max(1, round(gap * 0.15))
    min_motion = diagonal * 0.012
    min_approach = diagonal * 0.003
    candidates = []
    track_ids = list(histories)

    for first_index, first_id in enumerate(track_ids):
        for second_id in track_ids[first_index + 1:]:
            first_class, second_class = classes[first_id], classes[second_id]
            if first_class not in VEHICLE_CLASSES and second_class not in VEHICLE_CLASSES:
                continue
            common_frames = sorted(set(histories[first_id]) & set(histories[second_id]))
            for frame in common_frames:
                first_box = histories[first_id][frame]
                second_box = histories[second_id][frame]
                first_center, second_center = _center(first_box), _center(second_box)
                current_separation = _distance(first_center, second_center)
                if current_separation > diagonal * 0.11 and _iou(first_box, second_box) < 0.15:
                    continue

                prior_first = _nearest_observation(histories[first_id], frame - gap, tolerance)
                prior_second = _nearest_observation(histories[second_id], frame - gap, tolerance)
                if prior_first is None or prior_second is None:
                    continue
                prior_separation = _distance(_center(prior_first), _center(prior_second))
                approaching = prior_separation - current_separation >= min_approach

                first_changed, first_speed = _motion_change(
                    histories[first_id], frame, gap, tolerance, min_motion
                )
                second_changed, second_speed = _motion_change(
                    histories[second_id], frame, gap, tolerance, min_motion
                )
                changed_vehicles = [
                    track_id for track_id, class_id, changed in (
                        (first_id, first_class, first_changed),
                        (second_id, second_class, second_changed),
                    ) if class_id in VEHICLE_CLASSES and changed
                ]
                both_vehicles_changed = (
                    first_class in VEHICLE_CLASSES and second_class in VEHICLE_CLASSES
                    and first_changed and second_changed
                )
                if not changed_vehicles or not (approaching or both_vehicles_changed):
                    continue

                involved = [
                    {"track_id": track_id, "class_name": VEHICLE_CLASSES.get(class_id, "person")}
                    for track_id, class_id in ((first_id, first_class), (second_id, second_class))
                ]
                changed_labels = [
                    f"{VEHICLE_CLASSES[track_id_class]} #{track_id} changed motion"
                    for track_id, track_id_class, changed in (
                        (first_id, first_class, first_changed),
                        (second_id, second_class, second_changed),
                    ) if track_id_class in VEHICLE_CLASSES and changed
                ]
                seconds = max(0.0, (frame - 1) / max(fps, 1.0))
                timestamp = format_video_timestamp(seconds)
                participant_text = ", ".join(
                    f"{item['class_name']} #{item['track_id']}" for item in involved
                )
                signal_text = "; ".join(changed_labels)
                candidates.append({
                    "possible_incident": True,
                    "method": "proximity_and_motion_rules",
                    "frame_index": frame - 1,
                    "time_seconds": round(seconds, 3),
                    "video_timestamp": timestamp,
                    "track_ids": [first_id, second_id],
                    "involved_objects": involved,
                    "signals": [
                        "tracked objects approached one another",
                        "vehicle showed an abrupt slowdown or direction reversal",
                    ],
                    "rule_score": round(min(0.95, 0.65 + min(max(first_speed, second_speed) / diagonal, 0.2)), 2),
                    "message": (
                        f"Possible incident — manual review required. Video time {timestamp}; "
                        f"involved: {participant_text}. Motion evidence: {signal_text}."
                    ),
                    "_rank": int(approaching) + len(changed_vehicles),
                })

    if not candidates:
        return no_event
    result = max(candidates, key=lambda candidate: (candidate["_rank"], candidate["rule_score"]))
    result.pop("_rank", None)
    return result
