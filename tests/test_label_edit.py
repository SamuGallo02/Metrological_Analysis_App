import unittest

from common.label_edit import LabelModel
from common.label_shapes import Shape, format_labels, parse_labels

BOX = Shape(0, ((0.2, 0.2), (0.6, 0.6)))
TRI = Shape(1, ((0.7, 0.1), (0.9, 0.1), (0.8, 0.4)))


class FormatTest(unittest.TestCase):
    def test_round_trip(self):
        back = parse_labels(format_labels([BOX, TRI]))
        self.assertEqual(len(back), 2)
        self.assertTrue(back[0].is_box and not back[1].is_box)
        for a, b in zip(back[0].points + back[1].points, BOX.points + TRI.points):
            self.assertAlmostEqual(a[0], b[0], 5)
            self.assertAlmostEqual(a[1], b[1], 5)

    def test_a_box_is_written_as_center_and_size(self):
        self.assertEqual(format_labels([BOX]), "0 0.400000 0.400000 0.400000 0.400000\n")


class ModelTest(unittest.TestCase):
    def test_picking(self):
        m = LabelModel([BOX, TRI])
        self.assertEqual(m.handle_at(0.21, 0.19, 0.02), (0, 0))
        self.assertEqual(m.handle_at(0.6, 0.6, 0.02), (0, 2))
        self.assertEqual(m.handle_at(0.8, 0.41, 0.02), (1, 2))
        self.assertIsNone(m.handle_at(0.4, 0.4, 0.02))
        self.assertEqual(m.shape_at(0.4, 0.4), 0)
        self.assertEqual(m.shape_at(0.8, 0.2), 1)
        self.assertIsNone(m.shape_at(0.05, 0.9))

    def test_the_smallest_shape_wins_when_nested(self):
        m = LabelModel([BOX, Shape(2, ((0.3, 0.3), (0.4, 0.4)))])
        self.assertEqual(m.shape_at(0.35, 0.35), 1)
        self.assertEqual(m.shape_at(0.5, 0.5), 0)

    def test_resizing_a_box_keeps_it_normalised_even_when_flipped(self):
        m = LabelModel([BOX])
        m.move_handle(0, 2, 0.1, 0.1)                       # the bottom right corner crosses the top left one
        (x1, y1), (x2, y2) = m.shapes[0].points
        self.assertTrue(x1 <= x2 and y1 <= y2)
        self.assertEqual((x1, y1, x2, y2), (0.1, 0.1, 0.2, 0.2))

    def test_moving_stops_at_the_edges(self):
        m = LabelModel([BOX])
        m.move_shape(0, 5.0, -5.0)
        (x1, y1), (x2, y2) = m.shapes[0].points
        self.assertAlmostEqual(x2, 1.0)
        self.assertAlmostEqual(y1, 0.0)
        self.assertAlmostEqual(x2 - x1, 0.4)                # not squeezed

    def test_vertices(self):
        m = LabelModel([TRI])
        self.assertIsNone(m.insert_vertex(0, 0.5, 0.9, 0.02))        # too far from every edge
        i = m.insert_vertex(0, 0.8, 0.1, 0.02)
        self.assertEqual((i, len(m.shapes[0].points)), (1, 4))
        self.assertTrue(m.remove_vertex(0, i))
        self.assertFalse(m.remove_vertex(0, 0))                      # a polygon keeps at least 3 points
        m.move_handle(0, 0, 2.0, -1.0)                               # outside the image: clamped
        self.assertEqual(m.shapes[0].points[0], (1.0, 0.0))

    def test_adding_and_deleting(self):
        m = LabelModel()
        self.assertIsNone(m.add_box(0, 0.5, 0.5, 0.5005, 0.9))       # a line is not a box
        self.assertIsNone(m.add_polygon(0, [(0, 0), (1, 1)]))
        self.assertEqual(m.add_box(3, 0.9, 0.9, 0.1, 0.1), 0)
        self.assertEqual(m.shapes[0].points, ((0.1, 0.1), (0.9, 0.9)))
        m.set_class(0, 5)
        self.assertEqual(m.shapes[0].cls, 5)
        m.delete(0)
        self.assertEqual(m.shapes, [])

    def test_undo_redo_and_dirty(self):
        m = LabelModel([BOX])
        self.assertFalse(m.dirty)
        m.begin_change()
        m.move_shape(0, 0.1, 0.0)
        self.assertTrue(m.dirty)
        m.begin_change()
        m.delete(0)
        self.assertTrue(m.undo())
        self.assertEqual(len(m.shapes), 1)
        self.assertTrue(m.undo())
        self.assertFalse(m.dirty)                                    # back to what was saved
        self.assertTrue(m.redo())
        self.assertTrue(m.dirty)
        m.mark_saved()
        self.assertFalse(m.dirty)
        self.assertFalse(LabelModel().undo())


if __name__ == "__main__":
    unittest.main()
