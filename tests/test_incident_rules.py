import unittest

from incident_rules import assess_possible_incident, format_video_timestamp


def moving_box(center_x, center_y=100, width=24, height=18):
    return (
        round(center_x - width / 2), round(center_y - height / 2),
        round(center_x + width / 2), round(center_y + height / 2),
    )


class PossibleIncidentRuleTests(unittest.TestCase):
    def test_approach_followed_by_vehicle_slowdown_flags_manual_review(self):
        observations = {1: [], 2: []}
        for frame in range(1, 31):
            first_center = 40 + 4 * min(frame, 15) + 0.3 * max(0, frame - 15)
            observations[1].append((frame, 2, moving_box(first_center)))
            observations[2].append((frame, 5, moving_box(138)))

        result = assess_possible_incident(observations, fps=25, width=400, height=200)

        self.assertTrue(result["possible_incident"])
        self.assertEqual(result["involved_objects"], [
            {"track_id": 1, "class_name": "car"},
            {"track_id": 2, "class_name": "bus"},
        ])
        self.assertIn("Possible incident — manual review required", result["message"])
        self.assertIn("Video time", result["message"])
        self.assertIn("car #1", result["message"])
        self.assertIn("bus #2", result["message"])
        self.assertIn("video_timestamp", result)

    def test_overlapping_stationary_boxes_alone_do_not_flag(self):
        observations = {1: [], 2: []}
        for frame in range(1, 31):
            observations[1].append((frame, 2, moving_box(100)))
            observations[2].append((frame, 3, moving_box(105)))

        result = assess_possible_incident(observations, fps=25, width=400, height=200)

        self.assertFalse(result["possible_incident"])
        self.assertEqual(result["track_ids"], [])

    def test_motion_change_without_approach_or_second_vehicle_change_does_not_flag(self):
        observations = {1: [], 2: []}
        for frame in range(1, 31):
            center = 30 + 4 * min(frame, 15) + 0.3 * max(0, frame - 15)
            observations[1].append((frame, 2, moving_box(center)))
            observations[2].append((frame, 0, moving_box(center + 35)))

        result = assess_possible_incident(observations, fps=25, width=400, height=200)

        self.assertFalse(result["possible_incident"])

    def test_video_timestamp_format(self):
        self.assertEqual(format_video_timestamp(3661.234), "01:01:01.234")


if __name__ == "__main__":
    unittest.main()
