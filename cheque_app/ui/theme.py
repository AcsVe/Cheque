"""The application's look: one palette (the appace/SAS colours used by the user's other systems), one control height,
an application stylesheet, line icons drawn from inline SVG, and small helpers that build labelled, accessible
controls so every window is laid out the same way."""
from PySide6.QtCore import QByteArray, QEvent, QObject, QPoint, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QAbstractScrollArea, QAbstractSpinBox, QApplication,
                               QCalendarWidget, QComboBox, QDialogButtonBox, QFontComboBox, QFrame, QGridLayout,
                               QGroupBox, QLabel, QLayout, QLineEdit, QPushButton, QScrollArea, QSizePolicy,
                               QToolBar, QWidget)

C = {
    'primary': '#0C67EC', 'deep': '#0847B0', 'soft': '#e8f1fe', 'text': '#1e293b', 'muted': '#64748b',
    'border': '#d5deea', 'page': '#f4f7fb', 'card': '#ffffff', 'field': '#ffffff', 'readonly': '#f1f5f9',
    'danger': '#b42318', 'danger_soft': '#fdecea', 'ok': '#166534', 'ok_soft': '#e7f6ee', 'warn': '#8a5a00',
    'warn_soft': '#fff4e0',
}
CONTROL_H = 34          # the smallest height of a line edit, combo box, spin box, date edit and button
COMPACT_H = 28          # the smallest height of a filter inside a table header
REF_DIGIT = 7.5         # width of «0» in the 10 pt UI font the fixed widths below were drawn for


def control_height(font_or_widget=None, compact=False):
    """The height of a control for its font: never less than the design height, and always tall enough for the
    font Windows really uses (larger text size, 125 % / 150 % display scaling, Arabic glyphs with tall marks)."""
    if isinstance(font_or_widget, QWidget):
        fm = font_or_widget.fontMetrics()
    else:
        fm = QFontMetrics(font_or_widget or QApplication.font())
    if compact:
        return max(COMPACT_H, fm.height() + 10)
    return max(CONTROL_H, fm.height() + 16)


def font_scale(widget=None):
    """How much wider digits are than in the font the fixed widths were drawn for (1 = the same or narrower)."""
    fm = widget.fontMetrics() if widget is not None else QFontMetrics(QApplication.font())
    return max(1.0, fm.horizontalAdvance('0') / REF_DIGIT)

STYLE = f"""
QMainWindow, QDialog {{ background: {C['page']}; }}
QToolTip {{ background: {C['text']}; color: #fff; border: 0; padding: 5px 8px; border-radius: 6px; }}
QMenuBar {{ background: {C['card']}; border-bottom: 1px solid {C['border']}; padding: 2px 6px; }}
QMenuBar::item {{ padding: 6px 12px; border-radius: 6px; color: {C['text']}; }}
QMenuBar::item:selected {{ background: {C['soft']}; color: {C['deep']}; }}

QTabWidget::pane {{ border: 1px solid {C['border']}; border-radius: 10px; background: {C['page']}; top: -1px; }}
QTabBar::tab {{ padding: 9px 20px; margin: 0 2px; color: {C['muted']}; font-weight: 600; background: transparent;
               border: 1px solid transparent; border-top-left-radius: 8px; border-top-right-radius: 8px; }}
QTabBar::tab:selected {{ background: {C['page']}; color: {C['primary']}; border-color: {C['border']};
                        border-bottom-color: {C['page']}; }}
QTabBar::tab:hover:!selected {{ color: {C['deep']}; background: {C['soft']}; }}

QGroupBox {{ background: {C['card']}; border: 1px solid {C['border']}; border-radius: 10px; margin-top: 24px;
            padding: 10px 12px 12px 12px; font-weight: 600; color: {C['text']}; }}
QGroupBox[plain="true"] {{ margin-top: 8px; padding-top: 12px; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; left: 10px; right: 10px;
                   padding: 2px 4px; color: {C['deep']}; }}
QGroupBox QLabel {{ font-weight: normal; }}
QLabel {{ color: {C['text']}; }}
QLabel[muted="true"] {{ color: {C['muted']}; }}
QLabel[hint="true"] {{ color: {C['muted']}; background: {C['card']}; border: 1px solid {C['border']};
                      border-radius: 8px; padding: 8px 12px; }}
QLabel#status {{ padding: 6px 12px; border-radius: 8px; background: {C['ok_soft']}; color: {C['ok']}; }}
QLabel#status[warn="true"] {{ background: {C['warn_soft']}; color: {C['warn']}; }}
QLabel[chip="true"] {{ padding: 4px 12px; border-radius: 8px; background: {C['soft']}; color: {C['deep']};
                      font-weight: 600; }}

QLineEdit, QComboBox, QAbstractSpinBox, QPlainTextEdit, QListWidget {{
    background: {C['field']}; color: {C['text']}; border: 1px solid {C['border']}; border-radius: 8px;
    selection-background-color: {C['primary']}; selection-color: #fff; }}
QLineEdit, QComboBox, QAbstractSpinBox {{ padding: 0 10px; }}
QPlainTextEdit {{ padding: 6px; }}
QLineEdit:focus, QComboBox:focus, QAbstractSpinBox:focus, QPlainTextEdit:focus, QListWidget:focus {{
    border: 1px solid {C['primary']}; }}
QLineEdit:read-only {{ background: {C['readonly']}; color: #334155; }}
QLineEdit:disabled, QComboBox:disabled, QAbstractSpinBox:disabled {{ background: {C['readonly']}; color: #94a3b8; }}
QLineEdit[compact="true"], QComboBox[compact="true"] {{ border-radius: 6px; padding: 0 6px; }}
QComboBox QAbstractItemView {{ border: 1px solid {C['border']}; selection-background-color: {C['soft']};
                               selection-color: {C['text']}; outline: 0; }}
QListWidget {{ padding: 4px; outline: 0; }}
QListWidget::item {{ padding: 6px 8px; border-radius: 6px; }}
QListWidget::item:selected {{ background: {C['soft']}; color: {C['deep']}; }}

QPushButton {{ background: {C['card']}; color: {C['deep']}; border: 1px solid {C['border']}; border-radius: 8px;
              padding: 0 14px; font-weight: 600; }}
QPushButton:hover {{ background: {C['soft']}; border-color: #b9cdf0; }}
QPushButton:pressed {{ background: #d6e6fd; }}
QPushButton:focus {{ border-color: {C['primary']}; }}
QPushButton:disabled {{ color: #a0aec0; background: #f8fafc; border-color: #e2e8f0; }}
QPushButton[primary="true"] {{ background: {C['primary']}; color: #fff; border-color: {C['primary']}; }}
QPushButton[primary="true"]:hover {{ background: {C['deep']}; border-color: {C['deep']}; }}
QPushButton[primary="true"]:focus {{ border: 2px solid {C['deep']}; }}
QPushButton[primary="true"]:disabled {{ background: #9dbcf2; border-color: #9dbcf2; color: #fff; }}
QPushButton[danger="true"] {{ color: {C['danger']}; border-color: #f3c3bd; }}
QPushButton[danger="true"]:hover {{ background: {C['danger_soft']}; }}
QPushButton[danger="true"]:disabled {{ color: #e3a8a1; border-color: #f6dcd8; background: #fff; }}
QPushButton[ghost="true"] {{ background: transparent; border-color: transparent; color: {C['deep']}; padding: 0 8px; }}
QPushButton[ghost="true"]:hover {{ background: {C['soft']}; }}
QPushButton[iconOnly="true"] {{ padding: 0; }}

QComboBox::drop-down, QDateEdit::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right;
    width: 26px; border: 0; }}
QComboBox::down-arrow, QDateEdit::down-arrow {{ image: url(@ARROW_DOWN@); width: 12px; height: 12px; }}
QComboBox::down-arrow:disabled, QDateEdit::down-arrow:disabled {{ image: url(@ARROW_DOWN_OFF@); }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ subcontrol-origin: border; width: 22px; border: 0;
    background: transparent; }}
QAbstractSpinBox::up-button {{ subcontrol-position: top right; margin-top: 3px; }}
QAbstractSpinBox::down-button {{ subcontrol-position: bottom right; margin-bottom: 3px; }}
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{ background: {C['soft']}; border-radius: 4px; }}
QAbstractSpinBox::up-arrow {{ image: url(@ARROW_UP@); width: 10px; height: 10px; }}
QAbstractSpinBox::down-arrow {{ image: url(@ARROW_DOWN@); width: 10px; height: 10px; }}
QAbstractSpinBox::up-arrow:disabled, QAbstractSpinBox::up-arrow:off {{ image: url(@ARROW_UP_OFF@); }}
QAbstractSpinBox::down-arrow:disabled, QAbstractSpinBox::down-arrow:off {{ image: url(@ARROW_DOWN_OFF@); }}
QDateEdit[calendarPopup="true"] {{ padding-right: 4px; }}

QCheckBox, QRadioButton {{ spacing: 8px; color: {C['text']}; padding: 3px 0; }}

QTableView {{ background: {C['card']}; border: 1px solid {C['border']}; border-radius: 8px;
             gridline-color: #edf1f7; selection-background-color: {C['soft']}; selection-color: {C['text']};
             alternate-background-color: #f8fafc; }}
QHeaderView {{ background: {C['soft']}; border: 0; }}
QHeaderView::section {{ background: {C['soft']}; color: {C['deep']}; font-weight: 600; padding: 6px 8px; border: 0;
                       border-bottom: 1px solid {C['border']}; border-left: 1px solid #d9e6fb; }}
QScrollArea, QScrollArea > QWidget > QWidget#page {{ background: {C['page']}; }}
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:hover {{ background: {C['soft']}; }}
QGraphicsView {{ border: 1px solid {C['border']}; border-radius: 8px; background: #eef2f7; }}
"""

# ── icons: 24×24 line drawings, coloured on demand ──────────────────────────────────────────────
_ICONS = {
    'save': '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><path d="M17 21v-8H7v8"/><path d="M7 3v5h8"/>',
    'print': '<path d="M6 9V2h12v7"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><path d="M6 14h12v8H6z"/>',
    'preview': '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    'reprint': '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>',
    'new': '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M12 12v6M9 15h6"/>',
    'plus': '<path d="M12 5v14M5 12h14"/>',
    'search': '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
    'export': '<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M5 21h14"/>',
    'import': '<path d="M12 21V9"/><path d="M7 14l5-5 5 5"/><path d="M5 3h14"/>',
    'copy': '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    'key': '<circle cx="7.5" cy="15.5" r="4.5"/><path d="M10.7 12.3L21 2"/><path d="M16 7l3 3"/><path d="M18.5 4.5l2 2"/>',
    'trash': '<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>',
    'cancel': '<circle cx="12" cy="12" r="9"/><path d="M15 9l-6 6M9 9l6 6"/>',
    'check': '<path d="M20 6L9 17l-5-5"/>',
    'edit': '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
    'folder': '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    'image': '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/>',
    'grid': '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18M15 3v18"/>',
    'reset': '<path d="M9 14L4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/>',
    'star': '<path d="M12 3l2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2L3 9.6l6.2-.9z"/>',
    'on': '<circle cx="12" cy="12" r="9"/><path d="M8 12l3 3 5-6"/>',
    'off': '<circle cx="12" cy="12" r="9"/><path d="M5.7 5.7l12.6 12.6"/>',
    'select_all': '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M8 12l3 3 5-6"/>',
    'select_none': '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M8 12h8"/>',
    'bank': '<path d="M3 21h18"/><path d="M4 10h16"/><path d="M12 3l9 5H3z"/><path d="M6 10v8M10 10v8M14 10v8M18 10v8"/>',
    'calibrate': '<path d="M3 3h18v18H3z"/><path d="M3 8h4M3 13h6M3 18h4M8 3v4M13 3v6M18 3v4"/>',
    'move': '<path d="M12 2v20M2 12h20"/><path d="M9 5l3-3 3 3M9 19l3 3 3-3M5 9l-3 3 3 3M19 9l3 3-3 3"/>',
    'close': '<path d="M18 6L6 18M6 6l12 12"/>',
    'chevron_down': '<path d="M6 9l6 6 6-6"/>',
    'chevron_up': '<path d="M6 15l6-6 6 6"/>',
    'align_left': '<path d="M4 3v18"/><path d="M8 6h11v4H8z"/><path d="M8 14h6v4H8z"/>',
    'align_right': '<path d="M20 3v18"/><path d="M5 6h11v4H5z"/><path d="M10 14h6v4h-6z"/>',
    'align_top': '<path d="M3 4h18"/><path d="M6 8h4v11H6z"/><path d="M14 8h4v6h-4z"/>',
    'align_bottom': '<path d="M3 20h18"/><path d="M6 5h4v11H6z"/><path d="M14 10h4v6h-4z"/>',
    'same_width': '<path d="M3 5v14M21 5v14"/><path d="M6 12h12"/><path d="M9 9l-3 3 3 3M15 9l3 3-3 3"/>',
    'same_height': '<path d="M5 3h14M5 21h14"/><path d="M12 6v12"/><path d="M9 9l3-3 3 3M9 15l3 3 3-3"/>',
    'dist_h': '<path d="M4 3v18M20 3v18"/><path d="M10 7h4v10h-4z"/>',
    'dist_v': '<path d="M3 4h18M3 20h18"/><path d="M7 10h10v4H7z"/>',
}
_CACHE = {}


def icon(name, color=None):
    """A crisp line icon at every size, with a grey variant for disabled buttons."""
    color = color or C['deep']
    key = (name, color)
    if key in _CACHE:
        return _CACHE[key]
    from PySide6.QtSvg import QSvgRenderer
    body = _ICONS.get(name, _ICONS['check'])
    ic = QIcon()
    for mode, col in ((QIcon.Normal, color), (QIcon.Disabled, '#a0aec0')):
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="%s" stroke-width="2" '
               'stroke-linecap="round" stroke-linejoin="round">%s</svg>' % (col, body))
        r = QSvgRenderer(QByteArray(svg.encode()))
        for px in (16, 20, 24, 32, 48):
            pm = QPixmap(px, px)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            r.render(p, QRectF(0, 0, px, px))
            p.end()
            ic.addPixmap(pm, mode)
    _CACHE[key] = ic
    return ic


# ── helpers ─────────────────────────────────────────────────────────────────────────────────────
def a11y(w, name, desc=None):
    """Accessible name (what a screen reader announces) and optional description, returned for chaining."""
    w.setAccessibleName(name)
    if desc:
        w.setAccessibleDescription(desc)
    return w


def button(text, icon_name=None, kind='secondary', tip=None, desc=None):
    """kind: 'primary' (one per window), 'secondary', 'danger' or 'ghost'."""
    b = QPushButton((' ' + text) if icon_name else text)      # a little room between the icon and the text
    if kind in ('primary', 'danger', 'ghost'):
        b.setProperty(kind, True)
    if icon_name:
        col = '#ffffff' if kind == 'primary' else (C['danger'] if kind == 'danger' else C['deep'])
        b.setIcon(icon(icon_name, col))
        b.setIconSize(QSize(18, 18))
    if tip:
        b.setToolTip(tip)
    b.setCursor(Qt.PointingHandCursor)
    return a11y(b, text.replace('&&', '&'), desc or tip)


def icon_button(icon_name, tip, kind='secondary'):
    """A square button with only an icon — its tooltip and accessible name say what it does."""
    b = QPushButton()
    if kind != 'secondary':
        b.setProperty(kind, True)
    b.setProperty('iconOnly', True)
    b.setIcon(icon(icon_name, '#ffffff' if kind == 'primary' else C['deep']))
    b.setIconSize(QSize(18, 18))
    b.setFixedWidth(control_height(b))     # kept square by the sizer once the real font is known
    b.setToolTip(tip)
    b.setCursor(Qt.PointingHandCursor)
    return a11y(b, tip)


def name_buttons(box: QDialogButtonBox):
    """Give the standard buttons of a dialog button box accessible names (their visible text)."""
    for b in box.buttons():
        b.setAccessibleName(b.text().replace('&', ''))
        b.setCursor(Qt.PointingHandCursor)
    return box


def fit(w, width):
    """Size a field to its content: ``width`` (drawn for the 10 pt font) grows with the real font, and never cuts
    the widest value, date or option the field can show."""
    w.setProperty('fitWidth', int(width))
    w.setFixedWidth(int(width))
    return w


def ltr(w, width=None):
    """Numbers, dates and codes read left to right; ``width`` sizes the field to its content (see ``fit``)."""
    w.setLayoutDirection(Qt.LeftToRight)
    if width:
        fit(w, width)
    return w


def scroll_page(page, horizontal=True):
    """Put a page in a scroll area so a small screen or a large text size never hides the end of a window — the
    mouse wheel (or the scroll bar) reaches every field and button."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    if not horizontal:
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    if not page.objectName():
        page.setObjectName('page')
    area.setWidget(page)
    if page.accessibleName():
        area.setAccessibleName(page.accessibleName())
    return area


class FlowLayout(QLayout):
    """Buttons side by side that move to a new line when the window is too narrow, so none is cut off. Follows the
    layout direction (right to left in Arabic)."""

    def __init__(self, parent=None, spacing=8):
        super().__init__(parent)
        self._items = []
        self._sp = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._place(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._place(rect, False)

    def sizeHint(self):
        w = sum(it.sizeHint().width() for it in self._items) + self._sp * max(0, len(self._items) - 1)
        h = max((it.sizeHint().height() for it in self._items), default=0)
        return QSize(w, h)

    def minimumSize(self):
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        return s

    def _place(self, rect, test):
        owner = self.parentWidget()
        rtl = (owner.layoutDirection() if owner is not None else QApplication.layoutDirection()) == Qt.RightToLeft
        x, y, line_h = 0, rect.y(), 0
        for it in self._items:
            hint_ = it.sizeHint()
            if x and x + hint_.width() > rect.width():
                x, y, line_h = 0, y + line_h + self._sp, 0
            if not test:
                left = rect.right() - x - hint_.width() + 1 if rtl else rect.x() + x
                it.setGeometry(QRect(QPoint(left, y), hint_))
            x += hint_.width() + self._sp
            line_h = max(line_h, hint_.height())
        return y + line_h - rect.y()


def flow_row(widgets, spacing=8):
    """A widget holding ``widgets`` in a FlowLayout (they wrap onto more lines when there is not enough width)."""
    box = QWidget()
    lay = FlowLayout(box, spacing)
    for w in widgets:
        lay.addWidget(w)
    sp = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
    sp.setHeightForWidth(True)
    box.setSizePolicy(sp)
    return box


def fit_to_screen(win, width, height):
    """Open ``win`` at ``width``×``height``, or smaller when the screen (after Windows scaling and the taskbar) is
    smaller, so its title bar and buttons are never off the screen."""
    scr = win.screen() if win.screen() is not None else QGuiApplication.primaryScreen()
    if scr is None:
        win.resize(width, height)
        return
    av = scr.availableGeometry()
    win.resize(min(width, int(av.width() * 0.96)), min(height, int(av.height() * 0.92)))


def card(title=None, desc=None):
    g = QGroupBox(title or '')
    if title:
        a11y(g, title, desc)
    else:
        g.setProperty('plain', True)
    return g


def hint(text):
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setProperty('hint', True)
    return lab


def muted(text):
    lab = QLabel(text)
    lab.setProperty('muted', True)
    return lab


def form_grid(spacing=10):
    g = QGridLayout()
    g.setHorizontalSpacing(12)
    g.setVerticalSpacing(spacing)
    return g


def field(grid, row, col, label, widget, span=1, desc=None):
    """A label in column ``col`` and its field next to it, the label aligned to the field's start and linked to it
    (buddy, accessible name). ``widget`` may be a layout (several controls side by side)."""
    lab = QLabel(label)
    lab.setAlignment(Qt.AlignLeading | Qt.AlignVCenter)
    grid.addWidget(lab, row, col)
    if isinstance(widget, QWidget):
        lab.setBuddy(widget)
        if not widget.accessibleName():
            a11y(widget, label.rstrip(' *'), desc)
        if widget.maximumWidth() < 10000:      # a field sized to its content starts where the reading starts
            rtl = QApplication.layoutDirection() == Qt.RightToLeft
            grid.addWidget(widget, row, col + 1, 1, span,
                           (Qt.AlignRight if rtl else Qt.AlignLeft) | Qt.AlignAbsolute | Qt.AlignVCenter)
        else:
            grid.addWidget(widget, row, col + 1, 1, span)
    else:
        grid.addLayout(widget, row, col + 1, 1, span)
    return lab


def pick_font_family():
    """The UI font: Segoe UI (Windows, handles Arabic well), else an installed Arabic-capable UI font."""
    fams = set(QFontDatabase.families())
    for fam in ('Segoe UI', 'Noto Sans Arabic UI', 'Noto Sans Arabic', 'Tahoma', 'Arial', 'DejaVu Sans'):
        if fam in fams:
            return fam
    return QApplication.font().family()


class _ControlSizer(QObject):
    """One height for every line edit, combo box, spin box, date edit and push button of the program's windows,
    taken from the font so text is never cut; fields sized to their content grow with the font; and the mouse
    wheel over a field that is not being edited scrolls the window instead of changing the value."""

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t == QEvent.Polish and isinstance(obj, (QLineEdit, QComboBox, QAbstractSpinBox, QPushButton)):
            self._size(obj)
        elif t == QEvent.Wheel and isinstance(obj, (QComboBox, QAbstractSpinBox)) and not obj.hasFocus():
            area = obj.parentWidget()
            while area is not None and not isinstance(area, QAbstractScrollArea):
                area = area.parentWidget()
            if area is not None and not isinstance(area, QAbstractItemView):
                QApplication.sendEvent(area.verticalScrollBar(), ev)
            return True
        return False

    @staticmethod
    def _size(w):
        if w.objectName().startswith('qt_'):
            return
        parent = w.parentWidget()
        while parent is not None:
            if isinstance(parent, (QComboBox, QAbstractSpinBox, QToolBar, QCalendarWidget, QAbstractItemView)):
                return
            if type(parent).__name__ in ('QPrintPreviewDialog', 'QFileDialog', 'QPrintDialog', 'QPageSetupDialog'):
                return
            parent = parent.parentWidget()
        h = control_height(w, bool(w.property('compact')))
        w.setFixedHeight(h)
        if isinstance(w, (QComboBox, QAbstractSpinBox)):
            w.setFocusPolicy(Qt.StrongFocus)            # the wheel does not take focus (and change a value)
        if w.property('iconOnly'):
            w.setFixedWidth(h)
            return
        fw = w.property('fitWidth')
        if fw:
            need = int(fw * font_scale(w))
            if isinstance(w, (QAbstractSpinBox, QComboBox)) and not isinstance(w, QFontComboBox):
                need = max(need, w.sizeHint().width())   # the widest number, date or option
            w.setFixedWidth(need)


def _arrow_files():
    """The stylesheet's arrow images, drawn once as PNG files (no image plugin needed in the packaged program)."""
    import os
    import tempfile
    folder = os.path.join(tempfile.gettempdir(), 'ChequePrinter-ui')
    os.makedirs(folder, exist_ok=True)
    out = {}
    for tag, name, col in (('ARROW_DOWN', 'chevron_down', C['muted']), ('ARROW_UP', 'chevron_up', C['muted']),
                           ('ARROW_DOWN_OFF', 'chevron_down', '#cbd5e1'), ('ARROW_UP_OFF', 'chevron_up', '#cbd5e1')):
        path = os.path.join(folder, f'{tag.lower()}-{col[1:]}.png')
        if not os.path.isfile(path):
            icon(name, col).pixmap(32, 32).save(path, 'PNG')
        out[tag] = path.replace('\\', '/')
    return out


def stylesheet():
    s = STYLE
    try:
        for tag, path in _arrow_files().items():
            s = s.replace(f'@{tag}@', path)
    except OSError:
        pass
    return s


def apply_theme(app):
    fam = pick_font_family()
    font = QFont(fam)
    font.setPointSizeF(10)
    app.setFont(font)
    app.setStyle('Fusion')
    app.setStyleSheet(stylesheet())
    if not getattr(app, '_cheque_sizer', None):
        app._cheque_sizer = _ControlSizer(app)
        app.installEventFilter(app._cheque_sizer)
    pal = app.palette()
    pal.setColor(pal.ColorRole.Highlight, QColor(C['primary']))
    pal.setColor(pal.ColorRole.Link, QColor(C['primary']))
    app.setPalette(pal)
    return fam
