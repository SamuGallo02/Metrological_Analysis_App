import unittest

from corpse.gui.users.labels import area_label, folder_label, path_label


class LabelsTest(unittest.TestCase):
    def test_the_internal_quarantine_folder_has_a_readable_name(self):
        self.assertEqual(folder_label("_pending"), "Awaiting approval")
        self.assertEqual(folder_label("Pinna nobilis"), "Pinna nobilis")

    def test_a_path_is_shown_with_readable_names(self):
        self.assertEqual(path_label("_pending/mario/Pinna nobilis"),
                         "Awaiting approval / mario / Pinna nobilis")
        self.assertEqual(path_label(""), "")

    def test_every_media_area_has_a_label(self):
        self.assertEqual([area_label(a) for a in ("photos", "stereo", "videos")], ["Photos", "Stereo photos", "Videos"])
