"""Shaping the labels by hand: more points on a polygon, a box turned into one, and the colour of the lines.

The colour matters as much as the geometry: red lines on a red fish cannot be corrected by anybody.

Autore: Samuele Gallo
"""
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage                              # noqa: E402
from PySide6.QtWidgets import QApplication                            # noqa: E402

from common.label_edit import LabelModel                              # noqa: E402
from common.label_shapes import Shape                                 # noqa: E402
from common.label_store import save_labels                            # noqa: E402
from common.ui import label_style                                     # noqa: E402
from common.ui.label_editor import LabelCanvas, LabelEditorDialog, ImageSource  # noqa: E402
from common.ui.label_overlay import draw_shapes, shapes_of, with_labels          # noqa: E402

app = QApplication.instance() or QApplication([])
BOX = Shape(0, ((0.1, 0.1), (0.5, 0.5)))
POLY = Shape(0, ((0.1, 0.1), (0.5, 0.1), (0.5, 0.5), (0.1, 0.5)))


def a_photo(folder: Path, name: str = "a.png") -> Path:
    path = folder / name
    QImage(80, 60, QImage.Format.Format_RGB32).save(str(path))
    return path


class PolygonToolsTest(unittest.TestCase):
    def test_more_points_keeps_the_shape_and_doubles_the_nodes(self):
        m = LabelModel([POLY])
        self.assertEqual(m.subdivide(0), 4)
        points = m.shapes[0].points
        self.assertEqual(len(points), 8)
        self.assertIn((0.3, 0.1), points)                 # the new ones sit in the middle of each side
        self.assertEqual(points[0], (0.1, 0.1))           # the old ones are where they were

    def test_a_box_can_become_a_polygon_and_then_grow_nodes(self):
        m = LabelModel([BOX])
        self.assertEqual(m.subdivide(0), 0)               # a box has corners, not nodes
        self.assertTrue(m.to_polygon(0))
        self.assertEqual(len(m.shapes[0].points), 4)
        self.assertFalse(m.shapes[0].is_box)
        self.assertEqual(m.subdivide(0), 4)

    def test_a_polygon_does_not_grow_without_end(self):
        m = LabelModel([POLY])
        for _ in range(20):
            m.subdivide(0)
        self.assertLessEqual(len(m.shapes[0].points), 200)

    def test_the_point_that_would_be_added_is_known_before_the_click(self):
        m = LabelModel([POLY])
        self.assertIsNotNone(m.edge_point(0, 0.3, 0.102, 0.01))       # near the top side
        self.assertIsNone(m.edge_point(0, 0.3, 0.3, 0.01))            # in the middle: no side there
        self.assertIsNone(m.edge_point(0, 0.3, 0.102, 0.0001))        # too far for this tolerance

    def test_the_canvas_adds_a_point_where_the_user_clicks_an_edge(self):
        canvas = LabelCanvas()
        canvas.set_image(QImage(200, 200, QImage.Format.Format_RGB32))
        canvas.resize(200, 200)
        canvas.set_model(LabelModel([POLY]))
        canvas.select(0)
        self.assertTrue(canvas.add_point_here(0.3, 0.1))
        self.assertEqual(len(canvas.model.shapes[0].points), 5)
        self.assertEqual(canvas.subdivide_selected(), 5)
        canvas.set_model(LabelModel([BOX]))
        canvas.select(0)
        self.assertTrue(canvas.to_polygon_selected())
        canvas.deleteLater()


class CreateOrEditTest(unittest.TestCase):
    def test_the_window_says_create_when_there_is_nothing_yet(self):
        source = ImageSource(QImage(40, 40, QImage.Format.Format_RGB32))
        empty = LabelEditorDialog(source, {}, [], lambda r, c: None, "a.png")
        self.assertTrue(empty.creating)
        self.assertIn("a.png", empty.windowTitle())
        empty.close()
        full = LabelEditorDialog(ImageSource(QImage(40, 40, QImage.Format.Format_RGB32)),
                                 {0: [POLY]}, ["crab"], lambda r, c: None, "a.png")
        self.assertFalse(full.creating)
        full.close()


class LabelColourTest(unittest.TestCase):
    def tearDown(self):
        label_style.set_color_override(None)

    def test_a_chosen_colour_is_used_for_every_class(self):
        self.assertNotEqual(label_style.color_for(0), label_style.color_for(1))   # by class, to begin with
        label_style.set_color_override(QColor("#ffe100"))
        self.assertEqual(label_style.color_for(0).name(), "#ffe100")
        self.assertEqual(label_style.color_for(7).name(), "#ffe100")
        label_style.set_color_override(None)
        self.assertNotEqual(label_style.color_for(0), label_style.color_for(1))

    def test_the_colour_reaches_what_is_drawn(self):
        image = QImage(40, 40, QImage.Format.Format_RGB32)
        image.fill(0)
        label_style.set_color_override(QColor("#00ff00"))
        out = draw_shapes(image, [Shape(0, ((0.0, 0.0), (1.0, 1.0)))], with_names=False)
        drawn = [QColor(out.pixel(x, 0)) for x in range(40)]
        green = [c for c in drawn if c.green() > 100]               # antialiasing softens the line: the hue stays
        self.assertTrue(green)
        self.assertTrue(all(c.red() == 0 and c.blue() == 0 for c in green))

    def test_the_button_offers_the_colours_and_puts_them_back(self):
        button = label_style.LabelColorButton()
        self.assertTrue(button.menu().actions())
        button.deleteLater()


class PreviewLabelsTest(unittest.TestCase):
    def test_a_preview_carries_the_labels_of_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo = a_photo(Path(tmp))
            plain = QImage(str(photo))
            self.assertEqual(shapes_of(photo), [])
            self.assertEqual(with_labels(plain, photo), plain)        # nothing to draw: the picture as it is
            save_labels(photo, ["0 0.5 0.5 0.4 0.4"], ["crab"])
            self.assertEqual(len(shapes_of(photo)), 1)
            self.assertNotEqual(with_labels(plain, photo), plain)

    def test_the_previews_of_the_two_states_do_not_mix(self):
        from common.ui.thumbnails import _cache_file
        self.assertNotEqual(_cache_file("k", 64, "labels"), _cache_file("k", 64, ""))


if __name__ == "__main__":
    unittest.main()
