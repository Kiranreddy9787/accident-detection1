import io
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from app import create_app
from video_processing import extract_frames


class VideoUploadTests(unittest.TestCase):
    def setUp(self):
        self.test_id = uuid.uuid4().hex
        self.video_directory = Path.cwd() / "videos"
        self.frame_directory = Path.cwd() / "snapshots" / f"_test_frames_{self.test_id}"
        self.created_files = []
        self.app = create_app()
        self.app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
            VIDEO_UPLOAD_FOLDER=str(self.video_directory),
            SNAPSHOT_FOLDER=str(Path.cwd() / "snapshots"),
        )
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = 1
            session["user_name"] = "Test Admin"
            session["user_role"] = "admin"

    def tearDown(self):
        for file_path in self.created_files:
            file_path.unlink(missing_ok=True)
        if self.frame_directory.exists():
            for frame_path in self.frame_directory.iterdir():
                frame_path.unlink()
            self.frame_directory.rmdir()

    def _sample_avi(self) -> Path:
        path = self.video_directory / f"_test_source_{self.test_id}.avi"
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (32, 24))
        self.assertTrue(writer.isOpened(), "OpenCV test video writer did not open")
        for value in (0, 80, 160):
            writer.write(np.full((24, 32, 3), value, dtype=np.uint8))
        writer.release()
        self.created_files.append(path)
        return path

    def test_rejects_an_invalid_extension(self):
        response = self.client.post(
            "/upload-video",
            data={"video": (io.BytesIO(b"not a video"), "traffic.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Use an MP4, MOV, M4V, WebM, or AVI video file.", response.data)

    def test_rejects_corrupt_video_content_with_an_allowed_extension(self):
        response = self.client.post(
            "/upload-video",
            data={"video": (io.BytesIO(b"this is not a video"), "traffic.avi")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"OpenCV could not open this file as a video", response.data)

    def test_rejects_a_video_larger_than_the_configured_file_limit(self):
        sample = self._sample_avi()
        with patch("app.MAX_VIDEO_BYTES", 32):
            response = self.client.post(
                "/upload-video",
                data={"video": (io.BytesIO(sample.read_bytes()), "traffic.avi")},
                content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"exceeds the 500 MB file size limit", response.data)

    def test_upload_preview_playback_and_frame_extraction(self):
        sample = self._sample_avi()
        response = self.client.post(
            "/upload-video",
            data={"video": (io.BytesIO(sample.read_bytes()), "../../traffic video.avi")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

        with self.client.session_transaction() as session:
            selected_video = session["uploaded_video"]
        self.assertNotIn("..", selected_video["filename"])
        uploaded_path = Path(self.app.config["VIDEO_UPLOAD_FOLDER"]) / selected_video["filename"]
        self.created_files.append(uploaded_path)
        self.assertTrue(uploaded_path.is_file())

        dashboard = self.client.get("/")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn(b"Uploaded Video Preview", dashboard.data)
        self.assertIn(b'type="video/x-msvideo"', dashboard.data)
        playback = self.client.get(f"/videos/{selected_video['filename']}")
        self.assertEqual(playback.status_code, 200)
        self.assertGreater(len(playback.data), 0)
        playback.close()

        frames = extract_frames(uploaded_path, self.frame_directory, every_n_frames=2)
        self.assertEqual(len(frames), 2)
        self.assertTrue(all(frame.is_file() for frame in frames))


if __name__ == "__main__":
    unittest.main()
