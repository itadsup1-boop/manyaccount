import os
import tempfile
import unittest

from shared.core.experiment_manager import (
    ExperimentManager,
    apply_experiment_metadata,
    assign_experiment,
    evaluate_experiment,
    normalize_experiment,
    resolve_experiment_assignment,
)


def _experiment(**overrides):
    value = {
        "experiment_id": "hook-result-vs-conflict",
        "name": "Hook result vs conflict",
        "channel_id": "Adsupnews",
        "status": "running",
        "minimum_sample_size": 30,
        "primary_metric": "median_watch_percentage",
        "source_types": ["article", "facebook"],
        "variants": [
            {"name": "control", "changes": {"hook_type": "result"}},
            {"name": "variant", "changes": {"hook_type": "conflict"}},
        ],
    }
    value.update(overrides)
    return value


class ExperimentManagerTests(unittest.TestCase):
    def test_rejects_more_than_one_changed_variable(self):
        experiment = _experiment()
        experiment["variants"][0]["changes"]["music_energy"] = 1

        with self.assertRaisesRegex(
            ValueError,
            "EACH_VARIANT_MUST_CHANGE_EXACTLY_ONE_VARIABLE",
        ):
            normalize_experiment(experiment)

    def test_assignment_is_stable_and_only_stamps_metadata(self):
        first = assign_experiment(_experiment(), "source-123")
        second = assign_experiment(_experiment(), "source-123")
        content = apply_experiment_metadata({"hook_type": "unchanged"}, first)

        self.assertEqual(first, second)
        self.assertIn(first["experiment_variant"], {"control", "variant"})
        self.assertEqual("unchanged", content["hook_type"])
        self.assertEqual(first["experiment_id"], content["experiment_id"])

    def test_registry_prevents_two_running_tests_on_one_channel(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "experiments.json")
            manager = ExperimentManager(path)
            manager.upsert(_experiment())
            another = _experiment(experiment_id="duration-22-vs-28")
            another["variants"] = [
                {"name": "22s", "changes": {"target_duration_seconds": 22}},
                {"name": "28s", "changes": {"target_duration_seconds": 28}},
            ]

            with self.assertRaisesRegex(
                ValueError,
                "CHANNEL_ALREADY_HAS_RUNNING_EXPERIMENT",
            ):
                manager.upsert(another)

            changed = _experiment()
            changed["variants"][0]["changes"] = {"hook_type": "impact"}
            with self.assertRaisesRegex(
                ValueError,
                "PAUSE_EXPERIMENT_BEFORE_EDITING_DEFINITION",
            ):
                manager.upsert(changed)

            assignment = resolve_experiment_assignment(
                "Adsupnews",
                "source-1",
                source_type="article",
                path=path,
                enabled=True,
            )
            self.assertIsNotNone(assignment)
            self.assertIsNone(resolve_experiment_assignment(
                "Adsupnews",
                "source-1",
                source_type="tiktok",
                path=path,
                enabled=True,
            ))

    def test_evaluation_uses_only_story_types_present_in_both_arms(self):
        rows = []
        for variant, watch_time in (("control", 10), ("variant", 14)):
            for index in range(30):
                rows.append({
                    "video_id": f"{variant}-{index}",
                    "channel_id": "Adsupnews",
                    "experiment_id": "hook-result-vs-conflict",
                    "experiment_variant": variant,
                    "story_type": "explainer",
                    "duration": 20,
                    "average_watch_time": watch_time,
                    "watched_full_rate": 0.5,
                    "views": 1000,
                    "measured_at": (
                        f"2026-08-{(index % 28) + 1:02d}T00:00:00+00:00"
                    ),
                })
        rows.append({
            "video_id": "unmatched",
            "channel_id": "Adsupnews",
            "experiment_id": "hook-result-vs-conflict",
            "experiment_variant": "variant",
            "story_type": "warning",
            "duration": 20,
            "average_watch_time": 20,
            "views": 1_000_000,
            "measured_at": "2026-08-23T00:00:00+00:00",
        })

        report = evaluate_experiment(
            _experiment(),
            rows,
            minimum_group_size=5,
        )

        self.assertTrue(report["eligible"])
        self.assertEqual(["explainer"], report["comparable_story_types"])
        self.assertEqual("variant", report["leader"])
        self.assertEqual("", report["winner"])
        self.assertTrue(report["operator_review_required"])


if __name__ == "__main__":
    unittest.main()
