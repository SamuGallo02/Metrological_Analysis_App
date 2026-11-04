"""Le righe di testo che descrivono un modello a partire dai suoi metadati."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import i18n
from corpse.gui.users.model_info import model_info_lines

NONE = ["No details available for this model."]

FULL = {"species": "Pinna nobilis", "created": "2026-10-30T14:12:05+01:00", "trained_by": "admin",
        "base_model": "yolo11n-seg.pt", "dataset": {"name": "ok", "images": 120},
        "parameters": {"epochs": 50, "imgsz": 640, "batch": 8}, "device": "cpu",
        "metrics": {"mAP50": 0.812, "mAP50_95": 0.55, "precision": 0.77, "recall": 0.74}}


class ModelInfoLinesTest(unittest.TestCase):
    def setUp(self):
        i18n.set_language("en")

    def test_full_metadata(self):
        self.assertEqual(model_info_lines(FULL), [
            "Species: Pinna nobilis", "Created: 2026-10-30", "Trained by: admin", "Base model: yolo11n-seg.pt",
            "Dataset: ok (120 images)", "Training: 50 epochs, image size 640, batch 8, cpu",
            "Metrics: mAP50 0.81, mAP50-95 0.55, precision 0.77, recall 0.74"])

    def test_missing_parts_are_left_out(self):
        meta = {"species": "Pinna nobilis", "dataset": {"name": "ok"}}
        self.assertEqual(model_info_lines(meta), ["Species: Pinna nobilis", "Dataset: ok"])

    def test_no_metadata(self):
        for meta in (None, {}, {"schema": 1}):
            with self.subTest(meta=meta):
                self.assertEqual(model_info_lines(meta), NONE)

    def test_odd_values_do_not_break_it(self):
        meta = {"species": "X", "dataset": "oops", "parameters": [1], "metrics": {"mAP50": "n/a"}}
        self.assertEqual(model_info_lines(meta), ["Species: X"])


if __name__ == "__main__":
    unittest.main()