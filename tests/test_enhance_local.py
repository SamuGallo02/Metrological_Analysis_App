"""The improvement done on this computer: the registry of the methods, their settings, and where the copy goes.

The algorithms themselves (the `nautilus` package) are not needed here: a method is only a function that reads a
file and writes another one, so the test registers its own and checks what the application does around it.

Autore: Samuele Gallo
"""
import shutil
import tempfile
import unittest
from pathlib import Path

from common import enhance_nautilus, image_enhance


def a_file(folder: Path, name: str = "a.png", text: str = "original") -> Path:
    path = folder / name
    path.write_text(text, encoding="utf-8")
    return path


class RegistryTest(unittest.TestCase):
    def setUp(self):
        image_enhance.forget_all()

    tearDown = setUp

    def test_a_method_describes_itself_for_the_interface(self):
        params = [{"name": "sharpen", "label": "Sharpening", "type": "float", "default": 0.2, "min": 0, "max": 1}]
        image_enhance.register("quick", lambda src, dst: shutil.copy2(src, dst), label="Quick contrast",
                               description="A fast one.", kind="classical", params=params)
        self.assertEqual(image_enhance.available(), ["quick"])
        method = image_enhance.method("quick")
        self.assertEqual((method.title, method.kind, method.usable), ("Quick contrast", "classical", True))
        self.assertEqual(method.defaults(), {"sharpen": 0.2})
        self.assertEqual(image_enhance.method().name, "quick")        # no name: the first usable one

    def test_a_method_that_cannot_run_here_is_listed_but_not_offered(self):
        image_enhance.register("deep", lambda src, dst: None, label="Deep", problem="weights not downloaded")
        self.assertEqual(image_enhance.available(), [])
        self.assertEqual([m.title for m in image_enhance.methods()], ["Deep"])
        self.assertEqual(image_enhance.methods()[0].problem, "weights not downloaded")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(LookupError):
                image_enhance.improve(a_file(Path(tmp)), "deep")

    def test_the_settings_of_the_user_reach_the_method(self):
        seen = {}

        def run(src, dst, params=None):
            seen.update(params or {})
            dst.write_text(f"{src.read_text(encoding='utf-8')}+{params}", encoding="utf-8")

        image_enhance.register("with_params", run)
        with tempfile.TemporaryDirectory() as tmp:
            media = a_file(Path(tmp))
            out = image_enhance.improve(media, "with_params", params={"sharpen": 0.5})
            self.assertEqual(seen, {"sharpen": 0.5})
            self.assertEqual(out, media.parent / "enhanced" / "a.png")
            self.assertIn("0.5", out.read_text(encoding="utf-8"))

    def test_an_old_method_without_settings_keeps_working(self):
        image_enhance.register("plain", lambda src, dst: shutil.copy2(src, dst))
        with tempfile.TemporaryDirectory() as tmp:
            media = a_file(Path(tmp))
            out = image_enhance.improve(media, params={"ignored": 1})
            self.assertEqual(out.read_text(encoding="utf-8"), "original")

    def test_the_half_written_file_keeps_the_extension_and_is_cleared_away(self):
        """The format comes from the extension, so the temporary file cannot be called '.part' alone."""
        seen = []

        def run(src, dst):
            seen.append(dst.suffix)
            raise RuntimeError("no")

        image_enhance.register("broken", run)
        with tempfile.TemporaryDirectory() as tmp:
            media = a_file(Path(tmp))
            with self.assertRaises(RuntimeError):
                image_enhance.improve(media, "broken")
            self.assertEqual(seen, [".png"])
            self.assertEqual(list((media.parent / "enhanced").glob("*")), [])

    def test_the_copy_can_be_written_somewhere_else(self):
        image_enhance.register("plain", lambda src, dst: shutil.copy2(src, dst))
        with tempfile.TemporaryDirectory() as tmp:
            media = a_file(Path(tmp))
            elsewhere = Path(tmp) / "aside" / "a.png"
            elsewhere.parent.mkdir()
            out = image_enhance.improve(media, dest=elsewhere)
            self.assertEqual(out, elsewhere)
            self.assertFalse((media.parent / "enhanced").exists())     # the original folder is left alone

    def test_an_existing_copy_is_kept_unless_asked(self):
        image_enhance.register("plain", lambda src, dst: dst.write_text("new", encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            media = a_file(Path(tmp))
            first = image_enhance.improve(media)
            first.write_text("old", encoding="utf-8")
            self.assertEqual(image_enhance.improve(media).read_text(encoding="utf-8"), "old")
            self.assertEqual(image_enhance.improve(media, replace=True).read_text(encoding="utf-8"), "new")


class VideoTest(unittest.TestCase):
    def setUp(self):
        image_enhance.forget_all()

    tearDown = setUp

    def test_a_video_is_only_offered_to_a_method_that_can_do_videos(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = a_file(Path(tmp), "dive.mov")
            image_enhance.register("photos_only", lambda src, dst: shutil.copy2(src, dst))
            self.assertFalse(image_enhance.can_improve(video))
            with self.assertRaises(LookupError):
                image_enhance.improve(video, "photos_only")
            image_enhance.register("both", lambda src, dst: shutil.copy2(src, dst), video=True)
            self.assertTrue(image_enhance.can_improve(video))
            self.assertEqual(image_enhance.available(video=True), ["both"])

    def test_the_improved_video_comes_back_as_mp4_and_still_finds_its_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = a_file(Path(tmp), "dive.mov")
            image_enhance.register("both", lambda src, dst: shutil.copy2(src, dst), video=True)
            out = image_enhance.improve(video, "both")
            self.assertEqual(out.name, "dive.mp4")
            self.assertEqual(image_enhance.original_path(out), video)   # the extension changed, the file is found
            self.assertEqual(image_enhance.find_enhanced(video), out)

    def test_an_improved_copy_is_not_improved_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            image_enhance.register("plain", lambda src, dst: shutil.copy2(src, dst))
            media = a_file(Path(tmp))
            copy = image_enhance.improve(media)
            self.assertTrue(image_enhance.is_enhanced(copy))
            self.assertFalse(image_enhance.can_improve(copy))


class NautilusBridgeTest(unittest.TestCase):
    """Without the libraries nothing is registered, and nothing breaks: the application simply does not offer it."""

    def setUp(self):
        image_enhance.forget_all()

    tearDown = setUp

    def test_without_the_libraries_the_improvement_is_simply_not_there(self):
        if enhance_nautilus.possible():
            self.skipTest("the libraries of the models are installed here")
        self.assertEqual(enhance_nautilus.install(reload=True), [])
        self.assertEqual(image_enhance.available(), [])
        self.assertEqual(enhance_nautilus.device_name(), "")

    def test_with_the_libraries_every_model_becomes_a_method(self):
        if not enhance_nautilus.possible():
            self.skipTest("the models of nautilus are not installed here")
        from nautilus import load_models
        names = enhance_nautilus.install(reload=True)
        listed = {m.name for m in image_enhance.methods()}
        self.assertEqual(listed, set(load_models()))                    # all of them, usable or not
        self.assertTrue(set(names) <= listed)
        for name, why in enhance_nautilus.problems().items():
            self.assertTrue(why, f"{name} has no reason for being unusable")
            self.assertNotIn(name, names)


if __name__ == "__main__":
    unittest.main()
