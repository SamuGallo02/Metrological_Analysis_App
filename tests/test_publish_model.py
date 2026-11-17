"""Publishing a trained model on the server (with a real server and the real client).

Autore: Samuele Gallo
"""
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.errors import AppError
from common.model_metadata import build_metadata, write_metadata
from corpse.functions.training.publish import publish_model
from server.params import PENDING
from tests.test_system import Base

SPECIES = "Pinna nobilis"


class PublishModelTest(Base):
    def models_dir(self):
        return Path(self.data) / "store" / "library" / "models"

    def model(self, name, with_metadata=True):
        model = self.f(f"{name}.pt", b"modelbytes")
        if with_metadata:
            write_metadata(model, build_metadata(base_model="yolo11n-seg.pt", dataset_name="ok",
                                                 dataset_source="local", epochs=1, imgsz=64, batch=1, device="cpu"))
        return model

    def test_a_user_publishes_into_quarantine(self):
        res = publish_model(self.user("pub1"), self.model("u1"), SPECIES)
        # The file is named after the species it recognises and the network it comes from, not as it was locally.
        self.assertTrue(res["name"].startswith("Pinna_nobilis_yolo11n-seg"), res["name"])
        self.assertEqual(res, {"remote": f"{SPECIES}/{res['name']}", "pending": True, "metadata": True,
                               "name": res["name"]})
        folder = Path(self.data) / "store" / "pending" / "models" / "pub1" / SPECIES
        self.assertTrue((folder / res["name"]).is_file())
        self.assertTrue((folder / Path(res["name"]).with_suffix(".json").name).is_file())

    def test_an_admin_publishes_directly(self):
        res = publish_model(self.admin(), self.model("a1"), SPECIES)
        self.assertFalse(res["pending"])
        self.assertTrue((self.models_dir() / SPECIES / res["name"]).is_file())
        self.assertTrue((self.models_dir() / SPECIES / Path(res["name"]).with_suffix(".json").name).is_file())

    def test_the_chosen_species_is_written_in_the_metadata(self):
        res = publish_model(self.admin(), self.model("a2"), SPECIES)
        meta = json.loads((self.models_dir() / SPECIES / Path(res["name"]).with_suffix(".json").name)
                          .read_text(encoding="utf-8"))
        self.assertEqual(meta["species"], SPECIES)
        self.assertEqual(meta["dataset"]["name"], "ok")

    def test_a_model_without_metadata_is_published_alone(self):
        res = publish_model(self.admin(), self.model("a3", with_metadata=False), SPECIES)
        self.assertFalse(res["metadata"])
        self.assertEqual(res["name"], "Pinna_nobilis_a3.pt")          # no metadata: the file name is what is left
        self.assertFalse((self.models_dir() / SPECIES / "Pinna_nobilis_a3.json").exists())

    def test_a_wrong_species_name_is_refused_before_uploading(self):
        with self.assertRaises(AppError):
            publish_model(self.admin(), self.model("a4"), "pinna")
        self.assertFalse((self.models_dir() / "pinna").exists())

    def test_progress_ends_at_the_total_size(self):
        calls = []
        publish_model(self.admin(), self.model("a5"), SPECIES, progress=lambda d, t: calls.append((d, t)))
        self.assertTrue(calls)
        self.assertEqual(calls[-1][0], calls[-1][1])

    def test_a_user_model_is_sent_to_review(self):
        res = publish_model(self.user("pub6"), self.model("u6"), SPECIES)
        waiting = [s["path"] for s in self.admin().species_submissions(status="pending", kind="model")]
        self.assertTrue(any(p.endswith(f"{SPECIES}/{res['name']}") for p in waiting))

    def test_an_admin_model_is_in_the_catalog_with_no_review(self):
        res = publish_model(self.admin(), self.model("a6"), SPECIES)
        self.assertFalse(res["pending"])
        catalog = [i["path"] for i in self.admin().catalog("model")]
        self.assertIn(f"{SPECIES}/{res['name']}", catalog)


if __name__ == "__main__":
    unittest.main()