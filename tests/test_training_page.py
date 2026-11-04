"""Training page: connection with the account and the server (headless)."""
import os, sys, tempfile, types, unittest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import json

from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication, QWidget
app = QApplication.instance() or QApplication([])

from corpse.gui.training import page as training_page
from corpse.gui.training.page import TrainingPage

from common.errors import AppError
from common.model_metadata import build_metadata, write_metadata
from tests.util import pump


class TrainingPageSessionTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        # la pagina non deve toccare le cartelle vere, né controllare rete e hardware
        for name, value in (("TDATASET_DIR", tmp / "datasets"), ("MODELS_DIR", tmp / "models"),
                            ("check_internet_connection", lambda: False),
                            ("get_hardware_info", lambda: ("cpu", "CPU di prova")),
                            ("HardwareAccelerationWidget", lambda parent=None: QWidget())):
            patcher = mock.patch.object(training_page, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def page(self, session=None):
        p = TrainingPage(on_home=lambda: None, session=session)
        self.addCleanup(p.deleteLater)
        return p

    def test_without_a_session_the_server_is_not_available(self):
        self.assertFalse(self.page().server_available())

    def test_offline_session_cannot_use_the_server(self):
        session = types.SimpleNamespace(online=False, is_guest=False)
        self.assertFalse(self.page(session).server_available())

    def test_guest_cannot_use_the_server(self):
        session = types.SimpleNamespace(online=True, is_guest=True)
        self.assertFalse(self.page(session).server_available())

    def test_online_account_can_use_the_server(self):
        session = types.SimpleNamespace(online=True, is_guest=False)
        page = self.page(session)
        self.assertIs(page.session, session)
        self.assertTrue(page.server_available())

    def test_server_button_is_hidden_without_an_account(self):
        self.assertTrue(self.page().btn_server.isHidden())

    def test_server_button_follows_the_connection(self):
        session = types.SimpleNamespace(online=False, is_guest=False, client=object())
        page = self.page(session)
        self.assertFalse(page.btn_server.isEnabled())
        session.online = True                       # l'app si è riconnessa
        page._update_server_button()
        self.assertTrue(page.btn_server.isEnabled())

    def test_button_opens_the_dialog_with_the_session_client(self):
        client = object()
        page = self.page(types.SimpleNamespace(online=True, is_guest=False, client=client))
        with mock.patch.object(training_page, "ServerDatasetDialog") as dialog:
            page.btn_server.click()
        dialog.assert_called_once_with(client, training_page.TDATASET_DIR, page)
        dialog.return_value.downloaded.connect.assert_called_once_with(page._on_server_dataset_downloaded)
        dialog.return_value.exec.assert_called_once()

    def test_after_the_download_the_dataset_is_selected(self):
        page = self.page(types.SimpleNamespace(online=True, is_guest=False, client=object()))
        folder = training_page.TDATASET_DIR / "ok"
        folder.mkdir(parents=True)
        (folder / "data.yaml").write_text("names: [a]")
        page._on_server_dataset_downloaded("ok")
        self.assertTrue(page.combo_tdatasets.currentData().endswith("data.yaml"))
        self.assertIn("ok", page.combo_tdatasets.currentText())

    def _dataset(self, name="ok", names="names: [pinna]\n"):
        folder = training_page.TDATASET_DIR / name
        folder.mkdir(parents=True)
        (folder / "data.yaml").write_text(names)
        return folder

    def _started_page(self, session=None, downloaded=None):
        """Una pagina con il dataset 'ok', su cui è stato premuto AVVIA (il worker vero è sostituito)."""
        self._dataset()
        page = self.page(session)
        if downloaded:
            page._on_server_dataset_downloaded(downloaded)
        with mock.patch.object(training_page, "TrainingWorker"):
            page.btn_start.click()
        return page

    def test_start_remembers_what_is_being_trained(self):
        ctx = self._started_page()._run_context
        self.assertEqual((ctx["dataset_name"], ctx["dataset_source"], ctx["classes"], ctx["device"]),
                         ("ok", "local", ["pinna"], "cpu"))
        self.assertEqual(ctx["dataset_images"], 0)           # il dataset di prova non ha immagini

    def test_a_dataset_downloaded_from_the_server_is_marked_as_such(self):
        session = types.SimpleNamespace(online=True, is_guest=False, client=object(), username="admin")
        ctx = self._started_page(session, downloaded="ok")._run_context
        self.assertEqual(ctx["dataset_source"], "server")
        self.assertEqual(ctx["trained_by"], "admin")

    def test_a_guest_is_not_recorded_as_author(self):
        guest = types.SimpleNamespace(online=False, is_guest=True, client=None, username="offline")
        self.assertEqual(self._started_page(guest)._run_context["trained_by"], "")

    def test_finished_training_writes_the_metadata_next_to_the_model(self):
        page = self._started_page()
        model = Path(self._tmp.name) / "trained.pt"
        model.write_bytes(b"abc")
        page.worker.metrics = {"mAP50": 0.8}
        with mock.patch.object(training_page.QMessageBox, "information"):
            page._on_training_finished(str(model))
        meta = json.loads(model.with_suffix(".json").read_text(encoding="utf-8"))
        self.assertEqual(meta["dataset"]["name"], "ok")
        self.assertEqual(meta["metrics"], {"mAP50": 0.8})
        self.assertIsNone(meta["species"])                         # la classe "pinna" non è un nome scientifico
        self.assertEqual(meta["file"]["size"], 3)

    def test_without_a_started_training_no_metadata_is_written(self):
        page = self.page()
        model = Path(self._tmp.name) / "other.pt"
        model.write_bytes(b"abc")
        with mock.patch.object(training_page.QMessageBox, "information"):
            page._on_training_finished(str(model))
        self.assertFalse(model.with_suffix(".json").exists())

    def _online(self):
        client = object()
        return types.SimpleNamespace(online=True, is_guest=False, client=client, username="admin"), client

    def _trained(self, session, with_species=False):
        """Una pagina su cui è appena finito un training: restituisce (pagina, modello)."""
        page = self.page(session)
        model = Path(self._tmp.name) / "trained.pt"
        model.write_bytes(b"abc")
        if with_species:
            write_metadata(model, build_metadata(base_model="yolo11n.pt", dataset_name="ok",
                                                 dataset_source="local", epochs=1, imgsz=64, batch=1,
                                                 device="cpu", classes=["Pinna nobilis"]))
        with mock.patch.object(training_page.QMessageBox, "information"):
            page._on_training_finished(str(model))
        return page, model

    def test_publish_button_is_hidden_without_an_account(self):
        self.assertTrue(self.page().btn_publish.isHidden())

    def test_publish_needs_a_trained_model_and_the_server(self):
        session, _client = self._online()
        self.assertFalse(self.page(session).btn_publish.isEnabled())          # nessun modello ancora
        page, _model = self._trained(session)
        self.assertTrue(page.btn_publish.isEnabled())
        session.online = False
        page._update_server_button()
        self.assertFalse(page.btn_publish.isEnabled())                         # il server non risponde

    def test_publish_asks_for_the_species_and_uploads(self):
        session, client = self._online()
        page, model = self._trained(session)
        reply = {"remote": "Pinna nobilis/trained.pt", "pending": True, "metadata": False}
        with mock.patch.object(training_page.QInputDialog, "getText", return_value=("Pinna nobilis", True)), \
             mock.patch.object(training_page, "publish_model", return_value=reply) as publish, \
             mock.patch.object(training_page.QMessageBox, "information") as info:
            page.btn_publish.click()
            self.assertTrue(pump(lambda: info.called))
        self.assertEqual(publish.call_args.args, (client, model, "Pinna nobilis"))
        self.assertIn("approval", info.call_args.args[2])                      # in attesa dell'approvazione

    def test_an_admin_is_told_the_model_is_published(self):
        session, _client = self._online()
        page, _model = self._trained(session)
        reply = {"remote": "Pinna nobilis/trained.pt", "pending": False, "metadata": True}
        with mock.patch.object(training_page.QInputDialog, "getText", return_value=("Pinna nobilis", True)), \
             mock.patch.object(training_page, "publish_model", return_value=reply), \
             mock.patch.object(training_page.QMessageBox, "information") as info:
            page.btn_publish.click()
            self.assertTrue(pump(lambda: info.called))
        self.assertIn("published", info.call_args.args[2])

    def test_cancelling_the_species_dialog_uploads_nothing(self):
        session, _client = self._online()
        page, _model = self._trained(session)
        with mock.patch.object(training_page.QInputDialog, "getText", return_value=("", False)), \
             mock.patch.object(training_page, "publish_model") as publish:
            page.btn_publish.click()
            pump(lambda: False, secs=0.3)
        publish.assert_not_called()

    def test_the_species_is_proposed_from_the_metadata(self):
        session, _client = self._online()
        page, _model = self._trained(session, with_species=True)
        with mock.patch.object(training_page.QInputDialog, "getText", return_value=("", False)) as ask:
            page.btn_publish.click()
        self.assertEqual(ask.call_args.kwargs["text"], "Pinna nobilis")

    def test_a_failed_upload_is_reported_and_the_button_comes_back(self):
        session, _client = self._online()
        page, _model = self._trained(session)
        with mock.patch.object(training_page.QInputDialog, "getText", return_value=("Pinna nobilis", True)), \
             mock.patch.object(training_page, "publish_model", side_effect=AppError("Boom.")), \
             mock.patch.object(training_page.QMessageBox, "warning") as warn:
            page.btn_publish.click()
            self.assertTrue(pump(lambda: warn.called))
        self.assertTrue(page.btn_publish.isEnabled())