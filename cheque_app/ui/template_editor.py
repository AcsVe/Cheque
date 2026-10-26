"""Bank template & calibration: drag every field on the cheque (a scan of the bank's blank cheque, or the drawn
cheque face) or type its position in mm, see each field's sample text exactly as it prints, align several fields
at once, print a calibration sheet or a sample cheque, adjust, save."""
import copy
import os
import shutil
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFontComboBox,
                               QGraphicsItem, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene,
                               QGraphicsSimpleTextItem, QGraphicsView, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QScrollArea, QSplitter, QTabWidget, QVBoxLayout, QWidget)

from ..core.render import cheque_values, draw_cheque, min_size
from ..core.templates import FIELDS, default_template
from .common import L, error, info
from .printing import ChequePreview, load_background, preview_jobs, print_jobs
from .theme import C, a11y, button, card, field, form_grid, hint, icon, icon_button, ltr, muted

S = 5.0      # scene units per mm
RES = 12.0   # pixels per mm of the rendered cheque behind the fields (≈ 305 dpi, like a printer)

SAMPLE = {'cheque_date': '2026-12-31', 'payee': 'اسم المستفيد للتجربة', 'amount': '1250.750', 'crossing': 'first',
          'memo': 'البيان', 'cheque_no': 123456}

STATE_COLOR = {'ok': C['primary'], 'shrunk': '#d97706', 'overflow': '#dc2626', None: '#94a3b8'}


def _state_text(state, f):
    if state == 'ok':
        return L('النص يتسع في الحقل بحجم الخط المحدد.', 'The text fits the field at the set font size.')
    if state == 'shrunk':
        return L(f'صُغِّر الخط تلقائياً ليتسع النص (لا يقل عن {min_size(f):g} نقطة). كبّر الحقل لإبقاء الحجم المحدد.',
                 f'The font is reduced automatically to fit (never below {min_size(f):g} pt). Enlarge the field to keep the set size.')
    if state == 'overflow':
        return L('النص أطول من الحقل حتى بأصغر خط — كبّر الحقل أو صغّر الخط.',
                 'The text does not fit even at the smallest font — enlarge the field or reduce the font.')
    return L('الحقل لا يُطبع، أو لا نص له في النموذج.', 'The field is not printed, or has no sample text.')


class FieldItem(QGraphicsRectItem):
    """A field's box on the cheque. The text inside it is the real print rendering underneath; the box's colour
    tells whether the sample text fits (blue), was shrunk to fit (amber) or does not fit (red)."""

    def __init__(self, key, f, on_move):
        super().__init__(0, 0, float(f.get('w') or 30) * S, float(f.get('h') or 7) * S)
        self.key, self.on_move, self.state, self.dragging = key, on_move, None, False
        self.setPos(float(f['x']) * S, float(f['y']) * S)
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable |
                      QGraphicsItem.ItemSendsGeometryChanges | QGraphicsItem.ItemIsFocusable)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.SizeAllCursor)
        self.label = QGraphicsSimpleTextItem(L(*FIELDS[key]), self)
        self.label.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        font = QFont()
        font.setPointSizeF(8)
        font.setBold(True)
        self.label.setFont(font)
        self.label.setVisible(False)
        self.setToolTip(L(*FIELDS[key]))
        self.set_state(None)

    def set_state(self, state):
        self.state = state
        self.label.setBrush(QBrush(QColor(STATE_COLOR.get(state, C['primary']))))
        self.update()

    def place_label(self, scale):
        self.label.setPos(0, -15 / max(scale, 0.01))

    def paint(self, p, _opt, _w=None):
        col = QColor(STATE_COLOR.get(self.state, C['primary']))
        sel = self.isSelected()
        fill = QColor(col)
        fill.setAlpha(40 if sel else (26 if self.state == 'overflow' else 10))
        p.setBrush(fill)
        pen = QPen(col, 2.0 if sel else 1.0, Qt.SolidLine if sel else Qt.DashLine)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.drawRect(self.rect())
        self.label.setVisible(sel)

    def mousePressEvent(self, e):
        self.dragging = True
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        self.dragging = False
        super().mouseReleaseEvent(e)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.dragging:
            step = 0.5 * S                         # dragging snaps to 0.5 mm
            return QPointF(round(value.x() / step) * step, round(value.y() / step) * step)
        if change == QGraphicsItem.ItemPositionHasChanged and self.on_move:
            self.on_move(self.key, self.pos().x() / S, self.pos().y() / S)
        return super().itemChange(change, value)


class FieldView(QGraphicsView):
    """The cheque with its fields; arrow keys move the selected fields 0.5 mm (Shift: 5 mm)."""

    def __init__(self, scene, nudge):
        super().__init__(scene)
        self.nudge = nudge
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setLayoutDirection(Qt.LeftToRight)        # mm are measured from the cheque's left edge
        self.setFocusPolicy(Qt.StrongFocus)

    def keyPressEvent(self, e):
        step = 5.0 if e.modifiers() & Qt.ShiftModifier else 0.5
        d = {Qt.Key_Left: (-step, 0), Qt.Key_Right: (step, 0), Qt.Key_Up: (0, -step), Qt.Key_Down: (0, step)}.get(e.key())
        if d and self.scene().selectedItems():
            self.nudge(*d)
            e.accept()
            return
        super().keyPressEvent(e)


class TemplateEditor(QDialog):
    def __init__(self, parent, ctx, bank_id):
        super().__init__(parent)
        self.ctx, self.db, self.bank_id = ctx, ctx.db, bank_id
        bank = self.db.bank(bank_id) if bank_id else None
        self.tpl = self.db.template(bank_id) if bank_id else default_template()
        self.background = (bank or {}).get('background')
        self.setWindowTitle(L('قالب الشيك والمعايرة', 'Cheque template & calibration') + (f' — {bank["name"]}' if bank else ''))
        self.resize(1280, 800)
        self._syncing = False
        self.items, self.states = {}, {}
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._render)

        # ── left: the cheque with its fields ──
        self.scene = QGraphicsScene(self)
        self.scene.selectionChanged.connect(self._scene_selection)
        self.view = FieldView(self.scene, self.nudge)
        a11y(self.view, L('لوحة مواضع الحقول', 'Field positions board'),
             L('صورة الشيك وعليها إطار كل حقل بنص تجريبي كما يُطبع. اسحب الإطار لتحريكه، أو حدّده واستخدم الأسهم '
               '(0.5 مم، ومع Shift ‏5 مم). الإطار الأزرق: النص يتسع، البرتقالي: صُغّر الخط، الأحمر: لا يتسع.',
               'The cheque with a frame for every field and its sample text as printed. Drag a frame to move it, or '
               'select it and use the arrow keys (0.5 mm, Shift 5 mm). Blue frame: the text fits; amber: the font was '
               'reduced; red: it does not fit.'))
        self.bg_item = QGraphicsPixmapItem()
        self.bg_item.setTransformationMode(Qt.SmoothTransformation)
        self.bg_item.setZValue(-2)
        self.bg_item.setScale(S / RES)

        tools = QHBoxLayout()
        tools.setSpacing(4)
        self.align_buttons = []
        for ic, ar, en, fn, need in (
                ('align_left', 'محاذاة الحواف اليسرى', 'Align left edges', lambda: self.align('left'), 2),
                ('align_right', 'محاذاة الحواف اليمنى', 'Align right edges', lambda: self.align('right'), 2),
                ('align_top', 'محاذاة الحواف العليا', 'Align top edges', lambda: self.align('top'), 2),
                ('align_bottom', 'محاذاة الحواف السفلى (السطر)', 'Align bottom edges (the line)', lambda: self.align('bottom'), 2),
                ('same_width', 'العرض نفسه (عرض الحقل الحالي)', 'Same width (as the current field)', lambda: self.same('w'), 2),
                ('same_height', 'الارتفاع نفسه (ارتفاع الحقل الحالي)', 'Same height (as the current field)', lambda: self.same('h'), 2),
                ('dist_h', 'توزيع أفقي بمسافات متساوية', 'Distribute horizontally', lambda: self.distribute('x'), 3),
                ('dist_v', 'توزيع رأسي بمسافات متساوية', 'Distribute vertically', lambda: self.distribute('y'), 3)):
            b = icon_button(ic, L(ar, en))
            b.setProperty('need', need)
            b.clicked.connect(fn)
            tools.addWidget(b)
            self.align_buttons.append(b)
            if ic in ('align_bottom', 'same_height'):
                tools.addSpacing(10)
        tools.addSpacing(10)
        self.sel_label = muted('')
        tools.addWidget(self.sel_label, 1)
        legend = QHBoxLayout()
        legend.setSpacing(14)
        for state, ar, en in (('ok', 'يتسع', 'Fits'), ('shrunk', 'صُغِّر الخط ليتسع', 'Font reduced to fit'),
                              ('overflow', 'لا يتسع', 'Does not fit')):
            lab = QLabel(f'<span style="color:{STATE_COLOR[state]}">■</span> ' + L(ar, en))
            lab.setProperty('muted', True)
            legend.addWidget(lab)
        keys_hint = muted(L('الأسهم: تحريك 0.5 مم، ومع Shift ‏5 مم. Ctrl+نقر أو السحب حول الحقول لتحديد أكثر من حقل.',
                            'Arrows move 0.5 mm, with Shift 5 mm. Ctrl+click, or drag around fields, to select several.'))
        keys_hint.setWordWrap(True)
        legend.addWidget(keys_hint, 1)
        board = QWidget()
        bl = QVBoxLayout(board)
        bl.setContentsMargins(10, 10, 10, 10)
        bl.setSpacing(8)
        bl.addLayout(tools)
        bl.addWidget(self.view, 1)
        bl.addLayout(legend)

        self.preview = ChequePreview()
        self.preview.setLayoutDirection(Qt.LeftToRight)
        self.left_tabs = QTabWidget()
        a11y(self.left_tabs, L('عرض الشيك', 'Cheque view'))
        self.left_tabs.addTab(board, L('مواضع الحقول', 'Field positions'))
        self.left_tabs.addTab(self.preview, L('معاينة بنموذج', 'Sample preview'))
        self.left_tabs.currentChanged.connect(lambda *_: self._refresh_preview())

        # ── right: fields / template & printer ──
        self.fields = QListWidget()
        a11y(self.fields, L('حقول الشيك', 'Cheque fields'),
             L('اختر حقلاً لعرض خصائصه وتحديده على الشيك', 'Choose a field to see its properties and select it on the cheque'))
        for key in FIELDS:
            it = QListWidgetItem(L(*FIELDS[key]))
            it.setData(Qt.UserRole, key)
            self.fields.addItem(it)
        self.fields.setFixedHeight(6 * 32 + 10)
        self.fields.currentItemChanged.connect(self._field_selected)

        mm, pt = L(' مم', ' mm'), L(' نقطة', ' pt')
        self.f_visible = a11y(QCheckBox(L('يُطبع', 'Printed')), L('الحقل يُطبع', 'Field printed'))
        self.f_bold = a11y(QCheckBox(L('عريض', 'Bold')), L('خط عريض', 'Bold font'))
        self.f_x, self.f_y = self._dspin(-20, 300, 0, mm), self._dspin(-20, 200, 0, mm)
        self.f_w, self.f_h = self._dspin(1, 300, 30, mm), self._dspin(1, 100, 7, mm)
        self.f_size = self._dspin(5, 36, 10, pt)
        self.f_align = QComboBox()
        for k, ar, en in (('right', 'يمين', 'Right'), ('center', 'وسط', 'Centre'), ('left', 'يسار', 'Left')):
            self.f_align.addItem(L(ar, en), k)
        self.f_valign = QComboBox()
        for k, ar, en in (('bottom', 'على السطر', 'On the line'), ('center', 'في وسط الإطار', 'Centred in the box')):
            self.f_valign.addItem(L(ar, en), k)
        self.f_spacing = self._dspin(0, 20, 0, mm)
        self.f_spacing.setToolTip(L('للتاريخ في مربعات: المسافة بين الأرقام (0 = نص عادي)', 'For a boxed date: distance between digits (0 = normal text)'))
        self.f_angle = self._dspin(-90, 90, 0, '°')
        for w in (self.f_align, self.f_valign):
            w.setFixedWidth(160)
        self.f_state = QLabel()
        self.f_state.setWordWrap(True)
        self.f_state.setProperty('hint', True)
        a11y(self.f_state, L('ملاءمة النص للحقل', 'How the text fits the field'))
        ff = form_grid(8)
        checks = QHBoxLayout()
        checks.setSpacing(18)
        checks.addWidget(self.f_visible)
        checks.addWidget(self.f_bold)
        checks.addStretch(1)
        ff.addLayout(checks, 0, 1, 1, 3)
        field(ff, 1, 0, 'X', self.f_x, desc=L('بُعد الحقل عن الحافة اليسرى للشيك', 'Distance from the cheque\'s left edge'))
        field(ff, 1, 2, 'Y', self.f_y, desc=L('بُعد الحقل عن الحافة العليا للشيك', 'Distance from the cheque\'s top edge'))
        field(ff, 2, 0, L('العرض', 'Width'), self.f_w)
        field(ff, 2, 2, L('الارتفاع', 'Height'), self.f_h)
        field(ff, 3, 0, L('حجم الخط', 'Font size'), self.f_size)
        field(ff, 3, 2, L('المحاذاة', 'Alignment'), self.f_align)
        field(ff, 4, 0, L('مسافة الأرقام', 'Digit spacing'), self.f_spacing)
        field(ff, 4, 2, L('الموضع الرأسي', 'Vertical'), self.f_valign)
        field(ff, 5, 0, L('زاوية الختم', 'Stamp angle'), self.f_angle)
        ff.addWidget(self.f_state, 6, 0, 1, 4)
        ff.setColumnStretch(4, 1)
        props = card(L('خصائص الحقل', 'Field properties'))
        props.setLayout(ff)
        for w in (self.f_x, self.f_y, self.f_w, self.f_h, self.f_size, self.f_spacing, self.f_angle):
            w.valueChanged.connect(self._field_edited)
        for w in (self.f_visible, self.f_bold):
            w.toggled.connect(self._field_edited)
        self.f_align.currentIndexChanged.connect(self._field_edited)
        self.f_valign.currentIndexChanged.connect(self._field_edited)

        self.dx, self.dy = self._dspin(-50, 50, 0, mm), self._dspin(-50, 50, 0, mm)
        apply_shift = button(L('إزاحة', 'Shift'), 'move', tip=L('تحريك كل الحقول بالمقدار المحدد', 'Move every field by these amounts'))
        apply_shift.clicked.connect(self.shift_all)
        sh = form_grid()
        field(sh, 0, 0, 'X', self.dx, desc=L('إزاحة كل الحقول أفقياً', 'Shift all fields horizontally'))
        field(sh, 0, 2, 'Y', self.dy, desc=L('إزاحة كل الحقول رأسياً', 'Shift all fields vertically'))
        sh.addWidget(apply_shift, 0, 4)
        sh.setColumnStretch(5, 1)
        shift_card = card(L('إزاحة كل الحقول', 'Shift all fields'))
        shift_card.setLayout(sh)

        fields_tab = QWidget()
        lf = QVBoxLayout(fields_tab)
        lf.setContentsMargins(10, 4, 10, 10)
        lf.setSpacing(4)
        fl_card = card(L('الحقول', 'Fields'))
        QVBoxLayout(fl_card).addWidget(self.fields)
        lf.addWidget(fl_card)
        lf.addWidget(props)
        lf.addWidget(shift_card)
        lf.addStretch(1)

        # template & printer
        self.name = QLineEdit((bank or {}).get('name') or '')
        self.name_en = QLineEdit((bank or {}).get('name_en') or '')
        self.name_en.setLayoutDirection(Qt.LeftToRight)
        self.width = self._dspin(50, 300, self.tpl['width_mm'], mm)
        self.height = self._dspin(30, 200, self.tpl['height_mm'], mm)
        self.font = QFontComboBox()
        self.font.setCurrentFont(QFont(self.tpl.get('font') or 'Arial'))
        self.words_lang = QComboBox()
        self.words_lang.addItem(L('بالعربية', 'Arabic'), 'ar')
        self.words_lang.addItem(L('بالإنجليزية', 'English'), 'en')
        self.words_lang.setCurrentIndex(max(0, self.words_lang.findData(self.tpl.get('words_lang', 'ar'))))
        self.sub_digits = a11y(QCheckBox(L('الفلوس بالأرقام (و750 فلسًا)', 'Fils as digits (and 750/1000)')),
                               L('الفلوس بالأرقام', 'Fils as digits'))
        self.sub_digits.setChecked(bool(self.tpl.get('sub_as_digits')))
        self.date_fmt = QComboBox()
        for f in ('yyyy/MM/dd', 'dd/MM/yyyy', 'dd-MM-yyyy', 'yyyy-MM-dd', 'ddMMyyyy', 'dd / MM / yyyy'):
            self.date_fmt.addItem(f, f)
        self.date_fmt.setEditable(True)
        self.date_fmt.setCurrentText(self.tpl.get('date_format') or 'yyyy/MM/dd')
        ltr(self.date_fmt)
        self.hundred = QComboBox()
        self.hundred.addItem('مئة — ثلاثمئة، مئتان', 'مئة')
        self.hundred.addItem('مائة — ثلاثمائة، مائتان', 'مائة')
        self.hundred.setCurrentIndex(max(0, self.hundred.findData(self.tpl.get('hundred', 'مئة'))))
        self.digits = QComboBox()
        self.digits.addItem(L('أرقام 1250', 'Digits 1250'), 'latin')
        self.digits.addItem(L('أرقام عربية ١٢٥٠', 'Arabic-Indic digits ١٢٥٠'), 'arabic')
        self.digits.setCurrentIndex(max(0, self.digits.findData(self.tpl.get('digits', 'latin'))))
        self.zero_fils = ltr(QLineEdit(self.tpl.get('zero_fils') if self.tpl.get('zero_fils') is not None else '---'), 110)
        self.zero_fils.setToolTip(L('ما يُكتب في خانة الفلوس إن لم توجد فلوس، مثل --- أو 000', 'Shown in the fils box when there are no fils, e.g. --- or 000'))
        self.wrap = ltr(QLineEdit(self.tpl.get('amount_wrap') or '#{}#'), 110)
        self.wrap.setToolTip(L('{} مكان الرقم، مثل #{}# أو **{}**', '{} is the figure, e.g. #{}# or **{}**'))
        self.thousands = a11y(QCheckBox(L('فاصل الآلاف (1,250)', 'Thousands separator (1,250)')),
                              L('فاصل الآلاف', 'Thousands separator'))
        self.thousands.setChecked(bool(self.tpl.get('thousands')))
        feed = self.tpl.get('feed') or {}
        self.paper = QComboBox()
        self.paper.addItem(L('بمقاس الشيك (تغذية يدوية)', 'Cheque size (manual feed)'), 'cheque')
        self.paper.addItem('A4', 'A4')
        self.paper.addItem('Letter', 'Letter')
        self.paper.setCurrentIndex(max(0, self.paper.findData(feed.get('paper', 'cheque'))))
        self.rotate = QComboBox()
        self.rotate.addItem(L('أفقي (الطرف الطويل أولاً)', 'Horizontal (long edge first)'), 0)
        self.rotate.addItem(L('عامودي (الطرف القصير أولاً)', 'Vertical (short edge first)'), 90)
        self.rotate.addItem(L('عامودي معكوس', 'Vertical, reversed'), 270)
        self.rotate.setCurrentIndex(max(0, self.rotate.findData(int(feed.get('rotate') or 0))))
        self.align_feed = QComboBox()
        for k, ar, en in (('center', 'في الوسط', 'Centre'), ('left', 'يسار', 'Left'), ('right', 'يمين', 'Right')):
            self.align_feed.addItem(L(ar, en), k)
        self.align_feed.setCurrentIndex(max(0, self.align_feed.findData(feed.get('align') or 'center')))
        self.off_x = self._dspin(-100, 100, feed.get('offset_x') or 0, mm)
        self.off_y = self._dspin(-100, 100, feed.get('offset_y') or 0, mm)
        for w in (self.font, self.words_lang, self.date_fmt, self.hundred, self.digits, self.paper, self.rotate,
                  self.align_feed):
            w.setFixedWidth(250)

        gen = form_grid(8)
        field(gen, 0, 0, L('اسم البنك / القالب *', 'Bank / template name *'), self.name)
        field(gen, 1, 0, L('الاسم بالإنجليزية', 'Name in English'), self.name_en)
        size = QHBoxLayout()
        size.setSpacing(6)
        size.addWidget(self.width)
        size.addWidget(QLabel('×'))
        size.addWidget(self.height)
        size.addStretch(1)
        a11y(self.width, L('عرض الشيك', 'Cheque width'))
        a11y(self.height, L('ارتفاع الشيك', 'Cheque height'))
        field(gen, 2, 0, L('مقاس الشيك', 'Cheque size'), size)
        field(gen, 3, 0, L('الخط', 'Font'), self.font)
        field(gen, 4, 0, L('المبلغ كتابةً', 'Amount in words'), self.words_lang)
        gen.addWidget(self.sub_digits, 5, 1)
        field(gen, 6, 0, L('صيغة التاريخ', 'Date format'), self.date_fmt)
        field(gen, 7, 0, L('كتابة المئات', 'Spelling of hundreds'), self.hundred)
        field(gen, 8, 0, L('الأرقام المطبوعة', 'Printed figures'), self.digits)
        field(gen, 9, 0, L('خانة الفلوس عند عدم وجودها', 'Fils box when zero'), self.zero_fils)
        field(gen, 10, 0, L('إطار رقم الدنانير', 'Around the dinars figure'), self.wrap)
        gen.addWidget(self.thousands, 11, 1)
        bg = button(L('صورة الشيك الفارغ…', 'Blank cheque scan…'), 'image',
                    tip=L('تحميل صورة ممسوحة لشيك فارغ من الدفتر، للمعاينة والمعايرة فقط ولا تُطبع',
                          'Load a scan of a blank cheque from the book — for preview and calibration only, never printed'))
        bg.clicked.connect(self.load_background)
        gen.addWidget(bg, 12, 1, Qt.AlignLeading | Qt.AlignVCenter)
        gen.setColumnStretch(1, 1)
        g1 = card(L('القالب', 'Template'))
        g1.setLayout(gen)

        fd = form_grid(8)
        field(fd, 0, 0, L('الورق', 'Paper'), self.paper)
        field(fd, 1, 0, L('اتجاه إدخال الشيك', 'Feed direction'), self.rotate)
        field(fd, 2, 0, L('موضعه في الطابعة', 'Position in the printer'), self.align_feed)
        field(fd, 3, 0, L('إزاحة أفقية', 'Shift right/left'), self.off_x)
        field(fd, 4, 0, L('إزاحة رأسية', 'Shift down/up'), self.off_y)
        fd.setColumnStretch(2, 1)
        g2 = card(L('الطابعة (تُضبط بعد الطباعة التجريبية)', 'Printer (set after a test print)'))
        g2.setLayout(fd)

        for w in (self.width, self.height, self.off_x, self.off_y):
            w.valueChanged.connect(self._general_edited)
        for w in (self.words_lang, self.paper, self.rotate, self.align_feed, self.hundred, self.digits):
            w.currentIndexChanged.connect(self._general_edited)
        for w in (self.sub_digits, self.thousands):
            w.toggled.connect(self._general_edited)
        self.font.currentFontChanged.connect(self._general_edited)
        self.date_fmt.currentTextChanged.connect(self._general_edited)
        self.wrap.textChanged.connect(self._general_edited)
        self.zero_fils.textChanged.connect(self._general_edited)
        self.name.textChanged.connect(lambda *_: self._schedule())

        tpl_tab = QWidget()
        lt = QVBoxLayout(tpl_tab)
        lt.setContentsMargins(10, 4, 10, 10)
        lt.setSpacing(4)
        lt.addWidget(g1)
        lt.addWidget(g2)
        lt.addStretch(1)
        self.right_tabs = QTabWidget()
        a11y(self.right_tabs, L('إعدادات القالب', 'Template settings'))
        for page, ar, en in ((fields_tab, 'الحقول', 'Fields'), (tpl_tab, 'القالب والطابعة', 'Template && printer')):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setWidget(page)
            page.setObjectName('page')
            self.right_tabs.addTab(scroll, L(ar, en))
        self.right_tabs.setMinimumWidth(570)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        for label, ic, cb, tip in (
                (L('طباعة صفحة المعايرة', 'Print the calibration sheet'), 'grid', lambda: self._print(True),
                 L('شبكة مليمترية وإطارات الحقول على ورقة عادية', 'A millimetre grid and the field frames on plain paper')),
                (L('طباعة شيك تجريبي', 'Print a sample cheque'), 'print', lambda: self._print(False), None),
                (L('معاينة الطباعة', 'Print preview'), 'preview', self._preview, None),
                (L('استعادة القالب الافتراضي', 'Reset to default'), 'reset', self.reset,
                 L('إرجاع مواضع الحقول وأحجامها إلى القالب الافتراضي', 'Put the fields back to the default template'))):
            bt = button(label, ic, tip=tip)
            bt.clicked.connect(cb)
            btns.addWidget(bt)
        btns.addStretch(1)
        cancel = button(L('إلغاء', 'Cancel'))
        cancel.setMinimumWidth(110)
        cancel.clicked.connect(self.reject)
        save = button(L('حفظ', 'Save'), 'save', 'primary')
        save.setMinimumWidth(110)
        save.clicked.connect(self.save)
        btns.addWidget(cancel)
        btns.addWidget(save)

        sp = QSplitter()
        sp.setChildrenCollapsible(False)
        sp.addWidget(self.left_tabs)
        sp.addWidget(self.right_tabs)
        sp.setStretchFactor(0, 1)
        sp.setStretchFactor(1, 0)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)
        lay.addWidget(hint(L('١) اسحب كل حقل إلى مكانه على صورة الشيك أو اكتب موضعه بالمليمتر. ٢) اطبع «صفحة المعايرة» على ورقة عادية وضع الشيك فوقها مقابل الضوء. ٣) صحّح «الإزاحة» حتى تتطابق، ثم اطبع «شيكاً تجريبياً».',
                             '1) Drag every field onto the cheque or type its position in mm. 2) Print the «calibration sheet» on plain paper and hold a cheque over it against the light. 3) Correct the «shift» until they match, then print a «sample cheque».')))
        lay.addWidget(sp, 1)
        lay.addLayout(btns)
        self.build_scene()
        self.fields.setCurrentRow(0)
        self._scene_selection()

    @staticmethod
    def _dspin(lo, hi, val, suffix=''):
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(1)
        s.setSingleStep(0.5)
        s.setValue(float(val))
        s.setSuffix(suffix)
        s.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        ltr(s, 118)
        return s

    # ── scene ────────────────────────────────────────────────────────
    def build_scene(self):
        for it in list(self.items.values()):
            self.scene.removeItem(it)
        if self.bg_item.scene() is None:
            self.scene.addItem(self.bg_item)
        w, h = float(self.tpl['width_mm']) * S, float(self.tpl['height_mm']) * S
        self.items = {}
        for key, f in self.tpl['fields'].items():
            if key not in FIELDS:
                continue
            it = FieldItem(key, f, self._moved)
            it.setOpacity(1.0 if f.get('visible', True) else 0.4)
            self.scene.addItem(it)
            self.items[key] = it
        self.scene.setSceneRect(QRectF(-12, -24, w + 24, h + 36))
        self._fit_view()
        self._render()

    def _fit_view(self):
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)
        scale = self.view.transform().m11()
        for it in self.items.values():
            it.place_label(scale)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit_view()

    def showEvent(self, e):
        super().showEvent(e)
        self._fit_view()

    def _schedule(self):
        self._timer.start()

    def _render(self):
        """Draw the cheque exactly as it prints (same code as the printer) behind the field frames, and colour each
        frame by how its sample text fits."""
        w_mm, h_mm = float(self.tpl['width_mm']), float(self.tpl['height_mm'])
        img = QImage(int(w_mm * RES), int(h_mm * RES), QImage.Format_ARGB32_Premultiplied)
        img.setDotsPerMeterX(int(RES * 1000))
        img.setDotsPerMeterY(int(RES * 1000))
        img.fill(QColor('#fffaf3'))
        values, bg, labels = self._values(), load_background(self.background), self._labels()
        report = {}
        p = QPainter(img)
        try:
            draw_cheque(p, self.tpl, values, (0, 0), RES, background=bg, ink='#0b2a6b', simulate=True, labels=labels,
                        report=report)
            p.setPen(QPen(QColor('#94a3b8'), 2))
            p.drawRect(0, 0, img.width() - 1, img.height() - 1)
        finally:
            p.end()
        self.bg_item.setPixmap(QPixmap.fromImage(img))
        self.states = report
        for key, it in self.items.items():
            it.set_state(report.get(key))
        for i in range(self.fields.count()):
            item = self.fields.item(i)
            st = report.get(item.data(Qt.UserRole))
            item.setIcon(icon({'ok': 'check', 'shrunk': 'same_width', 'overflow': 'cancel'}.get(st, 'select_none'),
                              STATE_COLOR.get(st)))
            item.setToolTip(_state_text(st, self.tpl['fields'].get(item.data(Qt.UserRole)) or {}))
        self._show_state()
        self._refresh_preview()

    def _show_state(self):
        cur = self.fields.currentItem()
        if not cur:
            return
        key = cur.data(Qt.UserRole)
        st = self.states.get(key)
        self.f_state.setText(_state_text(st, self.tpl['fields'].get(key) or {}))
        self.f_state.setStyleSheet(f'color: {STATE_COLOR.get(st)};' if st in ('shrunk', 'overflow') else '')

    def _moved(self, key, x, y):
        f = self.tpl['fields'][key]
        f['x'], f['y'] = round(x, 1), round(y, 1)
        cur = self.fields.currentItem()
        if cur and cur.data(Qt.UserRole) == key and not self._syncing:
            self._syncing = True
            self.f_x.setValue(f['x'])
            self.f_y.setValue(f['y'])
            self._syncing = False
        self._schedule()

    def _selected_keys(self):
        return [it.key for it in self.scene.selectedItems() if isinstance(it, FieldItem)]

    def _scene_selection(self):
        keys = self._selected_keys()
        n = len(keys)
        for b in self.align_buttons:
            b.setEnabled(n >= int(b.property('need')))
        self.sel_label.setText(L(f'المحدد: {n} من {len(self.items)}', f'Selected: {n} of {len(self.items)}') if n
                               else L('حدّد حقلاً أو أكثر', 'Select one or more fields'))
        cur = self.fields.currentItem()
        if keys and not self._syncing and (not cur or cur.data(Qt.UserRole) not in keys):
            self._syncing = True
            for i in range(self.fields.count()):
                if self.fields.item(i).data(Qt.UserRole) == keys[0]:
                    self.fields.setCurrentRow(i)
            self._syncing = False
            self._fill_props(keys[0])

    def _field_selected(self, cur, _prev):
        if not cur:
            return
        key = cur.data(Qt.UserRole)
        self._fill_props(key)
        if not self._syncing:
            self._syncing = True
            self.scene.clearSelection()
            if key in self.items:
                self.items[key].setSelected(True)
            self._syncing = False
            self._scene_selection()

    def _fill_props(self, key):
        f = self.tpl['fields'][key]
        was, self._syncing = self._syncing, True
        self.f_visible.setChecked(bool(f.get('visible', True)))
        self.f_x.setValue(float(f['x']))
        self.f_y.setValue(float(f['y']))
        self.f_w.setValue(float(f.get('w') or 30))
        self.f_h.setValue(float(f.get('h') or 7))
        self.f_size.setValue(float(f.get('size') or 10))
        self.f_align.setCurrentIndex(max(0, self.f_align.findData(f.get('align') or 'center')))
        self.f_valign.setCurrentIndex(max(0, self.f_valign.findData(f.get('valign') or 'bottom')))
        self.f_bold.setChecked(bool(f.get('bold')))
        self.f_spacing.setValue(float(f.get('spacing') or 0))
        self.f_angle.setValue(float(f.get('angle') or 0))
        self.f_spacing.setEnabled(key in ('date', 'cheque_no', 'amount_dinar'))
        self.f_angle.setEnabled(key == 'crossing')
        self._syncing = was
        self._show_state()

    def _field_edited(self, *_):
        if self._syncing or not self.fields.currentItem():
            return
        key = self.fields.currentItem().data(Qt.UserRole)
        f = self.tpl['fields'][key]
        f.update({'visible': self.f_visible.isChecked(), 'x': self.f_x.value(), 'y': self.f_y.value(),
                  'w': self.f_w.value(), 'h': self.f_h.value(), 'size': self.f_size.value(),
                  'align': self.f_align.currentData(), 'valign': self.f_valign.currentData(),
                  'bold': self.f_bold.isChecked(), 'spacing': self.f_spacing.value(), 'angle': self.f_angle.value()})
        self._place(key)
        self._schedule()

    def _place(self, key):
        f, it = self.tpl['fields'][key], self.items.get(key)
        if not it:
            return
        was, self._syncing = self._syncing, True
        it.setRect(0, 0, float(f.get('w') or 30) * S, float(f.get('h') or 7) * S)
        it.setPos(float(f['x']) * S, float(f['y']) * S)
        it.setOpacity(1.0 if f.get('visible', True) else 0.4)
        self._syncing = was

    # ── alignment tools ──────────────────────────────────────────────
    def _apply(self, changes):
        """changes: {key: {attr: value}} — applied to the template, the frames and the property panel."""
        for key, ch in changes.items():
            self.tpl['fields'][key].update({a: round(float(v), 1) for a, v in ch.items()})
            self._place(key)
        cur = self.fields.currentItem()
        if cur:
            self._fill_props(cur.data(Qt.UserRole))
        self._render()

    def nudge(self, dx, dy):
        self._apply({k: {'x': float(self.tpl['fields'][k]['x']) + dx, 'y': float(self.tpl['fields'][k]['y']) + dy}
                     for k in self._selected_keys()})

    def align(self, edge):
        keys = self._selected_keys()
        if len(keys) < 2:
            return
        fs = {k: self.tpl['fields'][k] for k in keys}

        def x(f): return float(f['x'])
        def y(f): return float(f['y'])
        def w(f): return float(f.get('w') or 30)
        def h(f): return float(f.get('h') or 7)
        if edge == 'left':
            v = min(x(f) for f in fs.values())
            self._apply({k: {'x': v} for k in keys})
        elif edge == 'right':
            v = max(x(f) + w(f) for f in fs.values())
            self._apply({k: {'x': v - w(f)} for k, f in fs.items()})
        elif edge == 'top':
            v = min(y(f) for f in fs.values())
            self._apply({k: {'y': v} for k in keys})
        else:
            v = max(y(f) + h(f) for f in fs.values())
            self._apply({k: {'y': v - h(f)} for k, f in fs.items()})

    def same(self, attr):
        keys = self._selected_keys()
        if len(keys) < 2:
            return
        cur = self.fields.currentItem()
        ref = cur.data(Qt.UserRole) if cur and cur.data(Qt.UserRole) in keys else keys[0]
        v = float(self.tpl['fields'][ref].get(attr) or (30 if attr == 'w' else 7))
        self._apply({k: {attr: v} for k in keys})

    def distribute(self, axis):
        keys = self._selected_keys()
        if len(keys) < 3:
            return
        size = 'w' if axis == 'x' else 'h'
        fs = sorted(keys, key=lambda k: float(self.tpl['fields'][k][axis]))
        first, last = self.tpl['fields'][fs[0]], self.tpl['fields'][fs[-1]]
        span = float(last[axis]) + float(last.get(size) or 0) - float(first[axis])
        total = sum(float(self.tpl['fields'][k].get(size) or 0) for k in fs)
        gap = (span - total) / (len(fs) - 1)
        pos, changes = float(first[axis]), {}
        for k in fs:
            changes[k] = {axis: pos}
            pos += float(self.tpl['fields'][k].get(size) or 0) + gap
        self._apply(changes)

    # ── template ─────────────────────────────────────────────────────
    def _general_edited(self, *_):
        t = self.tpl
        resized = (t['width_mm'], t['height_mm']) != (self.width.value(), self.height.value())
        t.update({'width_mm': self.width.value(), 'height_mm': self.height.value(),
                  'font': self.font.currentFont().family(), 'words_lang': self.words_lang.currentData(),
                  'sub_as_digits': self.sub_digits.isChecked(), 'date_format': self.date_fmt.currentText().strip() or 'yyyy/MM/dd',
                  'amount_wrap': self.wrap.text() or '{}', 'thousands': self.thousands.isChecked(),
                  'hundred': self.hundred.currentData(), 'digits': self.digits.currentData(),
                  'zero_fils': self.zero_fils.text()})
        t['feed'] = {'paper': self.paper.currentData(), 'rotate': self.rotate.currentData(),
                     'align': self.align_feed.currentData(), 'offset_x': self.off_x.value(), 'offset_y': self.off_y.value()}
        if resized:
            self.build_scene()
        else:
            self._schedule()

    def shift_all(self):
        dx, dy = self.dx.value(), self.dy.value()
        for f in self.tpl['fields'].values():
            f['x'] = round(float(f['x']) + dx, 1)
            f['y'] = round(float(f['y']) + dy, 1)
        self.build_scene()
        self._field_selected(self.fields.currentItem(), None)

    def reset(self):
        keep = (self.tpl['width_mm'], self.tpl['height_mm'])
        self.tpl = default_template()
        self.tpl['width_mm'], self.tpl['height_mm'] = keep
        self.build_scene()
        self._field_selected(self.fields.currentItem(), None)

    def load_background(self):
        path, _ = QFileDialog.getOpenFileName(self, L('صورة الشيك الفارغ', 'Blank cheque scan'), '',
                                              L('صور', 'Images') + ' (*.png *.jpg *.jpeg *.bmp)')
        if not path:
            return
        folder = os.path.join(self.ctx.data_dir, 'backgrounds')
        os.makedirs(folder, exist_ok=True)
        target = os.path.join(folder, f'bank-{self.bank_id or "new"}-{int(time.time())}{os.path.splitext(path)[1].lower()}')
        try:
            shutil.copyfile(path, target)
        except OSError as e:
            error(self, str(e))
            return
        self.background = target
        self._render()

    def _values(self):
        return cheque_values(self.tpl, SAMPLE, self.ctx.crossing_texts())

    def _labels(self):
        return {'bank': self.name.text().strip()}

    def _refresh_preview(self):
        if self.left_tabs.currentWidget() is self.preview:
            self.preview.show_cheque(self.tpl, self._values(), load_background(self.background), labels=self._labels())

    def _print(self, calibration):
        print_jobs(self, [(copy.deepcopy(self.tpl), self._values())], self.db.get, self.db.set, calibration=calibration)

    def _preview(self):
        preview_jobs(self, [(copy.deepcopy(self.tpl), self._values())], self.db.get)

    def save(self):
        name = self.name.text().strip()
        if not name:
            error(self, L('أدخل اسم البنك أو القالب.', 'Enter the bank / template name.'))
            self.right_tabs.setCurrentIndex(1)
            self.name.setFocus()
            return
        self.bank_id = self.db.save_bank({'name': name, 'name_en': self.name_en.text().strip() or None,
                                          'template': self.tpl, 'background': self.background,
                                          'is_active': (self.db.bank(self.bank_id) or {}).get('is_active', 1) if self.bank_id else 1},
                                         self.bank_id)
        info(self, L('حُفظ القالب.', 'Template saved.'))
        self.accept()

    def done(self, r):
        self._timer.stop()             # no late redraw once the dialog is closed
        super().done(r)
