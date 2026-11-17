"""The views of the files: the labels can be shown over the media or hidden, and corrected from there."""
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage                                      # noqa: E402
from PySide6.QtWidgets import QApplication                            # noqa: E402

from common.label_store import save_labels                            # noqa: E402
from common.ui.label_editor import LabelCanvas                        # noqa: E402
from common.ui.media_viewer import MediaViewerDialog, labels_of       # noqa: E402

app = QApplication.instance() or QApplication([])


def a_photo(folder: Path, name: str = "a.png") -> Path:
    path = folder / name
    QImage(60, 40, QImage.Format.Format_RGB32).save(str(path))
    return path


class MediaViewerTest(unittest.TestCase):
    def test_the_labels_of_the_analysis_are_found_and_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo = a_photo(Path(tmp))
            self.assertEqual(labels_of(photo), {})
            save_labels(photo, ["0 0.5 0.5 0.2 0.2", "1 0.1 0.1 0.1 0.1"], ["crab", "shell"])
            self.assertEqual(len(labels_of(photo)[0]), 2)

    def test_the_labels_button_shows_and_hides_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo = a_photo(Path(tmp))
            save_labels(photo, ["0 0.5 0.5 0.2 0.2"], ["crab"])
            view = MediaViewerDialog(photo)
            self.assertTrue(view.canvas.show_shapes)
            self.assertEqual(view.canvas.names, ["crab"])
            self.assertEqual(len(view.canvas.model.shapes), 1)        # they are there either way
            view.toggle.setChecked(False)
            self.assertFalse(view.canvas.show_shapes)                 # only the photo is drawn
            view.toggle.setChecked(True)
            self.assertTrue(view.canvas.show_shapes)
            view.close()

    def test_a_view_never_changes_the_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo = a_photo(Path(tmp))
            save_labels(photo, ["0 0.5 0.5 0.2 0.2"], ["crab"])
            view = MediaViewerDialog(photo)
            self.assertTrue(view.canvas.read_only)
            canvas = LabelCanvas()
            canvas.read_only = True
            canvas.keyPressEvent(None)                                # no event is even looked at
            view.close()

    def test_a_photo_without_labels_opens_all_the_same(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = MediaViewerDialog(a_photo(Path(tmp)))
            self.assertEqual(view.canvas.model.shapes, [])
            self.assertTrue(view.count.text())
            view.close()


if __name__ == "__main__":
    unittest.main()
