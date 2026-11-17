"""Measuring a model on photos that already have labels.

Autore: Samuele Gallo
"""
import unittest
from pathlib import Path

from corpse.functions.analysis.model_eval import Score, compare, evaluate, iou, shape_box, truth_boxes
from common.label_shapes import Shape

CRAB, FISH = 0, 1
NAMES = ["crab", "fish"]


class OverlapTest(unittest.TestCase):
    def test_iou(self):
        self.assertEqual(iou((0, 0, 10, 10), (0, 0, 10, 10)), 1.0)
        self.assertEqual(iou((0, 0, 10, 10), (20, 20, 30, 30)), 0.0)
        self.assertAlmostEqual(iou((0, 0, 10, 10), (5, 0, 15, 10)), 1 / 3, places=3)

    def test_a_polygon_is_measured_by_the_box_around_it(self):
        shape = Shape(CRAB, ((0.1, 0.2), (0.5, 0.2), (0.5, 0.6)))
        self.assertEqual(shape_box(shape, 100, 100), (10.0, 20.0, 50.0, 60.0))

    def test_the_labels_of_a_photo_are_read_as_boxes(self):
        boxes = truth_boxes("0 0.5 0.5 0.2 0.2\n1 0.1 0.1 0.9 0.1 0.9 0.5\n", 100, 100)
        self.assertEqual(boxes[0], (CRAB, (40.0, 40.0, 60.0, 60.0)))
        self.assertEqual(boxes[1][0], FISH)


class CompareTest(unittest.TestCase):
    def score(self, truth, found):
        s = Score()
        compare(truth, found, NAMES, s)
        return s

    def test_everything_right(self):
        s = self.score([(CRAB, (0, 0, 10, 10))], [(CRAB, (0, 0, 10, 10))])
        self.assertEqual((s.hits, s.missed, s.false_alarms), (1, 0, 0))
        self.assertEqual((s.precision, s.recall, s.f1), (1.0, 1.0, 1.0))

    def test_a_missed_object_and_a_false_alarm(self):
        s = self.score([(CRAB, (0, 0, 10, 10))], [(CRAB, (90, 90, 99, 99))])
        self.assertEqual((s.hits, s.missed, s.false_alarms), (0, 1, 1))
        self.assertEqual(s.per_class["crab"], {"objects": 1, "hits": 0, "missed": 1, "false_alarms": 1})

    def test_the_right_place_with_the_wrong_name(self):
        s = self.score([(CRAB, (0, 0, 10, 10))], [(FISH, (0, 0, 10, 10))])
        self.assertEqual((s.hits, s.wrong_class), (0, 1))
        self.assertEqual(s.recall, 0.0)

    def test_each_object_is_used_once(self):
        s = self.score([(CRAB, (0, 0, 10, 10))], [(CRAB, (0, 0, 10, 10)), (CRAB, (1, 1, 11, 11))])
        self.assertEqual((s.hits, s.false_alarms), (1, 1))

    def test_a_small_overlap_does_not_count_as_a_hit(self):
        s = self.score([(CRAB, (0, 0, 10, 10))], [(CRAB, (8, 8, 18, 18))])
        self.assertEqual(s.hits, 0)

    def test_a_photo_with_nothing_in_it(self):
        s = self.score([], [(CRAB, (0, 0, 10, 10))])
        self.assertEqual((s.objects, s.false_alarms, s.recall), (0, 1, 0.0))


class EvaluateTest(unittest.TestCase):
    def test_several_photos_add_up_and_a_broken_one_is_skipped(self):
        photos = [(Path("a.jpg"), "0 0.5 0.5 0.2 0.2\n"), (Path("b.jpg"), "0 0.5 0.5 0.2 0.2\n"),
                  (Path("broken.jpg"), "0 0.5 0.5 0.2 0.2\n")]
        seen = []

        def detect(path):
            if path.name == "broken.jpg":
                raise OSError("cannot read")
            found = [(CRAB, (40.0, 40.0, 60.0, 60.0))] if path.name == "a.jpg" else []
            return found, NAMES, 100, 100

        score = evaluate(detect, photos, progress=lambda i, n: seen.append((i, n)))
        self.assertEqual((score.photos, score.hits, score.missed), (2, 1, 1))
        self.assertEqual(score.summary()["recall"], 0.5)
        self.assertEqual(seen[-1], (3, 3))

    def test_a_photo_without_a_size_is_skipped(self):
        score = evaluate(lambda p: ([], NAMES, 0, 0), [(Path("a.jpg"), "")])
        self.assertEqual(score.photos, 0)


if __name__ == "__main__":
    unittest.main()
