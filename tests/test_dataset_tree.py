import tempfile
import unittest
from pathlib import Path

from server.dataset_tree import validate_dataset_dir


class DatasetTreeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def make(self, *names):
        for name in names:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x")

    def problems(self):
        return validate_dataset_dir(self.root)

    def test_a_flat_dataset_is_valid(self):
        self.make("data.yaml", "images/a.jpg", "images/b.png", "labels/a.txt", "labels/b.txt")
        self.assertEqual(self.problems(), [])

    def test_a_dataset_with_train_and_val_folders_is_valid(self):
        self.make("data.yaml", "images/train/a.jpg", "images/val/b.jpg", "labels/train/a.txt", "labels/val/b.txt")
        self.assertEqual(self.problems(), [])

    def test_the_other_usual_layout_is_valid(self):
        self.make("data.yaml", "train/images/a.jpg", "train/labels/a.txt", "val/images/b.jpg", "val/labels/b.txt")
        self.assertEqual(self.problems(), [])

    def test_data_yml_is_accepted_and_other_files_are_ignored(self):
        self.make("data.yml", "README.md", "classes.txt", "images/a.jpg", "labels/a.txt")
        self.assertEqual(self.problems(), [])

    def test_a_dataset_without_data_yaml_is_not_valid(self):
        self.make("images/a.jpg", "labels/a.txt")
        self.assertEqual([e.key for e in self.problems()], ["The dataset must contain a data.yaml file."])

    def test_a_dataset_without_images_is_not_valid(self):
        self.make("data.yaml", "labels/a.txt")
        self.assertEqual([e.key for e in self.problems()], ["The dataset contains no images."])

    def test_an_image_without_its_label_is_reported(self):
        self.make("data.yaml", "images/a.jpg", "images/b.jpg", "labels/a.txt")
        (error,) = self.problems()
        self.assertEqual(error.key, "Images and labels must correspond one to one: "
                                    "{n} images have no label (for example {example}).")
        self.assertEqual((error.params["n"], error.params["example"]), (1, "images/b.jpg"))

    def test_a_label_without_its_image_is_reported(self):
        self.make("data.yaml", "images/a.jpg", "labels/a.txt", "labels/c.txt")
        (error,) = self.problems()
        self.assertEqual(error.key, "Images and labels must correspond one to one: "
                                    "{n} labels have no image (for example {example}).")
        self.assertEqual((error.params["n"], error.params["example"]), (1, "labels/c.txt"))

    def test_an_image_outside_an_images_folder_has_no_label(self):
        self.make("data.yaml", "a.jpg", "labels/a.txt")
        keys = [e.key for e in self.problems()]
        self.assertEqual(len(keys), 2)                              # the image has no label and the label has no image