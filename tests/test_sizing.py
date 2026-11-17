"""Every window and page must stay usable on a small screen (a 1366x768 laptop, or a window made smaller)."""
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication, QScrollArea, QWidget

from common.ui.layout import Responsive, fit_to_screen, scrollable

app = QApplication.instance() or QApplication([])
SMALL = (1024, 600)                 # the smallest screen the app is expected to run on


def close_later(case, *widgets):
    """Gives Qt back the windows of a test: a suite that keeps hundreds of them alive is heavy and fragile."""
    for w in widgets:
        case.addCleanup(w.deleteLater)
    case.addCleanup(app.processEvents)


def fits(widget, size=SMALL) -> bool:
    m = widget.minimumSizeHint().expandedTo(widget.minimumSize())
    return m.width() <= size[0] and m.height() <= size[1]


class LayoutHelpersTest(unittest.TestCase):
    def test_fit_to_screen_never_exceeds_the_screen(self):
        w = QWidget()
        w.setMinimumSize(3000, 3000)
        fit_to_screen(w, 4000, 4000)
        free = app.primaryScreen().availableGeometry()
        self.assertLessEqual(w.minimumWidth(), free.width())
        self.assertLessEqual(w.height(), free.height())

    def test_fit_to_screen_keeps_a_size_that_fits(self):
        w = QWidget()
        fit_to_screen(w, 400, 300)
        self.assertEqual((w.width(), w.height()), (400, 300))

    def test_scrollable_does_not_pass_on_the_minimum_of_its_content(self):
        big = QWidget()
        big.setMinimumSize(2000, 2000)
        area = scrollable(big)
        self.assertTrue(fits(area))
        self.assertIs(area.widget(), big)

    def test_responsive_hides_below_the_breakpoint(self):
        from PySide6.QtWidgets import QVBoxLayout
        host, side = QWidget(), QWidget()
        QVBoxLayout(host).addWidget(side)
        host.resize(500, 400)
        host.show()
        Responsive(host, 880, [side])
        self.assertFalse(side.isVisibleTo(host))
        host.resize(1000, 400)
        app.processEvents()
        self.assertTrue(side.isVisibleTo(host))


class AnalysisPagesTest(unittest.TestCase):
    def pages(self):
        from corpse.gui.analysis.analysis_gui import StereoAnalysisPage
        from corpse.gui.analysis.photo_gui import PhotoAnalysisPage
        from corpse.gui.analysis.video_gui import VideoAnalysisPage
        from corpse.gui.analysis.video_stereo_gui import VideoStereoAnalysisPage
        return [c(on_home=lambda: None) for c in (StereoAnalysisPage, PhotoAnalysisPage, VideoAnalysisPage,
                                                  VideoStereoAnalysisPage)]

    def test_inside_a_scroll_area_every_analysis_page_fits_a_small_screen(self):
        for page in self.pages():
            area = scrollable(page)
            close_later(self, area)
            self.assertTrue(fits(area), type(page).__name__)


class DialogSizeTest(unittest.TestCase):
    def test_the_login_window_fits_a_small_screen(self):
        from corpse.functions.users.session import Session
        from corpse.functions.users.store import LocalStore
        from corpse.gui.users.login import LoginDialog
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            dlg = LoginDialog(Session(LocalStore(Path(tmp))))
            close_later(self, dlg)
            self.assertTrue(fits(dlg), dlg.minimumSizeHint())
            self.assertLessEqual(dlg.minimumWidth(), 520)

    def test_the_label_editor_and_the_settings_fit(self):
        from PySide6.QtGui import QImage
        from common.ui.label_editor import ImageSource, LabelEditorDialog
        from corpse.gui.settings_dialog import SettingsDialog
        from unittest import mock
        import corpse.gui.settings_dialog as sd
        editor = LabelEditorDialog(ImageSource(QImage(40, 40, QImage.Format.Format_RGB32)), {}, [], lambda r, c: None)
        close_later(self, editor)
        self.assertTrue(fits(editor))
        with mock.patch.object(sd, "HardwareAccelerationWidget", lambda parent=None: QWidget()), \
                mock.patch.object(sd, "LanguageWidget", lambda: QWidget()):
            settings = SettingsDialog(type("S", (), {"server_url": "http://x"})())
        close_later(self, settings)
        self.assertTrue(fits(settings))


class MainWindowTest(unittest.TestCase):
    def test_every_page_of_the_window_is_scrollable_and_the_window_stays_small(self):
        import tempfile
        from unittest import mock
        from corpse.functions.users.session import Session
        from corpse.functions.users.store import LocalStore
        with tempfile.TemporaryDirectory() as tmp:
            session = Session(LocalStore(Path(tmp)))
            from corpse.gui.home import home_gui
            with mock.patch.object(home_gui, "WebcamDemoButton", lambda: QWidget()):
                win = home_gui.AppWindow(session)
            close_later(self, win)
            free = app.primaryScreen().availableGeometry()   # the floor of the window is high, but never higher
            self.assertTrue(fits(win, (free.width(), free.height())), win.minimumSize())
            for i in range(win.stack.count()):
                self.assertIsInstance(win.stack.widget(i), QScrollArea)
            win.show_page(win.training_page)
            self.assertIs(win.current_page(), win.training_page)
            win._go_home()
            self.assertIs(win.current_page(), win.home_page)


class SignOutTest(unittest.TestCase):
    """Signing in and out must not restart the application: the window closes and the login comes back."""

    def window(self, tmp):
        from unittest import mock
        from corpse.functions.users.session import Session
        from corpse.functions.users.store import LocalStore
        from corpse.gui.home import home_gui
        with mock.patch.object(home_gui, "WebcamDemoButton", lambda: QWidget()):
            return home_gui.AppWindow(Session(LocalStore(tmp))), home_gui

    def test_signing_out_closes_the_window_in_the_same_process(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            win, _home_gui = self.window(Path(tmp))
            close_later(self, win)
            win.show()
            self.assertFalse(win.sign_out_requested)
            seen = []
            win.closing.connect(lambda: seen.append(True))   # main.py waits for this, not for app.quit()
            win._sign_out()
            self.assertTrue(win.sign_out_requested)          # main.py will show the login again
            win._finish_sign_out()                           # what the timer does
            self.assertEqual(seen, [True])
            self.assertFalse(win.isVisible())
            self.assertFalse(win.session.logged_in)

    def test_signing_out_from_a_dialog_closes_the_dialog_too(self):
        """Changing server asks for the sign-out from inside the settings dialog: its own event loop must end,
        otherwise the application would stay running with no window at all."""
        import tempfile
        from PySide6.QtWidgets import QDialog
        with tempfile.TemporaryDirectory() as tmp:
            win, _home_gui = self.window(Path(tmp))
            close_later(self, win)
            win.show()
            dialog = QDialog(win)
            dialog.show()
            seen = []
            win.closing.connect(lambda: seen.append(True))
            win._sign_out()
            win._finish_sign_out()
            self.assertFalse(dialog.isVisible())
            self.assertEqual(seen, [True])

    def test_the_main_loop_builds_the_window_again(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            first, _ = self.window(Path(tmp))
            first._finish_sign_out()
            second, _ = self.window(Path(tmp))               # a new window, same process
            close_later(self, first, second)
            self.assertIsNot(first, second)
            self.assertFalse(second.sign_out_requested)


if __name__ == "__main__":
    unittest.main()
