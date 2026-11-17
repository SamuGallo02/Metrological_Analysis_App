"""The performance view: which photos the test uses and what it shows.

Autore: Samuele Gallo
"""
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest import mock

from PySide6.QtWidgets import QApplication

from corpse.gui.home import performance as perf

app = QApplication.instance() or QApplication([])


class FakeClient:
    """A server with two photos, one of which has labels, and a model."""

    def __init__(self):
        self.tree = {"photos": [("Pinna nobilis/b1/IMG_0001.png", 10), ("Pinna nobilis/b1/IMG_0001.txt", 4),
                                ("Pinna nobilis/b1/IMG_0002.png", 10), ("Pinna nobilis/b1/classes.txt", 4)]}

    def list_tree(self, area, rel):
        return self.tree.get(area, [])


class LabelledPhotosTest(unittest.TestCase):
    def photos(self, limit=10):
        client = FakeClient()
        with mock.patch.object(perf, "walk_remote", lambda c, area, rel: client.list_tree(area, rel)):
            return perf.labelled_photos(client, "Pinna nobilis", limit)

    def test_only_the_photos_that_have_labels_are_used(self):
        self.assertEqual(self.photos(), [("Pinna nobilis/b1/IMG_0001.png", "Pinna nobilis/b1/IMG_0001.txt")])

    def test_the_number_of_photos_is_limited(self):
        self.assertEqual(self.photos(limit=0), [])

    def test_classes_txt_is_not_taken_for_a_label(self):
        pairs = self.photos()
        self.assertTrue(all(not p[1].endswith("classes.txt") for p in pairs))


class DialogTest(unittest.TestCase):
    def dialog(self, items=()):
        session = type("S", (), {"online": False, "client": None})()
        dlg = perf.ModelPerformanceDialog(session)
        dlg._fill(list(items))
        return dlg

    def item(self, path, species="Pinna nobilis", **metrics):
        return {"path": path, "species": species, "uploader": "mario",
                "meta": {"metrics": metrics, "trained_by": "mario"}}

    def test_offline_the_test_button_is_off(self):
        dlg = self.dialog()
        self.assertFalse(dlg.btn_test.isEnabled())

    def test_the_table_shows_the_numbers_of_the_training(self):
        dlg = self.dialog([self.item("Pinna nobilis/a.pt", **{"mAP50": 0.9, "recall": 0.5})])
        self.assertEqual(dlg.table.item(0, 1).text(), "a.pt")
        self.assertEqual(dlg.table.item(0, 2).text(), "0.900")
        self.assertEqual(dlg.table.item(0, 3).text(), "-")            # a number that is not there
        self.assertEqual(dlg.table.item(0, 5).text(), "0.500")

    def test_several_models_selected_are_compared(self):
        dlg = self.dialog([self.item("Pinna nobilis/a.pt", **{"mAP50": 0.9}),
                           self.item("Pinna nobilis/b.pt", **{"mAP50": 0.7})])
        dlg.table.selectAll()
        self.assertIn("a.pt", dlg.card.toPlainText())
        self.assertIn("b.pt", dlg.card.toPlainText())
        self.assertIn("0.700", dlg.card.toPlainText())

    def test_the_result_of_a_test_names_the_best(self):
        from corpse.functions.analysis.model_eval import Score
        good, bad = Score(), Score()
        for s, hits in ((good, 9), (bad, 3)):
            s.photos, s.objects, s.found, s.hits = 10, 10, 10, hits
        dlg = self.dialog()
        dlg._show_test([("a.pt", bad), ("b.pt", good)])
        text = dlg.card.toPlainText()
        self.assertIn("b.pt  <<", text)
        self.assertNotIn("a.pt  <<", text)
        self.assertIn("0.9", text)


if __name__ == "__main__":
    unittest.main()
