"""Metadati dei modelli allenati (senza YOLO: i risultati del training sono finti)."""
import hashlib
import json
import sys
import tempfile
import types
import unittest
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.model_metadata import (
    build_metadata, classes_from_data_yaml, count_images, metrics_from_results, model_filename,
    read_metadata, suggest_species, write_metadata)

class MetricsTest(unittest.TestCase):
    def test_reads_the_known_values(self):
        results = types.SimpleNamespace(results_dict={
            "metrics/mAP50(B)": 0.81, "metrics/mAP50-95(B)": 0.55,
            "metrics/precision(B)": 0.77, "metrics/recall(B)": 0.74, "fitness": 0.6})
        self.assertEqual(metrics_from_results(results),
                         {"mAP50": 0.81, "mAP50_95": 0.55, "precision": 0.77, "recall": 0.74})

    def test_missing_or_odd_values_are_left_out(self):
        self.assertEqual(metrics_from_results(types.SimpleNamespace()), {})
        odd = types.SimpleNamespace(results_dict={"metrics/mAP50(B)": "n/a", "metrics/recall(B)": 0.5})
        self.assertEqual(metrics_from_results(odd), {"recall": 0.5})


class BuildMetadataTest(unittest.TestCase):
    def meta(self, **extra):
        args = dict(base_model="/x/models/yolo11n-seg.pt", dataset_name="mini_ok", dataset_source="server",
                    epochs=50, imgsz=640, batch=8, device="cpu", metrics={"mAP50": 0.8},
                    classes=["pinna"], trained_by="admin")
        args.update(extra)
        return build_metadata(**args)

    def test_records_the_recipe(self):
        m = self.meta()
        self.assertEqual(m["schema"], 1)
        self.assertEqual(m["base_model"], "yolo11n-seg.pt")                      # solo il nome del file
        self.assertEqual(m["dataset"], {"name": "mini_ok", "source": "server", "classes": ["pinna"]})
        self.assertEqual(m["parameters"], {"epochs": 50, "imgsz": 640, "batch": 8})
        self.assertEqual((m["device"], m["trained_by"], m["metrics"]), ("cpu", "admin", {"mAP50": 0.8}))
        datetime.fromisoformat(m["created"])                                       # una data leggibile

    def test_species_is_proposed_from_the_classes(self):
        self.assertEqual(self.meta(classes=["Pinna nobilis"])["species"], "Pinna nobilis")
        self.assertIsNone(self.meta(classes=["pinna"])["species"])

    def test_dataset_size_is_recorded_when_known(self):
        self.assertEqual(self.meta(dataset_images=120)["dataset"]["images"], 120)
        self.assertNotIn("images", self.meta()["dataset"])


class WriteReadTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.model = self.dir / "m.pt"
        self.model.write_bytes(b"abc")
        self.meta = BuildMetadataTest().meta()

    def test_writes_next_to_the_model_with_size_and_fingerprint(self):
        path = write_metadata(self.model, self.meta)
        self.assertEqual(path, self.dir / "m.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["file"], {"name": "m.pt", "size": 3, "sha256": hashlib.sha256(b"abc").hexdigest()})
        self.assertNotIn("file", self.meta)                                        # l'originale non cambia

    def test_reads_back(self):
        write_metadata(self.model, self.meta)
        self.assertEqual(read_metadata(self.model)["dataset"]["name"], "mini_ok")

    def test_missing_or_broken_file_gives_none(self):
        self.assertIsNone(read_metadata(self.model))
        (self.dir / "m.json").write_text("{not json", encoding="utf-8")
        self.assertIsNone(read_metadata(self.model))


class ClassesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.yaml = Path(self._tmp.name) / "data.yaml"

    def test_names_as_a_list(self):
        self.yaml.write_text("names: [a, b]\n", encoding="utf-8")
        self.assertEqual(classes_from_data_yaml(self.yaml), ["a", "b"])

    def test_names_as_a_numbered_dictionary(self):
        self.yaml.write_text("names:\n  1: b\n  0: a\n", encoding="utf-8")
        self.assertEqual(classes_from_data_yaml(self.yaml), ["a", "b"])           # in ordine di numero

    def test_missing_file_or_names(self):
        self.assertEqual(classes_from_data_yaml(self.yaml), [])
        self.yaml.write_text("train: images\n", encoding="utf-8")
        self.assertEqual(classes_from_data_yaml(self.yaml), [])


class SuggestSpeciesTest(unittest.TestCase):
    def test_single_scientific_name(self):
        self.assertEqual(suggest_species(["Pinna nobilis"]), "Pinna nobilis")
        self.assertEqual(suggest_species(["pinna_nobilis"]), "Pinna nobilis")

    def test_no_suggestion_when_unsure(self):
        self.assertIsNone(suggest_species(["pinna"]))
        self.assertIsNone(suggest_species(["Pinna nobilis", "Thunnus albacares"]))
        self.assertIsNone(suggest_species([]))


class ModelFilenameTest(unittest.TestCase):
    def test_includes_dataset_base_model_and_time(self):
        name = model_filename("tonno", "/x/models/yolo11n-seg.pt", datetime(2026, 10, 30, 14, 5))
        self.assertEqual(name, "tonno_yolo11n-seg_20261030-1405.pt")

    def test_unsafe_characters_are_replaced(self):
        name = model_filename("Tonni pinna gialla/v2", "yolo11n.pt", datetime(2026, 1, 2, 3, 4))
        self.assertEqual(name, "Tonni_pinna_gialla_v2_yolo11n_20260102-0304.pt")


class CountImagesTest(unittest.TestCase):
    def test_counts_images_in_all_subfolders_and_ignores_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel in ("images/train/a.jpg", "images/train/b.PNG", "images/val/c.jpeg",
                        "labels/train/a.txt", "data.yaml"):
                f = root / rel
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(b"x")
            self.assertEqual(count_images(root), 3)

    def test_missing_folder_has_no_images(self):
        self.assertEqual(count_images(Path("/this/folder/does/not/exist")), 0)

class ClassesWithoutPyYamlTest(unittest.TestCase):
    def read(self, text):
        import sys
        import tempfile
        from pathlib import Path
        from unittest import mock
        from common.model_metadata import classes_from_data_yaml
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "data.yaml"
            f.write_text(text, encoding="utf-8")
            with mock.patch.dict(sys.modules, {"yaml": None}):          # as if PyYAML was not installed
                return classes_from_data_yaml(f)

    def test_numbered_block(self):
        self.assertEqual(self.read("path: .\nnames:\n  0: Pinna nobilis\n  1: Sparus aurata\n"),
                         ["Pinna nobilis", "Sparus aurata"])

    def test_numbers_decide_the_order(self):
        self.assertEqual(self.read("names:\n  1: b\n  0: a\n"), ["a", "b"])

    def test_block_list(self):
        self.assertEqual(self.read("names:\n  - Pinna nobilis\n  - Sparus aurata\n"),
                         ["Pinna nobilis", "Sparus aurata"])

    def test_inline_list(self):
        self.assertEqual(self.read("names: [pinna, 'Sparus aurata']\n"), ["pinna", "Sparus aurata"])

    def test_inline_dict(self):
        self.assertEqual(self.read("names: {0: a, 1: b}\n"), ["a", "b"])

    def test_no_names(self):
        self.assertEqual(self.read("train: images\n"), [])

if __name__ == "__main__":
    unittest.main()