"""Bank template & calibration: drag every field on a scan of the bank's blank cheque (or type its position in mm),
print a calibration sheet or a sample cheque, adjust, save."""
import copy
import os
import shutil
import time

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPen, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFontComboBox, QFormLayout,
                               QGraphicsItem, QGraphicsRectItem, QGraphicsScene, QGraphicsSimpleTextItem,
                               QGraphicsView, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPushButton, QSpinBox, QSplitter, QTabWidget, QVBoxLayout, QWidget)

from ..core.render import cheque_values
from ..core.templates import FIELDS, default_template
from .common import L, error, info
from .printing import ChequePreview, load_background, preview_jobs, print_jobs

S = 5.0   # scene pixels per mm

SAMPLE = {'cheque_date': '2026-12-31', 'payee': 'اسم المستفيد للتجربة', 'amount': '1250.750', 'crossing': 'first',
          'memo': 'البيان', 'cheque_no': 123456}


class FieldItem(QGraphicsRectItem):
    def __init__(self, key, f, on_move):
        super().__init__(0, 0, float(f.get('w') or 30) * S, float(f.get('h') or 7) * S)
        self.key, self.on_move = key, on_move
        self.setPos(float(f['x']) * S, float(f['y']) * S)
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemSendsGeometryChanges)
        self.setPen(QPen(QColor('#1d5fbf'), 1.2, Qt.DashLine))
        self.setBrush(QBrush(QColor(29, 95, 191, 28)))
        self.label = QGraphicsSimpleTextItem(L(*FIELDS[key]), self)
        font = QFont()
        font.setPointSizeF(7)
        self.label.setFont(font)
        self.label.setBrush(QBrush(QColor('#1d5fbf')))
        self.label.setPos(1, -12)
        self.setToolTip(L(*FIELDS[key]))

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged and self.on_move:
            self.on_move(self.key, self.pos().x() / S, self.pos().y() / S)
        return super().itemChange(change, value)


class TemplateEditor(QDialog):
    def __init__(self, parent, ctx, bank_id):
        super().__init__(parent)
        self.ctx, self.db, self.bank_id = ctx, ctx.db, bank_id
        bank = self.db.bank(bank_id) if bank_id else None
        self.tpl = self.db.template(bank_id) if bank_id else default_template()
        self.background = (bank or {}).get('background')
        self.setWindowTitle(L('قالب الشيك والمعايرة', 'Cheque template & calibration') + (f' — {bank["name"]}' if bank else ''))
        self.resize(1250, 760)
        self._syncing = False

        # ── left: the cheque to drag on ──
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHints(self.view.renderHints())
        self.view.setLayoutDirection(Qt.LeftToRight)        # mm are measured from the cheque's left edge
        self.preview = ChequePreview()
        self.preview.setLayoutDirection(Qt.LeftToRight)
        left_tabs = QTabWidget()
        left_tabs.addTab(self.view, L('مواضع الحقول (اسحبها)', 'Field positions (drag them)'))
        left_tabs.addTab(self.preview, L('معاينة بنموذج', 'Sample preview'))
        left_tabs.currentChanged.connect(lambda *_: self._refresh_preview())

        # ── right: settings ──
        self.name = QLineEdit((bank or {}).get('name') or '')
        self.name_en = QLineEdit((bank or {}).get('name_en') or '')
        self.width = self._dspin(50, 300, self.tpl['width_mm'])
        self.height = self._dspin(30, 200, self.tpl['height_mm'])
        self.font = QFontComboBox()
        self.font.setCurrentFont(QFont(self.tpl.get('font') or 'Arial'))
        self.words_lang = QComboBox()
        self.words_lang.addItem(L('بالعربية', 'Arabic'), 'ar')
        self.words_lang.addItem(L('بالإنجليزية', 'English'), 'en')
        self.words_lang.setCurrentIndex(max(0, self.words_lang.findData(self.tpl.get('words_lang', 'ar'))))
        self.sub_digits = QCheckBox(L('الفلوس بالأرقام (و750 فلسًا)', 'Fils as digits (and 750/1000)'))
        self.sub_digits.setChecked(bool(self.tpl.get('sub_as_digits')))
        self.date_fmt = QComboBox()
        for f in ('yyyy/MM/dd', 'dd/MM/yyyy', 'dd-MM-yyyy', 'yyyy-MM-dd', 'ddMMyyyy', 'dd / MM / yyyy'):
            self.date_fmt.addItem(f, f)
        self.date_fmt.setEditable(True)
        self.date_fmt.setCurrentText(self.tpl.get('date_format') or 'yyyy/MM/dd')
        self.hundred = QComboBox()
        self.hundred.addItem('مئة — ثلاثمئة، مئتان', 'مئة')
        self.hundred.addItem('مائة — ثلاثمائة، مائتان', 'مائة')
        self.hundred.setCurrentIndex(max(0, self.hundred.findData(self.tpl.get('hundred', 'مئة'))))
        self.digits = QComboBox()
        self.digits.addItem(L('أرقام 1250', 'Digits 1250'), 'latin')
        self.digits.addItem(L('أرقام عربية ١٢٥٠', 'Arabic-Indic digits ١٢٥٠'), 'arabic')
        self.digits.setCurrentIndex(max(0, self.digits.findData(self.tpl.get('digits', 'latin'))))
        self.zero_fils = QLineEdit(self.tpl.get('zero_fils') if self.tpl.get('zero_fils') is not None else '---')
        self.zero_fils.setToolTip(L('ما يُكتب في خانة الفلوس إن لم توجد فلوس، مثل --- أو 000', 'Shown in the fils box when there are no fils, e.g. --- or 000'))
        self.wrap = QLineEdit(self.tpl.get('amount_wrap') or '#{}#')
        self.wrap.setToolTip(L('{} مكان الرقم، مثل #{}# أو **{}**', '{} is the figure, e.g. #{}# or **{}**'))
        self.thousands = QCheckBox(L('فاصل الآلاف (1,250)', 'Thousands separator (1,250)'))
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
        self.align = QComboBox()
        for k, ar, en in (('center', 'في الوسط', 'Centre'), ('left', 'يسار', 'Left'), ('right', 'يمين', 'Right')):
            self.align.addItem(L(ar, en), k)
        self.align.setCurrentIndex(max(0, self.align.findData(feed.get('align') or 'center')))
        self.off_x = self._dspin(-100, 100, feed.get('offset_x') or 0)
        self.off_y = self._dspin(-100, 100, feed.get('offset_y') or 0)

        gen = QFormLayout()
        gen.addRow(L('اسم البنك / القالب *', 'Bank / template name *'), self.name)
        gen.addRow(L('بالإنجليزية', 'In English'), self.name_en)
        size = QHBoxLayout()
        size.addWidget(self.width)
        size.addWidget(QLabel('×'))
        size.addWidget(self.height)
        gen.addRow(L('مقاس الشيك (مم)', 'Cheque size (mm)'), size)
        gen.addRow(L('الخط', 'Font'), self.font)
        gen.addRow(L('المبلغ كتابةً', 'Amount in words'), self.words_lang)
        gen.addRow('', self.sub_digits)
        gen.addRow(L('صيغة التاريخ', 'Date format'), self.date_fmt)
        gen.addRow(L('كتابة المئات', 'Spelling of hundreds'), self.hundred)
        gen.addRow(L('الأرقام المطبوعة', 'Printed figures'), self.digits)
        gen.addRow(L('خانة الفلوس عند عدم وجودها', 'Fils box when zero'), self.zero_fils)
        gen.addRow(L('إطار رقم الدنانير', 'Around the dinars figure'), self.wrap)
        gen.addRow('', self.thousands)
        bg = QPushButton(L('تحميل صورة الشيك الفارغ (للمعاينة فقط)', 'Load a scan of the blank cheque (preview only)'))
        bg.clicked.connect(self.load_background)
        gen.addRow(bg)
        g1 = QGroupBox(L('القالب', 'Template'))
        g1.setLayout(gen)

        fd = QFormLayout()
        fd.addRow(L('الورق', 'Paper'), self.paper)
        fd.addRow(L('اتجاه إدخال الشيك', 'Feed direction'), self.rotate)
        fd.addRow(L('موضعه في الطابعة', 'Position in the printer'), self.align)
        fd.addRow(L('إزاحة أفقية (مم)', 'Shift right/left (mm)'), self.off_x)
        fd.addRow(L('إزاحة رأسية (مم)', 'Shift down/up (mm)'), self.off_y)
        g2 = QGroupBox(L('الطابعة (تُضبط بعد الطباعة التجريبية)', 'Printer (set after a test print)'))
        g2.setLayout(fd)

        self.fields = QListWidget()
        for key in FIELDS:
            it = QListWidgetItem(L(*FIELDS[key]))
            it.setData(Qt.UserRole, key)
            self.fields.addItem(it)
        self.fields.currentItemChanged.connect(self._field_selected)
        self.f_visible = QCheckBox(L('يُطبع', 'Printed'))
        self.f_x, self.f_y = self._dspin(-20, 300, 0), self._dspin(-20, 200, 0)
        self.f_w, self.f_h = self._dspin(1, 300, 30), self._dspin(1, 100, 7)
        self.f_size = QDoubleSpinBox()
        self.f_size.setRange(5, 36)
        self.f_size.setSingleStep(0.5)
        self.f_align = QComboBox()
        for k, ar, en in (('right', 'يمين', 'Right'), ('center', 'وسط', 'Centre'), ('left', 'يسار', 'Left')):
            self.f_align.addItem(L(ar, en), k)
        self.f_bold = QCheckBox(L('عريض', 'Bold'))
        self.f_spacing = self._dspin(0, 20, 0)
        self.f_spacing.setToolTip(L('للتاريخ في مربعات: المسافة بين الأرقام (0 = نص عادي)', 'For a boxed date: distance between digits (0 = normal text)'))
        self.f_angle = self._dspin(-90, 90, 0)
        ff = QFormLayout()
        ff.addRow('', self.f_visible)
        xy = QHBoxLayout()
        xy.addWidget(QLabel('X'))
        xy.addWidget(self.f_x)
        xy.addWidget(QLabel('Y'))
        xy.addWidget(self.f_y)
        ff.addRow(L('الموضع (مم)', 'Position (mm)'), xy)
        wh = QHBoxLayout()
        wh.addWidget(QLabel(L('عرض', 'W')))
        wh.addWidget(self.f_w)
        wh.addWidget(QLabel(L('ارتفاع', 'H')))
        wh.addWidget(self.f_h)
        ff.addRow(L('المقاس (مم)', 'Size (mm)'), wh)
        ff.addRow(L('حجم الخط', 'Font size'), self.f_size)
        ff.addRow(L('المحاذاة', 'Alignment'), self.f_align)
        ff.addRow('', self.f_bold)
        ff.addRow(L('مسافة الأرقام (مم)', 'Digit spacing (mm)'), self.f_spacing)
        ff.addRow(L('زاوية الختم', 'Stamp angle'), self.f_angle)
        for w in (self.f_x, self.f_y, self.f_w, self.f_h, self.f_size, self.f_spacing, self.f_angle):
            w.valueChanged.connect(self._field_edited)
        for w in (self.f_visible, self.f_bold):
            w.toggled.connect(self._field_edited)
        self.f_align.currentIndexChanged.connect(self._field_edited)
        shift = QHBoxLayout()
        self.dx, self.dy = self._dspin(-50, 50, 0), self._dspin(-50, 50, 0)
        apply_shift = QPushButton(L('إزاحة كل الحقول', 'Shift all fields'))
        apply_shift.clicked.connect(self.shift_all)
        shift.addWidget(QLabel('X'))
        shift.addWidget(self.dx)
        shift.addWidget(QLabel('Y'))
        shift.addWidget(self.dy)
        shift.addWidget(apply_shift)
        g3 = QGroupBox(L('الحقول', 'Fields'))
        l3 = QVBoxLayout(g3)
        l3.addWidget(self.fields, 1)
        l3.addLayout(ff)
        l3.addLayout(shift)

        for w in (self.width, self.height, self.off_x, self.off_y):
            w.valueChanged.connect(self._general_edited)
        for w in (self.words_lang, self.paper, self.rotate, self.align, self.hundred, self.digits):
            w.currentIndexChanged.connect(self._general_edited)
        for w in (self.sub_digits, self.thousands):
            w.toggled.connect(self._general_edited)
        self.font.currentFontChanged.connect(self._general_edited)
        self.date_fmt.currentTextChanged.connect(self._general_edited)
        self.wrap.textChanged.connect(self._general_edited)
        self.zero_fils.textChanged.connect(self._general_edited)

        right = QWidget()
        rl = QVBoxLayout(right)
        tabs = QTabWidget()
        a, b = QWidget(), QWidget()
        la, lb = QVBoxLayout(a), QVBoxLayout(b)
        la.addWidget(g1)
        la.addWidget(g2)
        la.addStretch(1)
        lb.addWidget(g3)
        tabs.addTab(b, L('الحقول', 'Fields'))
        tabs.addTab(a, L('القالب والطابعة', 'Template & printer'))
        rl.addWidget(tabs)

        btns = QHBoxLayout()
        for label, cb in ((L('طباعة صفحة المعايرة', 'Print the calibration sheet'), lambda: self._print(True)),
                          (L('طباعة شيك تجريبي', 'Print a sample cheque'), lambda: self._print(False)),
                          (L('معاينة الطباعة', 'Print preview'), self._preview),
                          (L('استعادة القالب الافتراضي', 'Reset to default'), self.reset)):
            bt = QPushButton(label)
            bt.clicked.connect(cb)
            btns.addWidget(bt)
        btns.addStretch(1)
        save = QPushButton(L('حفظ', 'Save'))
        save.setProperty('primary', True)
        save.clicked.connect(self.save)
        cancel = QPushButton(L('إلغاء', 'Cancel'))
        cancel.clicked.connect(self.reject)
        btns.addWidget(save)
        btns.addWidget(cancel)

        sp = QSplitter()
        sp.addWidget(left_tabs)
        sp.addWidget(right)
        sp.setStretchFactor(0, 3)
        sp.setStretchFactor(1, 2)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(L('١) اسحب كل حقل إلى مكانه على صورة الشيك أو اكتب موضعه بالمليمتر. ٢) اطبع «صفحة المعايرة» على ورقة عادية وضع الشيك فوقها مقابل الضوء. ٣) صحّح «الإزاحة» حتى تتطابق، ثم اطبع «شيكاً تجريبياً».',
                                 '1) Drag every field onto the cheque scan or type its position in mm. 2) Print the «calibration sheet» on plain paper and hold a cheque over it against the light. 3) Correct the «shift» until they match, then print a «sample cheque».')))
        lay.addWidget(sp, 1)
        lay.addLayout(btns)
        self.build_scene()
        self.fields.setCurrentRow(0)

    @staticmethod
    def _dspin(lo, hi, val):
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(1)
        s.setSingleStep(0.5)
        s.setValue(float(val))
        return s

    # ── scene ────────────────────────────────────────────────────────
    def build_scene(self):
        self.scene.clear()
        w, h = float(self.tpl['width_mm']) * S, float(self.tpl['height_mm']) * S
        img = load_background(self.background)
        if img is not None:
            pm = self.scene.addPixmap(QPixmap.fromImage(img).scaled(int(w), int(h), Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
            pm.setZValue(-2)
        else:
            self.scene.addRect(QRectF(0, 0, w, h), QPen(Qt.NoPen), QBrush(QColor('#fffaf3'))).setZValue(-2)
        frame = self.scene.addRect(QRectF(0, 0, w, h), QPen(QColor('#555'), 1.5))
        frame.setZValue(-1)
        self.items = {}
        for key, f in self.tpl['fields'].items():
            if key not in FIELDS:
                continue
            it = FieldItem(key, f, self._moved)
            it.setOpacity(1.0 if f.get('visible', True) else 0.35)
            self.scene.addItem(it)
            self.items[key] = it
        self.scene.setSceneRect(QRectF(-20, -20, w + 40, h + 40))
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def _moved(self, key, x, y):
        f = self.tpl['fields'][key]
        f['x'], f['y'] = round(x, 1), round(y, 1)
        cur = self.fields.currentItem()
        if cur and cur.data(Qt.UserRole) == key and not self._syncing:
            self._syncing = True
            self.f_x.setValue(f['x'])
            self.f_y.setValue(f['y'])
            self._syncing = False
        elif not self._syncing:
            for i in range(self.fields.count()):
                if self.fields.item(i).data(Qt.UserRole) == key:
                    self.fields.setCurrentRow(i)

    def _field_selected(self, cur, _prev):
        if not cur:
            return
        key = cur.data(Qt.UserRole)
        f = self.tpl['fields'][key]
        self._syncing = True
        self.f_visible.setChecked(bool(f.get('visible', True)))
        self.f_x.setValue(float(f['x']))
        self.f_y.setValue(float(f['y']))
        self.f_w.setValue(float(f.get('w') or 30))
        self.f_h.setValue(float(f.get('h') or 7))
        self.f_size.setValue(float(f.get('size') or 10))
        self.f_align.setCurrentIndex(max(0, self.f_align.findData(f.get('align') or 'center')))
        self.f_bold.setChecked(bool(f.get('bold')))
        self.f_spacing.setValue(float(f.get('spacing') or 0))
        self.f_angle.setValue(float(f.get('angle') or 0))
        self.f_spacing.setEnabled(key in ('date', 'cheque_no', 'amount_dinar'))
        self.f_angle.setEnabled(key == 'crossing')
        self._syncing = False
        for k, it in self.items.items():
            it.setSelected(k == key)

    def _field_edited(self, *_):
        if self._syncing or not self.fields.currentItem():
            return
        key = self.fields.currentItem().data(Qt.UserRole)
        f = self.tpl['fields'][key]
        f.update({'visible': self.f_visible.isChecked(), 'x': self.f_x.value(), 'y': self.f_y.value(),
                  'w': self.f_w.value(), 'h': self.f_h.value(), 'size': self.f_size.value(),
                  'align': self.f_align.currentData(), 'bold': self.f_bold.isChecked(),
                  'spacing': self.f_spacing.value(), 'angle': self.f_angle.value()})
        it = self.items.get(key)
        if it:
            self._syncing = True
            it.setRect(0, 0, f['w'] * S, f['h'] * S)
            it.setPos(f['x'] * S, f['y'] * S)
            it.setOpacity(1.0 if f['visible'] else 0.35)
            self._syncing = False
        self._refresh_preview()

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
                     'align': self.align.currentData(), 'offset_x': self.off_x.value(), 'offset_y': self.off_y.value()}
        if resized:
            self.build_scene()
        self._refresh_preview()

    def shift_all(self):
        dx, dy = self.dx.value(), self.dy.value()
        for f in self.tpl['fields'].values():
            f['x'] = round(float(f['x']) + dx, 1)
            f['y'] = round(float(f['y']) + dy, 1)
        self.build_scene()
        self._field_selected(self.fields.currentItem(), None)
        self._refresh_preview()

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
        self.build_scene()
        self._refresh_preview()

    def _values(self):
        return cheque_values(self.tpl, SAMPLE, self.ctx.crossing_texts())

    def _refresh_preview(self):
        self.preview.show_cheque(self.tpl, self._values(), load_background(self.background),
                                 labels={'bank': self.name.text().strip(), 'holder': 'اسم صاحب الحساب'})

    def _print(self, calibration):
        print_jobs(self, [(copy.deepcopy(self.tpl), self._values())], self.db.get, self.db.set, calibration=calibration)

    def _preview(self):
        preview_jobs(self, [(copy.deepcopy(self.tpl), self._values())], self.db.get)

    def save(self):
        name = self.name.text().strip()
        if not name:
            error(self, L('أدخل اسم البنك أو القالب.', 'Enter the bank / template name.'))
            return
        self.bank_id = self.db.save_bank({'name': name, 'name_en': self.name_en.text().strip() or None,
                                          'template': self.tpl, 'background': self.background,
                                          'is_active': (self.db.bank(self.bank_id) or {}).get('is_active', 1) if self.bank_id else 1},
                                         self.bank_id)
        info(self, L('حُفظ القالب.', 'Template saved.'))
        self.accept()
