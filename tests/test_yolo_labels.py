import unittest

from corpse.functions.users.yolo_labels import (class_label, class_names, label_candidates, names_candidates,
                                                parse_labels)


class YoloLabelsTest(unittest.TestCase):
    def test_box_and_polygon(self):
        shapes = parse_labels("0 0.5 0.5 0.2 0.4\n2 0.1 0.1 0.9 0.1 0.5 0.8\n")
        self.assertTrue(shapes[0].is_box)
        self.assertEqual(shapes[0].points, ((0.4, 0.3), (0.6, 0.7)))
        self.assertEqual((shapes[1].cls, len(shapes[1].points)), (2, 3))

    def test_malformed_lines_are_skipped(self):
        self.assertEqual(parse_labels("x 1 2 3 4\n0 1 2\n-1 .1 .1 .1 .1\n0 nan .1 .1 .1\n\n"), [])

    def test_candidates(self):
        self.assertEqual(label_candidates("S/b/images/a.jpg"), ["S/b/images/a.txt", "S/b/labels/a.txt"])
        self.assertEqual(label_candidates("S/b/a.jpg")[0], "S/b/a.txt")
        self.assertEqual(names_candidates("S/a.jpg")[-1], "classes.txt")

    def test_names(self):
        self.assertEqual(class_names("classes.txt", "a\n\nb\n"), ["a", "b"])
        self.assertEqual(class_names("data.yaml", "names:\n  0: x\n  1: y\n"), ["x", "y"])
        self.assertEqual((class_label(["x"], 0), class_label(["x"], 5), class_label(None, 1)), ("x", "5", "1"))


if __name__ == "__main__":
    unittest.main()
