import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def catalog():
    from corgidrp_gui.core.steps import StepCatalog
    return StepCatalog()


@pytest.fixture(scope="session")
def mock_l1_files(tmp_path_factory):
    """Two small mock L1 frames made with corgidrp.mocks (headers only matter here)."""
    import corgidrp.mocks as mocks
    d = tmp_path_factory.mktemp("l1")
    ds = mocks.create_prescan_files(filedir=str(d), numfiles=2)
    return sorted(str(f.filepath) for f in ds)


@pytest.fixture(scope="session", autouse=True)
def _close_qt_windows_at_exit():
    yield
    try:
        from qtpy import QtWidgets
    except ImportError:  # pragma: no cover
        return
    app = QtWidgets.QApplication.instance()
    if app is None:
        return
    for w in app.topLevelWidgets():
        w.close()
        w.deleteLater()
    app.processEvents()
    app.processEvents()
