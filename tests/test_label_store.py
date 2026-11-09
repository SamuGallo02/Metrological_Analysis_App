import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from common.label_store import (class_list, find_labels, label_paths, save_labels, sidecars, yolo_box_line,
                                yolo_polygon_line)
from corpse.functions.analysis.label_export import LabelRecorder, model_class_names, save_media_labels
from corpse.functions.users.yolo_labels import parse_labels


class LabelLinesTest(unittest.TestCase):
    def test_box_is_normalised_and_clipped(self):
        self.assertEqual(yolo_box_line(2, (10, 20, 30, 60), 100, 200), "2 0.200000 0.200000 0.200000 0.200000")
        self.assertEqual(yolo_box_line(0, (-50, -50, 50, 50), 100, 100), "0 0.250000 0.250000 0.500000 0.500000")

    def test_polygon(self):
        line = yolo_polygon_line(1, [(0, 0), (100, 0), (100, 50)], 100, 100)
        self.assertEqual(line, "1 0.000000 0.000000 1.000000 0.000000 1.000000 0.500000")
        with self.assertRaises(ValueError):
            yolo_polygon_line(0, [(0, 0), (1, 1)], 10, 10)

    def test_the_viewer_reads_what_the_analysis_writes(self):
        shapes = parse_labels(yolo_box_line(3, (10, 10, 50, 30), 100, 100) + "\n"
                              + yolo_polygon_line(1, [(0, 0), (50, 0), (50, 50)], 100, 100))
        self.assertEqual([s.cls for s in shapes], [3, 1])
        self.assertTrue(shapes[0].is_box and not shapes[1].is_box)


class LabelStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name) / "labels"
        self.media = Path(self.tmp.name) / "photos" / "a.jpg"
        self.media.parent.mkdir()
        self.media.write_bytes(b"x")

    def test_saved_labels_are_found_by_media_path(self):
        self.assertIsNone(find_labels(self.media, self.base))
        save_labels(self.media, ["0 .5 .5 .1 .1"], ["crab", "fish"], self.base)
        label, names = find_labels(self.media, self.base)
        self.assertEqual(label.read_text(), "0 .5 .5 .1 .1\n")
        self.assertEqual(class_list(names.read_text()), ["crab", "fish"])
        self.assertEqual(list(self.media.parent.iterdir()), [self.media])      # nothing is written next to the photo

    def test_two_files_with_the_same_name_do_not_share_labels(self):
        other = Path(self.tmp.name) / "other" / "a.jpg"
        other.parent.mkdir()
        other.write_bytes(b"y")
        self.assertNotEqual(label_paths(self.media, self.base), label_paths(other, self.base))

    def test_saving_again_replaces_the_labels(self):
        save_labels(self.media, ["0 1 1 1 1"], ["a"], self.base)
        save_labels(self.media, [], ["a"], self.base)
        self.assertEqual(find_labels(self.media, self.base)[0].read_text(), "")

    def test_a_label_beside_the_media_wins(self):
        save_labels(self.media, ["saved"], ["x"], self.base)
        label, classes = sidecars(self.media, self.base)
        self.assertEqual(label.read_text(), "saved\n")
        self.media.with_suffix(".txt").write_text("beside")
        (self.media.parent / "classes.txt").write_text("beside-class")
        label, classes = sidecars(self.media, self.base)
        self.assertEqual((label.read_text(), classes.read_text()), ("beside", "beside-class"))

    def test_no_labels_no_sidecars(self):
        self.assertEqual(sidecars(self.media, self.base), (None, None))


class LabelRecorderTest(unittest.TestCase):
    def det(self, label, contour=None, bbox=(10, 10, 30, 30)):
        return SimpleNamespace(label=label, contour=contour, bbox_xyxy=bbox)

    def test_class_numbers_follow_the_model_and_grow(self):
        rec = LabelRecorder(["crab", "fish"])
        self.assertEqual((rec.class_id("Fish"), rec.class_id("crab"), rec.class_id("urchin")), (1, 0, 2))
        self.assertEqual(rec.classes, ["crab", "fish", "urchin"])

    def test_polygon_when_there_is_a_contour_else_the_box(self):
        contour = np.array([[[0, 0]], [[50, 0]], [[50, 50]], [[0, 50]]], dtype=np.int32)
        rec = LabelRecorder(["crab"])
        lines = rec.lines_for([self.det("crab", contour), self.det("crab", None)], 100, 100)
        self.assertEqual(len(lines[0].split()), 1 + 2 * 4)                        # class + 4 points
        self.assertEqual(lines[1], "0 0.200000 0.200000 0.200000 0.200000")       # box

    def test_video_lines_start_with_the_frame(self):
        lines = LabelRecorder(["crab"]).lines_for([self.det("crab")], 100, 100, frame=7)
        self.assertTrue(lines[0].startswith("7 0 "))

    def test_model_class_names(self):
        self.assertEqual(model_class_names(SimpleNamespace(model=SimpleNamespace(names={1: "b", 0: "a"}))), ["a", "b"])
        self.assertEqual(model_class_names(SimpleNamespace()), [])

    def test_a_failure_to_save_does_not_stop_the_analysis(self):
        import common.label_store as store
        from unittest import mock
        with mock.patch.object(store, "save_labels", side_effect=OSError("disk full")), \
                mock.patch("corpse.functions.analysis.label_export.save_labels", side_effect=OSError("disk full")):
            save_media_labels("x.jpg", [], [])                                    # must not raise


if __name__ == "__main__":
    unittest.main()
