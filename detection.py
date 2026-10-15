"""YOLO detection, simple object tracking, and demonstration incident rules."""

from pathlib import Path
import math
from typing import Any

from incident_rules import assess_possible_incident

try:
    import cv2
except ImportError:  # Keep Flask importable so the route can report the missing dependency.
    cv2 = None


MODEL_FILENAME = "yolov8n.pt"
TARGET_CLASSES = {0: "person", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
BOX_COLORS = {
    "person": (66, 189, 255),
    "car": (98, 230, 136),
    "motorcycle": (255, 180, 67),
    "bus": (238, 103, 103),
    "truck": (184, 116, 255),
}


class DetectionError(RuntimeError):
    """Raised when the YOLO model or video processing cannot be used."""


def _require_cv2():
    """Return OpenCV or raise a route-friendly dependency error."""
    global cv2
    if cv2 is None:
        try:
            import cv2 as opencv
        except ImportError as error:
            raise DetectionError(
                "OpenCV is not installed. Run 'python -m pip install opencv-python' and restart the app."
            ) from error
        cv2 = opencv
    return cv2


def get_model(models_directory: str | Path):
    """Load YOLOv8 nano, downloading it to ``models/`` on first use."""
    try:
        from ultralytics import YOLO
        from ultralytics.utils.downloads import attempt_download_asset
    except Exception as error:  # Import can fail if the package is not installed or cannot initialize.
        raise DetectionError(
            "Ultralytics YOLO is unavailable. Run 'python -m pip install -r requirements.txt' "
            "and restart the app."
        ) from error

    model_path = Path(models_directory) / MODEL_FILENAME
    model_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Download the official pretrained asset directly into this project if
        # it is not already present, then load that local copy.
        weights_path = attempt_download_asset(str(model_path))
        if not Path(weights_path).is_file():
            raise FileNotFoundError(f"Pretrained weights were not found at {weights_path}")
        return YOLO(weights_path)
    except Exception as error:
        raise DetectionError(
            "Could not load pretrained YOLOv8n weights. Confirm models/yolov8n.pt exists, "
            "or connect to the internet for Ultralytics to download it."
        ) from error


def _box_iou(first: tuple[int, int, int, int], second: tuple[int, int, int, int]) -> float:
    """Calculate intersection over union for two xyxy boxes."""
    x1, y1 = max(first[0], second[0]), max(first[1], second[1])
    x2, y2 = min(first[2], second[2]), min(first[3], second[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    first_area = max(0, first[2] - first[0]) * max(0, first[3] - first[1])
    second_area = max(0, second[2] - second[0]) * max(0, second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union else 0.0


class _ObjectTracker:
    """Associate same-class detections between frames without extra packages."""

    def __init__(self, minimum_iou: float = 0.25, max_gap: int = 30):
        self.minimum_iou = minimum_iou
        self.max_gap = max_gap
        self.frame_index = 0
        self.next_id = 1
        self.active: dict[int, tuple[int, tuple[int, int, int, int], int]] = {}
        self.history: dict[int, list[tuple[int, int, tuple[int, int, int, int]]]] = {}

    def update(self, detections: list[tuple[int, tuple[int, int, int, int]]]) -> list[int]:
        """Return one stable ID per detection using greedy best-IoU matching."""
        self.frame_index += 1
        self.active = {
            track_id: track for track_id, track in self.active.items()
            if self.frame_index - track[2] <= self.max_gap
        }
        candidates = []
        for detection_index, (class_id, box) in enumerate(detections):
            for track_id, (track_class, previous_box, _last_seen) in self.active.items():
                if class_id != track_class:
                    continue
                overlap = _box_iou(box, previous_box)
                if overlap >= self.minimum_iou:
                    candidates.append((overlap, detection_index, track_id))

        assigned_detections: set[int] = set()
        assigned_tracks: set[int] = set()
        track_ids = [0] * len(detections)
        for _overlap, detection_index, track_id in sorted(candidates, reverse=True):
            if detection_index in assigned_detections or track_id in assigned_tracks:
                continue
            class_id, box = detections[detection_index]
            self.active[track_id] = (class_id, box, self.frame_index)
            track_ids[detection_index] = track_id
            assigned_detections.add(detection_index)
            assigned_tracks.add(track_id)

        for detection_index, (class_id, box) in enumerate(detections):
            if detection_index in assigned_detections:
                continue
            track_id = self.next_id
            self.next_id += 1
            self.active[track_id] = (class_id, box, self.frame_index)
            track_ids[detection_index] = track_id
        for detection_index, (class_id, box) in enumerate(detections):
            track_id = track_ids[detection_index]
            self.history.setdefault(track_id, []).append((self.frame_index, class_id, box))
        return track_ids


def _find_movement_incident(tracker: _ObjectTracker, fps: float, width: int, height: int) -> dict[str, Any]:
    """Assess track histories for a possible, never confirmed, incident."""
    return assess_possible_incident(tracker.history, fps, width, height)


def _draw_detections(frame, result, tracker: _ObjectTracker) -> tuple[int, float, set[tuple[int, int]]]:
    """Draw one frame and return raw detections, confidence, and observed tracks."""
    opencv = _require_cv2()
    detection_count = 0
    confidence_total = 0.0
    tracked_objects: set[tuple[int, int]] = set()
    boxes = result.boxes
    if boxes is None:
        tracker.update([])
        return detection_count, confidence_total, tracked_objects

    class_names = result.names
    valid_boxes = []
    detections = []
    for box in boxes:
        class_id = int(box.cls[0].item())
        if class_id not in TARGET_CLASSES:
            continue
        coordinates = tuple(int(value) for value in box.xyxy[0].tolist())
        valid_boxes.append((box, class_id, coordinates))
        detections.append((class_id, coordinates))

    track_ids = tracker.update(detections)
    for (box, class_id, (x1, y1, x2, y2)), track_id in zip(valid_boxes, track_ids):
        label_name = class_names[class_id]
        confidence = float(box.conf[0].item())
        color = BOX_COLORS.get(label_name, (0, 220, 255))
        opencv.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        label = f"{label_name} #{track_id} {confidence:.0%}"
        (label_width, label_height), baseline = opencv.getTextSize(label, opencv.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        label_top = max(y1, label_height + baseline + 5)
        opencv.rectangle(frame, (x1, label_top - label_height - baseline - 5), (x1 + label_width + 8, label_top), color, -1)
        opencv.putText(frame, label, (x1 + 4, label_top - baseline - 3), opencv.FONT_HERSHEY_SIMPLEX, 0.55, (20, 30, 40), 2)
        detection_count += 1
        tracked_objects.add((class_id, track_id))
        confidence_total += confidence
    return detection_count, confidence_total, tracked_objects


def process_video(
    input_path: str | Path,
    output_path: str | Path,
    models_directory: str | Path,
    confidence: float = 0.35,
    image_size: int = 640,
    progress_callback=None,
) -> dict[str, Any]:
    """Detect people and road vehicles, writing a browser-friendly WebM copy.

    Inference uses the YOLO nano model, CPU device, filtered target classes, and
    640px input size to keep the college-project demonstration practical on CPU.
    """
    source = Path(input_path)
    destination = Path(output_path)
    if not source.is_file():
        raise DetectionError("The uploaded source video could not be found.")
    if not 0 < confidence <= 1:
        raise ValueError("confidence must be between 0 and 1.")

    opencv = _require_cv2()
    capture = opencv.VideoCapture(str(source))
    if not capture.isOpened():
        capture.release()
        raise DetectionError("OpenCV could not open the uploaded video.")

    fps = float(capture.get(opencv.CAP_PROP_FPS))
    if not math.isfinite(fps) or fps <= 0:
        fps = 25.0
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = max(0, int(capture.get(opencv.CAP_PROP_FRAME_COUNT)))
    if width < 1 or height < 1:
        capture.release()
        raise DetectionError("The uploaded video has invalid dimensions.")

    # Reject empty/corrupt clips before loading model weights or creating output.
    has_readable_frame, first_frame = capture.read()
    if not has_readable_frame or first_frame is None:
        capture.release()
        raise DetectionError("The uploaded video contains no readable frames.")
    try:
        model = get_model(models_directory)
    except DetectionError:
        capture.release()
        raise

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = destination.with_suffix(".processing.webm")
    temporary_output.unlink(missing_ok=True)
    writer = opencv.VideoWriter(str(temporary_output), opencv.VideoWriter_fourcc(*"VP80"), fps, (width, height))
    if not writer.isOpened():
        capture.release()
        writer.release()
        temporary_output.unlink(missing_ok=True)
        raise DetectionError("OpenCV could not create the browser-compatible WebM video.")

    frame_count = 0
    frame_detection_count = 0
    tracked_objects: set[tuple[int, int]] = set()
    tracker = _ObjectTracker()
    confidence_total = 0.0
    processing_error = None
    try:
        if progress_callback:
            progress_callback(0, total_frames)
        frame = first_frame
        while True:
            if frame is None:
                break
            results = model.predict(
                frame,
                conf=confidence,
                classes=list(TARGET_CLASSES),
                imgsz=image_size,
                device="cpu",
                verbose=False,
            )
            frame_detections, frame_confidence, frame_tracks = _draw_detections(frame, results[0], tracker)
            frame_detection_count += frame_detections
            tracked_objects.update(frame_tracks)
            confidence_total += frame_confidence
            writer.write(frame)
            frame_count += 1
            if progress_callback:
                progress_callback(frame_count, total_frames)
            has_frame, frame = capture.read()
            if not has_frame:
                frame = None
    except Exception as error:
        processing_error = error
    finally:
        capture.release()
        writer.release()

    if processing_error is not None:
        temporary_output.unlink(missing_ok=True)
        raise DetectionError(f"YOLO could not process the video: {processing_error}") from processing_error
    if frame_count == 0:
        temporary_output.unlink(missing_ok=True)
        raise DetectionError("The uploaded video contains no readable frames.")
    if not temporary_output.is_file() or temporary_output.stat().st_size == 0:
        temporary_output.unlink(missing_ok=True)
        raise DetectionError("OpenCV did not produce a playable annotated video file.")
    temporary_output.replace(destination)
    object_counts = {name: 0 for name in TARGET_CLASSES.values()}
    for class_id, _track_id in tracked_objects:
        object_counts[TARGET_CLASSES[class_id]] += 1
    unique_object_count = sum(object_counts.values())
    movement_incident = _find_movement_incident(tracker, float(fps), width, height)
    return {
        "frame_count": frame_count,
        "fps": round(float(fps), 2),
        "width": width,
        "height": height,
        "detection_count": unique_object_count,
        "frame_detection_count": frame_detection_count,
        "object_counts": object_counts,
        "movement_incident": movement_incident,
        "average_detection_confidence": round(confidence_total / frame_detection_count, 4) if frame_detection_count else 0.0,
    }
