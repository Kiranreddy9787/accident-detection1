import unittest
from unittest.mock import patch

from app import create_app


class PossibleIncidentAlertIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = 1
            session["user_name"] = "Test Operator"
            session["user_role"] = "operator"
            session["uploaded_video"] = {
                "filename": "integration-check.mp4",
                "original_name": "traffic-sample.mp4",
                "frame_count": 100,
                "width": 400,
                "height": 200,
                "duration_seconds": 4.0,
            }

    @patch("app.db.get_active_email_contacts")
    @patch("app.db.log_notification_attempt")
    @patch("app.db.create_alert", return_value=81)
    @patch("app.db.save_accident_event_from_video", return_value=42)
    @patch("app.db.find_recent_accident_event", return_value=None)
    @patch("app.capture_accident_snapshot", return_value={
        "filename": "incident-test.jpg", "captured_at": "2026-10-15T12:00:00", "frame_index": 60,
    })
    @patch("app.process_video")
    def test_dashboard_alert_has_video_time_tracks_and_no_external_delivery(
        self, process_video, capture_snapshot, _find_event, _save_event, _create_alert,
        _log_attempt, get_contacts,
    ):
        process_video.return_value = {
            "frame_count": 100,
            "fps": 25.0,
            "width": 400,
            "height": 200,
            "detection_count": 2,
            "object_counts": {"car": 1, "bus": 1, "motorcycle": 0, "truck": 0, "person": 0},
            "average_detection_confidence": 0.8,
            "movement_incident": {
                "possible_incident": True,
                "frame_index": 60,
                "time_seconds": 2.4,
                "video_timestamp": "00:00:02.400",
                "track_ids": [3, 8],
                "involved_objects": [
                    {"track_id": 3, "class_name": "car"},
                    {"track_id": 8, "class_name": "bus"},
                ],
                "signals": ["approach", "abrupt vehicle slowdown"],
                "rule_score": 0.8,
                "message": "Possible incident — manual review required. Video time 00:00:02.400; involved: car #3, bus #8.",
            },
        }

        response = self.client.post("/process-video")
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as session:
            classification = session["accident_classification"]
            alert = session["current_alert"]
        self.assertEqual(classification["label"], "Possible incident — manual review required")
        self.assertIn("00:00:02.400", alert["message"])
        self.assertIn("car #3", alert["message"])
        self.assertIn("bus #8", alert["message"])
        get_contacts.assert_not_called()


if __name__ == "__main__":
    unittest.main()
