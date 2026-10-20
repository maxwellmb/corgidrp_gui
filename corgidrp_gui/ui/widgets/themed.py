"""Small widgets that carry the parts of a theme a Qt stylesheet cannot express.

* :class:`SectionLabel` - text case and letter-spacing per theme.
* :class:`Panel` - ``QFrame[role="panel"]`` that gets the soft shadow when the theme has one.
* :class:`Chip`, :func:`step_label` - status chips and step-strip labels.
* :class:`TileButton` - a big two-line button (bold title, one-line subtitle).
* :class:`ElidedLabel` - single-line label that elides long paths in the middle.
* :class:`RainbowRule` - the 6px rainbow stripe some themes draw under the menu bar.
"""

from __future__ import annotations

from qtpy import QtCore, QtGui, QtWidgets

from ... import theming


class SectionLabel(QtWidgets.QLabel):
    """``QLabel[role="section"]``; applies the theme's label case and tracking."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._raw = text
        self.setProperty("role", "section")
        self.apply_theme_text(theming.current_theme())

    def raw_text(self) -> str:
        return self._raw

    def setRawText(self, text: str) -> None:
        self._raw = text
        self.apply_theme_text(theming.current_theme())

    def apply_theme_text(self, theme) -> None:
        self.setText(theming.label_text(self._raw, theme))
        self._tracking = theme.type.label_tracking * (theme.type.label_size or theme.type.size)
        self._apply_tracking()

    def _apply_tracking(self) -> None:
        f = self.font()
        if abs(f.letterSpacing() - self._tracking) > 1e-3 or (
                f.letterSpacingType() != QtGui.QFont.SpacingType.AbsoluteSpacing):
            f.setLetterSpacing(QtGui.QFont.SpacingType.AbsoluteSpacing, self._tracking)
            self.setFont(f)

    def changeEvent(self, event):
        super().changeEvent(event)
        # the stylesheet re-resolves the font on polish; re-add tracking afterwards
        if event.type() in (QtCore.QEvent.Type.StyleChange, QtCore.QEvent.Type.FontChange):
            if hasattr(self, "_tracking"):
                self._apply_tracking()


class Panel(QtWidgets.QFrame):
    """``QFrame[role="panel"]`` with a layout; decorated with the theme's shadow."""

    def __init__(self, parent=None, layout: str = "v"):
        super().__init__(parent)
        self.setProperty("role", "panel")
        theme = theming.current_theme()
        if layout == "v":
            QtWidgets.QVBoxLayout(self)
        elif layout == "h":
            QtWidgets.QHBoxLayout(self)
        else:
            QtWidgets.QGridLayout(self)
        self.apply_density(theme)
        theming.decorate_panel(self, theme)

    def apply_density(self, theme) -> None:
        pad = theme.density.padding
        lay = self.layout()
        lay.setContentsMargins(pad, pad, pad, pad)
        lay.setSpacing(theme.density.gap)

    def apply_theme_text(self, theme) -> None:  # called by theming.decorate_tree
        self.apply_density(theme)


def section(title: str, body: QtWidgets.QWidget, parent=None) -> QtWidgets.QWidget:
    """A section label stacked above ``body`` (usually a :class:`Panel`)."""
    w = QtWidgets.QWidget(parent)
    lay = QtWidgets.QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)
    lay.addWidget(SectionLabel(title))
    lay.addWidget(body, 1)
    return w


class Chip(QtWidgets.QLabel):
    """Status chip: ``QLabel[chip="ok|warn|err|run|dim"]``."""

    KINDS = ("ok", "warn", "err", "run", "dim")

    def __init__(self, text: str, kind: str = "dim", parent=None):
        super().__init__(text, parent)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        self.set_kind(kind)

    def set_kind(self, kind: str) -> None:
        if kind not in self.KINDS:
            raise ValueError(kind)
        self.setProperty("chip", kind)
        theming.repolish(self)


def step_label(text: str, state: str) -> QtWidgets.QLabel:
    """A step-strip label: ``QLabel[step="done|running|pending"]``."""
    lab = QtWidgets.QLabel(text)
    lab.setProperty("step", state)
    lab.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    if state == "running":
        lab.setProperty("glow", True)
    return lab


class TileButton(QtWidgets.QPushButton):
    """Large button with a bold title and a one-line subtitle."""

    def __init__(self, title: str, subtitle: str, parent=None, primary: bool = False):
        super().__init__(parent)
        self.setProperty("tile", "true")
        if primary:
            self.setProperty("role", "primary")
            self.setProperty("glow", True)
        self.setAccessibleName(f"{title}: {subtitle}")
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                           QtWidgets.QSizePolicy.Policy.Expanding)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setSpacing(1)
        self.title_label = QtWidgets.QLabel(title)
        self.title_label.setProperty("role", "tile_title")
        self.subtitle_label = QtWidgets.QLabel(subtitle)
        self.subtitle_label.setProperty("role", "tile_subtitle")
        lay.addStretch(1)
        for lab in (self.title_label, self.subtitle_label):
            lab.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            lay.addWidget(lab)
        lay.addStretch(1)
        self.apply_theme_text(theming.current_theme())

    def apply_theme_text(self, theme) -> None:
        pad = theme.density.padding
        self.layout().setContentsMargins(pad + 6, pad, pad + 6, pad)
        self.setMinimumHeight(theme.density.row_height + 2 * pad + 8)
        self._hint_h = 2 * theme.density.row_height + 2 * pad
        self.updateGeometry()

    def sizeHint(self):
        return self.layout().sizeHint().expandedTo(QtCore.QSize(180, self._hint_h))

    def minimumSizeHint(self):
        return self.layout().minimumSize()


class ElidedLabel(QtWidgets.QLabel):
    """Single-line label that elides its text (middle by default); full text in the tooltip."""

    def __init__(self, text: str = "", parent=None,
                 mode=QtCore.Qt.TextElideMode.ElideMiddle):
        super().__init__(parent)
        self._full = ""
        self._mode = mode
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored,
                           QtWidgets.QSizePolicy.Policy.Preferred)
        self.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.setFullText(text)

    def fullText(self) -> str:
        return self._full

    def setFullText(self, text: str) -> None:
        self._full = text
        self.setToolTip(text)
        self._elide()

    def _elide(self) -> None:
        fm = QtGui.QFontMetrics(self.font())
        width = max(self.contentsRect().width(), 20)
        super().setText(fm.elidedText(self._full, self._mode, width))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QtCore.QEvent.Type.FontChange, QtCore.QEvent.Type.StyleChange):
            self._elide()

    def minimumSizeHint(self):
        return QtCore.QSize(20, super().minimumSizeHint().height())


class RainbowRule(QtWidgets.QWidget):
    """A 6px repeating rainbow stripe (themes with ``[extras] rainbow_rule = true``)."""

    HEIGHT = 6
    BAND = 14

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(self.HEIGHT)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                           QtWidgets.QSizePolicy.Policy.Fixed)

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        colors = [QtGui.QColor(c) for c in theming.RAINBOW]
        x, i, w = 0, 0, self.width()
        while x < w:
            p.fillRect(x, 0, self.BAND, self.height(), colors[i % len(colors)])
            x += self.BAND
            i += 1
        p.end()
