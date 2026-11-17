"""The worker that takes the queued trainings: what it does with a job, and what it does when it fails.

Autore: Samuele Gallo
"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import training_worker as qw


class FakeClient:
    def __init__(self, jobs):
        self.jobs, self.updates, self.published = list(jobs), [], []

    def claim_training(self, name):
        return self.jobs.pop(0) if self.jobs else None

    def update_training(self, job_id, **fields):
        self.updates.append((job_id, fields))
        return {}


JOB = {"id": 7, "username": "mario", "dataset": "set1", "base_model": "yolo11n-seg.pt", "epochs": 3,
       "imgsz": 320, "batch": 2, "species": "Pinna nobilis"}


class WorkerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.space = Path(self.tmp.name)
        self.client = FakeClient([dict(JOB)])
        self.worker = qw.Worker(self.client, "gpu-test", self.space, device="cpu")

    def prepare(self, model_name="m.pt"):
        """A downloaded dataset and a trained model, without downloading or training anything."""
        def download(_client, _area, dataset, dest, **kw):
            Path(dest).mkdir(parents=True, exist_ok=True)
            (Path(dest) / "data.yaml").write_text("names: [crab]\n")
        model = self.space / model_name
        model.write_bytes(b"weights")
        return download, model

    def test_a_job_goes_through_download_training_and_publishing(self):
        download, model = self.prepare()
        with mock.patch.object(qw, "download_tree", download), \
                mock.patch.object(qw, "train_model", return_value=(model, {"mAP50": 0.8})) as train, \
                mock.patch.object(qw, "write_metadata") as meta, \
                mock.patch.object(qw, "publish_model", return_value={"remote": "Pinna nobilis/m.pt"}) as publish:
            self.assertTrue(self.worker.one())
        self.assertEqual(train.call_args.args[0], str(self.space / "set1" / "data.yaml"))
        self.assertEqual(train.call_args.args[1:6], ("yolo11n-seg.pt", 3, 320, 2, "cpu"))
        meta.assert_called_once()
        publish.assert_called_once()
        last_id, last = self.client.updates[-1]
        self.assertEqual((last_id, last["status"], last["model"]), (7, "done", "Pinna nobilis/m.pt"))
        self.assertEqual(last["metrics"], {"mAP50": 0.8})

    def test_without_a_species_the_model_is_not_published(self):
        self.client.jobs = [dict(JOB, species="")]
        download, model = self.prepare()
        with mock.patch.object(qw, "download_tree", download), \
                mock.patch.object(qw, "train_model", return_value=(model, {})), \
                mock.patch.object(qw, "write_metadata"), \
                mock.patch.object(qw, "publish_model") as publish:
            self.worker.one()
        publish.assert_not_called()
        self.assertEqual(self.client.updates[-1][1]["status"], "done")

    def test_a_failure_is_reported_and_the_worker_keeps_going(self):
        download, _model = self.prepare()
        with mock.patch.object(qw, "download_tree", download), \
                mock.patch.object(qw, "train_model", side_effect=RuntimeError("CUDA out of memory")):
            self.assertTrue(self.worker.one())                 # it does not raise
        job_id, last = self.client.updates[-1]
        self.assertEqual((job_id, last["status"]), (7, "failed"))
        self.assertIn("CUDA out of memory", last["message"])
        self.assertFalse(self.worker.one())                    # queue empty

    def test_a_dataset_without_data_yaml_is_a_clear_failure(self):
        def download(_client, _area, dataset, dest, **kw):
            Path(dest).mkdir(parents=True, exist_ok=True)
        with mock.patch.object(qw, "download_tree", download):
            self.worker.one()
        self.assertIn("data.yaml", self.client.updates[-1][1]["message"])

    def test_nothing_to_do(self):
        self.client.jobs = []
        self.assertFalse(self.worker.one())
        self.assertEqual(self.client.updates, [])

    def test_the_device_is_the_graphics_card_when_there_is_one(self):
        with mock.patch.dict("sys.modules", {"torch": SimpleNamespace(
                cuda=SimpleNamespace(is_available=lambda: True), backends=SimpleNamespace(mps=None))}):
            self.assertEqual(qw.pick_device(), "0")
        with mock.patch.dict("sys.modules", {"torch": SimpleNamespace(
                cuda=SimpleNamespace(is_available=lambda: False),
                backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: True)))}):
            self.assertEqual(qw.pick_device(), "mps")

    def test_the_password_is_not_asked_on_the_command_line_only(self):
        with mock.patch.dict("os.environ", {"AM_WORKER_PASSWORD": ""}, clear=False):
            self.assertEqual(qw.main(["--server", "http://x", "--user", "u"]), 2)


if __name__ == "__main__":
    unittest.main()
