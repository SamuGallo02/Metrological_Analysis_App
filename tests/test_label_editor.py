import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from common.label_shapes import Shape, format_video_labels, parse_video_labels
from common.label_store import read_labels, write_labels
from common.ui.label_editor import (MODE_BOX, MODE_POLYGON, MODE_SELECT, ImageSource, LabelCanvas, LabelEditorDialog)

app = QApplication.instance() or QApplication([])
BOX = Shape(0, ((0.2, 0.2), (0.6, 0.6)))


def canvas(shapes=()):
    c = LabelCanvas()
    c.resize(400, 400)
    c.set_image(QImage(100, 100, QImage.Format.Format_RGB32))
    c.model.shapes = list(shapes)
    c.show()
    return c


def at(c, x, y):
    """Screen position of a normalised point."""
    p = c.to_screen((x, y))
    return QPoint(round(p.x()), round(p.y()))


class VideoLabelsTest(unittest.TestCase):
    def test_round_trip(self):
        frames = {3: [BOX], 10: [Shape(1, ((0.1, 0.1), (0.2, 0.1), (0.2, 0.3)))]}
        back = parse_video_labels(format_video_labels(frames))
        self.assertEqual(sorted(back), [3, 10])
        self.assertTrue(back[3][0].is_box and not back[10][0].is_box)
        self.assertEqual(back[10][0].cls, 1)

    def test_lines_without_a_frame_number_are_ignored(self):
        self.assertEqual(parse_video_labels("x 0 .5 .5 .1 .1\n"), {})


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.media = Path(self.tmp.name) / "a.jpg"
        self.media.write_bytes(b"x")
        self.base = Path(self.tmp.name) / "store"

    def test_a_file_without_labels_starts_empty(self):
        self.assertEqual(read_labels(self.media, self.base), ("", [], False))

    def test_edits_go_back_where_the_labels_came_from(self):
        write_labels(self.media, "0 .5 .5 .1 .1\n", ["crab"], False, self.base)
        text, names, beside = read_labels(self.media, self.base)
        self.assertEqual((text, names, beside), ("0 .5 .5 .1 .1\n", ["crab"], False))
        self.assertFalse(self.media.with_suffix(".txt").exists())            # nothing appears next to the photo
        self.media.with_suffix(".txt").write_text("1 .5 .5 .2 .2\n")         # the user's own label file
        self.assertTrue(read_labels(self.media, self.base)[2])
        write_labels(self.media, "2 .5 .5 .3 .3\n", ["a", "b", "c"], True, self.base)
        self.assertEqual(self.media.with_suffix(".txt").read_text(), "2 .5 .5 .3 .3\n")
        self.assertEqual((self.media.parent / "classes.txt").read_text(), "a\nb\nc\n")


class CanvasTest(unittest.TestCase):
    def test_draw_a_box(self):
        c = canvas()
        c.set_mode(MODE_BOX)
        QTest.mousePress(c, Qt.MouseButton.LeftButton, pos=at(c, 0.2, 0.2))
        QTest.mouseMove(c, at(c, 0.6, 0.5))
        QTest.mouseRelease(c, Qt.MouseButton.LeftButton, pos=at(c, 0.6, 0.5))
        self.assertEqual(len(c.model.shapes), 1)
        (x1, y1), (x2, y2) = c.model.shapes[0].points
        self.assertAlmostEqual(x1, 0.2, 1)
        self.assertAlmostEqual(y2, 0.5, 1)
        self.assertAlmostEqual(x2, 0.6, 1)
        self.assertEqual(c.sel, 0)

    def test_a_click_does_not_make_a_box(self):
        c = canvas()
        c.set_mode(MODE_BOX)
        QTest.mouseClick(c, Qt.MouseButton.LeftButton, pos=at(c, 0.3, 0.3))
        self.assertEqual(c.model.shapes, [])

    def test_drag_a_corner_and_move_the_box(self):
        c = canvas([BOX])
        c.set_mode(MODE_SELECT)
        QTest.mousePress(c, Qt.MouseButton.LeftButton, pos=at(c, 0.6, 0.6))       # bottom right corner
        QTest.mouseMove(c, at(c, 0.8, 0.8))
        QTest.mouseRelease(c, Qt.MouseButton.LeftButton, pos=at(c, 0.8, 0.8))
        self.assertAlmostEqual(c.model.shapes[0].points[1][0], 0.8, 1)
        QTest.mousePress(c, Qt.MouseButton.LeftButton, pos=at(c, 0.4, 0.4))       # inside: moves the whole box
        QTest.mouseMove(c, at(c, 0.3, 0.3))
        QTest.mouseRelease(c, Qt.MouseButton.LeftButton, pos=at(c, 0.3, 0.3))
        self.assertAlmostEqual(c.model.shapes[0].points[0][0], 0.1, 1)

    def test_delete_undo_and_class_change(self):
        c = canvas([BOX])
        c.select(0)
        c.set_class_of_selected(2)
        self.assertEqual(c.model.shapes[0].cls, 2)
        c.delete_selected()
        self.assertEqual(c.model.shapes, [])
        c.model.undo()
        self.assertEqual(len(c.model.shapes), 1)
        c.model.undo()
        self.assertEqual(c.model.shapes[0].cls, 0)

    def test_draw_a_polygon(self):
        c = canvas()
        c.set_mode(MODE_POLYGON)
        for p in ((0.1, 0.1), (0.5, 0.1), (0.5, 0.5), (0.1, 0.5)):
            QTest.mouseClick(c, Qt.MouseButton.LeftButton, pos=at(c, *p))
        c.finish_polygon()
        self.assertEqual(len(c.model.shapes), 1)
        self.assertEqual(len(c.model.shapes[0].points), 4)

    def test_right_click_removes_a_vertex(self):
        c = canvas([Shape(0, ((0.1, 0.1), (0.5, 0.1), (0.5, 0.5), (0.1, 0.5)))])
        c.select(0)
        QTest.mouseClick(c, Qt.MouseButton.RightButton, pos=at(c, 0.5, 0.5))
        self.assertEqual(len(c.model.shapes[0].points), 3)


class DialogTest(unittest.TestCase):
    def dialog(self, saved, labels=None):
        image = QImage(100, 100, QImage.Format.Format_RGB32)
        return LabelEditorDialog(ImageSource(image), labels if labels is not None else {0: [BOX]}, ["crab", "fish"],
                                 lambda result, classes: saved.append((result, list(classes))), "t")

    def test_save_sends_the_shapes_and_classes(self):
        saved = []
        d = self.dialog(saved)
        d.canvas.select(0)
        d.canvas.set_class_of_selected(1)
        self.assertTrue(d.dirty)
        self.assertTrue(d.save())
        self.assertFalse(d.dirty)
        self.assertEqual(saved[0][0][0][0].cls, 1)
        self.assertEqual(saved[0][1], ["crab", "fish"])

    def test_a_failing_save_keeps_the_changes(self):
        from unittest import mock
        from PySide6.QtWidgets import QMessageBox

        def boom(result, classes):
            raise OSError("disk full")
        image = QImage(10, 10, QImage.Format.Format_RGB32)
        d = LabelEditorDialog(ImageSource(image), {0: [BOX]}, ["a"], boom)
        d.canvas.select(0)
        d.canvas.delete_selected()
        with mock.patch.object(QMessageBox, "warning") as warn:
            self.assertFalse(d.save())
        warn.assert_called_once()
        self.assertTrue(d.dirty)

    def test_empty_frames_are_not_saved(self):
        saved = []
        d = self.dialog(saved, {0: [BOX]})
        d.canvas.select(0)
        d.canvas.delete_selected()
        d.save()
        self.assertEqual(saved[0][0], {})

    def test_a_video_goes_from_labelled_frame_to_labelled_frame(self):
        from common.ui.label_editor import FrameSource

        class Frames(FrameSource):
            count = 20

            def image(self, i):
                return QImage(10, 10, QImage.Format.Format_RGB32)
        d = LabelEditorDialog(Frames(), {3: [BOX], 12: [BOX]}, ["a"], lambda r, c: None)
        self.assertEqual(d.frame, 3)
        d._jump(1)
        self.assertEqual(d.frame, 12)
        d._jump(1)
        self.assertEqual(d.frame, 12)                                      # nothing after
        d._jump(-1)
        self.assertEqual(d.frame, 3)


if __name__ == "__main__":
    unittest.main()
