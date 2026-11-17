"""PySide6 windows of the Users page.

Autore: Samuele Gallo
"""
from .account_bar import AccountBar
from .browser import ServerFoldersWidget, ServerBrowserWidget
from .folders_local import LocalFoldersWidget
from .folders_page import FoldersPage
from .groups_page import GroupsPage
from .login import LoginDialog
from .profile import ProfilePage
from .transfer import TransferDialog
from .uploads import UploadsWidget
from .preview_dialog import PreviewDialog
from .catalog import CatalogWidget
from .image_viewer import ImageViewerDialog

try:                                              # the administrator screens are not part of the user edition
    from .admin import AdminHome, UserAdminWidget, SubmissionsWidget, ReviewWidget
except ImportError:
    AdminHome = UserAdminWidget = SubmissionsWidget = ReviewWidget = None

__all__ = ["AccountBar", "AdminHome", "UserAdminWidget", "SubmissionsWidget", "ReviewWidget", "ServerFoldersWidget", "FoldersPage", "LocalFoldersWidget", "GroupsPage", "ServerBrowserWidget",
           "LoginDialog", "ProfilePage", "TransferDialog", "UploadsWidget", "PreviewDialog", "CatalogWidget", "ImageViewerDialog"]
