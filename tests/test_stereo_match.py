import unittest
from types import SimpleNamespace
from unittest import mock

import numpy as np

from corpse.functions.analysis import analysis
from corpse.functions.analysis.analysis import ObjectAnalyzer, StereoConfig, match_stereo_detections


def det(label, box):
    return analysis.ObjectDetection("t", label, 0.9, box, np.zeros((0, 1, 2), np.int32), ((0, 0), (10, 5), 0),
                                    None, None)


class MatchTest(unittest.TestCase):
    def test_the_same_subject_in_both_views(self):
        left = [det("crab", (200, 100, 300, 200))]
        right = [det("crab", (170, 100, 270, 200))]          # 30 px to the left
        self.assertEqual(match_stereo_detections(left, right), [(0, 0)])

    def test_different_classes_or_wrong_side_do_not_match(self):
        self.assertEqual(match_stereo_detections([det("crab", (200, 100, 300, 200))],
                                                 [det("fish", (170, 100, 270, 200))]), [])
        self.assertEqual(match_stereo_detections([det("crab", (200, 100, 300, 200))],
                                                 [det("crab", (230, 100, 330, 200))]), [])   # negative disparity

    def test_a_different_height_or_size_does_not_match(self):
        left = [det("crab", (200, 100, 300, 200))]
        self.assertEqual(match_stereo_detections(left, [det("crab", (170, 300, 270, 400))]), [])
        self.assertEqual(match_stereo_detections(left, [det("crab", (170, 100, 190, 120))]), [])

    def test_each_subject_is_used_once_and_the_best_fit_wins(self):
        left = [det("crab", (200, 100, 300, 200)), det("crab", (400, 110, 500, 210))]
        right = [det("crab", (365, 112, 465, 212)), det("crab", (170, 100, 270, 200))]
        self.assertEqual(match_stereo_detections(left, right), [(0, 1), (1, 0)])


class AnalyzerTest(unittest.TestCase):
    """The pipeline with a fake model: the right view is searched, and its subjects matched with the left ones."""

    def analyzer(self, detect_right):
        a = ObjectAnalyzer.__new__(ObjectAnalyzer)
        a.device, a.model = "cpu", SimpleNamespace(predict=lambda img, **kw: [img.tag])
        a.stereo_config = StereoConfig(baseline_mm=60, focal_length_px=1000, detect_right=detect_right)
        a._compute_disparity_map = lambda l, r: np.zeros(l.shape[:2], np.float32)      # the dense matching fails
        return a

    def run_pair(self, detect_right):
        class Img(np.ndarray):
            tag = None
        left, right = np.zeros((300, 400, 3), np.uint8).view(Img), np.zeros((300, 400, 3), np.uint8).view(Img)
        left.tag, right.tag = "L", "R"
        boxes = {"L": [det("crab", (200, 100, 300, 200))], "R": [det("crab", (170, 100, 270, 200))]}
        with mock.patch.object(analysis, "_extract_raw_detections", lambda pred, ts: boxes[pred]):
            return self.analyzer(detect_right).analyze_frame_pair("t", right, left)

    def test_a_subject_seen_by_both_cameras_gets_a_depth_when_matching_fails(self):
        res = self.run_pair(True)
        d = res.detections[0]
        self.assertEqual(d.object_disparity_px, 30)
        self.assertAlmostEqual(d.depth_mm, 60 * 1000 / 30)
        self.assertEqual(len(res.right_detections), 1)

    def test_without_the_right_view_nothing_changes(self):
        res = self.run_pair(False)
        self.assertIsNone(res.detections[0].depth_mm)
        self.assertEqual(res.right_detections, [])


if __name__ == "__main__":
    unittest.main()
