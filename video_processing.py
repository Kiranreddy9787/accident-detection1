"""OpenCV video helpers. This module does not perform accident detection."""

from pathlib import Path
from typing import Any

try:
    import cv2
except ImportError:  # Defer the useful error until video functionality is requested.
    cv2 = None


class VideoProcessingError(ValueError):
    """Raised when OpenCV cannot read a supplied video."""


def _require_cv2():
    global cv2
    if cv2 is None:
        try:
            import cv2 as opencv
        except ImportError as error:
            raise VideoProcessingError(
                "OpenCV is not installed. Run 'python -m pip install opencv-python' and restart the app."
            ) from error
        cv2 = opencv
    return cv2


def read_video_metadata(video_path: str | Path) -> dict[str, Any]:
    """Open a video with OpenCV and return basic, non-detection metadata."""
    opencv = _require_cv2()
    capture = opencv.VideoCapture(str(video_path))
    try:
        if not capture.isOpened():
            raise VideoProcessingError("OpenCV could not open this file as a video.")

        frame_count = int(capture.get(opencv.CAP_PROP_FRAME_COUNT))
        fps = float(capture.get(opencv.CAP_PROP_FPS))
        width = int(capture.get(opencv.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(opencv.CAP_PROP_FRAME_HEIGHT))
        if frame_count < 1 or width < 1 or height < 1:
            raise VideoProcessingError("The video has no readable frames.")

        return {
            "frame_count": frame_count,
            "fps": round(fps, 2) if fps > 0 else None,
            "width": width,
            "height": height,
            "duration_seconds": round(frame_count / fps, 2) if fps > 0 else None,
        }
    finally:
        capture.release()


def extract_frames(
    video_path: str | Path,
    output_directory: str | Path,
    every_n_frames: int = 30,
    max_frames: int | None = None,
) -> list[Path]:
    """Save selected video frames as JPEG files and return their paths.

    This is a general OpenCV utility for later processing; it does not analyse
    frames or detect accidents.
    """
    if every_n_frames < 1:
        raise ValueError("every_n_frames must be at least 1.")
    if max_frames is not None and max_frames < 1:
        raise ValueError("max_frames must be at least 1 when provided.")

    read_video_metadata(video_path)  # Validate before writing any frame files.
    destination = Path(output_directory)
    destination.mkdir(parents=True, exist_ok=True)
    opencv = _require_cv2()
    capture = opencv.VideoCapture(str(video_path))
    saved_frames: list[Path] = []
    frame_number = 0
    try:
        while True:
            has_frame, frame = capture.read()
            if not has_frame:
                break
            if frame_number % every_n_frames == 0:
                frame_path = destination / f"frame_{frame_number:06d}.jpg"
                if not opencv.imwrite(str(frame_path), frame):
                    raise VideoProcessingError("OpenCV could not write an extracted frame.")
                saved_frames.append(frame_path)
                if max_frames is not None and len(saved_frames) >= max_frames:
                    break
            frame_number += 1
    finally:
        capture.release()
    return saved_frames
