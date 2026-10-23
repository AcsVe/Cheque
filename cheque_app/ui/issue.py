"""«إصدار شيك»: the cheque form with the live preview, save / save & print / reprint / new."""
from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QCompleter, QDateEdit, QDialog, QDialogButtonBox,
                               QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton,
                               QSpinBox, QVBoxLayout, QWidget)

from ..core.db import CROSSINGS, STATUSES, to_decimal
from ..core.render import cheque_values
from ..core.tafqeet import amount_words
from .common import DataTable, L, confirm, error, info
from .printing import ChequePreview, load_background, preview_jobs, print_jobs

ERRORS = {
    'amount': ('أدخل مبلغاً صحيحاً أكبر من صفر.', 'Enter a valid amount greater than zero.'),
    'payee': ('أدخل اسم المستفيد.', 'Enter the payee name.'),
    'account': ('اختر الحساب البنكي.', 'Choose the bank account.'),
    'duplicate': ('رقم الشيك مستخدم لشيك آخر في هذا الحساب.', 'This cheque number is already used in this account.'),
    'beyond_book': ('رقم الشيك بعد آخر رقم في دفتر الشيكات لهذا الحساب.', 'The cheque number is past the last number of this account\'s cheque book.'),
    'cancelled': ('لا يمكن تعديل شيك ملغى.', 'A cancelled cheque cannot be edited.'),
}


class PickDialog(QDialog):
    """Choose one row from a table (cheques of an account, or payees)."""

    def __init__(self, parent, title, columns, rows):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(820, 480)
        self.table = DataTable(columns)
        self.table.view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.set_rows(rows)
        self.table.activated.connect(lambda _id: self.accept())
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(L('اختيار', 'Choose'))
        bb.button(QDialogButtonBox.Cancel).setText(L('إلغاء', 'Cancel'))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.table)
        lay.addWidget(bb)

    def chosen(self):
        ids = self.table.selected_ids()
        return ids[0] if ids else None


class IssueTab(QWidget):
    saved = Signal()

    def __init__(self, app_ctx):
        super().__init__()
        self.ctx = app_ctx
        self.db = app_ctx.db
        self.cheque_id = None

        self.account = QComboBox()
        self.account.currentIndexChanged.connect(self._account_changed)
        self.number = QSpinBox()
        self.number.setRange(1, 999999999)
        self.number.valueChanged.connect(self._number_changed)
        find_no = QPushButton('؟')
        find_no.setToolTip(L('فتح شيك محفوظ', 'Open a saved cheque'))
        find_no.setFixedWidth(34)
        find_no.clicked.connect(self.pick_cheque)
        self.date = QDateEdit(QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat('dd/MM/yyyy')
        self.date.setLayoutDirection(Qt.LeftToRight)
        self.date.dateChanged.connect(self.refresh_preview)
        self.payee = QComboBox()
        self.payee.setEditable(True)
        self.payee.setInsertPolicy(QComboBox.NoInsert)
        self.payee.lineEdit().setPlaceholderText(L('اكتب أو اختر المستفيد', 'Type or choose the payee'))
        self.payee.editTextChanged.connect(self.refresh_preview)
        find_payee = QPushButton('؟')
        find_payee.setToolTip(L('اختيار من قائمة المستفيدين', 'Choose from the payees list'))
        find_payee.setFixedWidth(34)
        find_payee.clicked.connect(self.pick_payee)
        self.amount = QLineEdit()
        self.amount.setPlaceholderText('0.000')
        self.amount.setAlignment(Qt.AlignCenter)
        self.amount.setLayoutDirection(Qt.LeftToRight)
        self.number.setLayoutDirection(Qt.LeftToRight)
        self.amount.textChanged.connect(self._amount_changed)
        self.words = QLineEdit()
        self.words.setReadOnly(True)
        self.words_manual = QCheckBox(L('تعديل النص يدوياً', 'Edit the text by hand'))
        self.words_manual.toggled.connect(self._manual_toggled)
        self.words.textEdited.connect(self.refresh_preview)
        self.memo = QLineEdit()
        self.memo.setPlaceholderText(L('سبب الدفع أو رقم الفاتورة (لا يُطبع إلا إن فُعِّل في القالب)',
                                       'Purpose or invoice number (printed only if enabled in the template)'))
        self.memo.textChanged.connect(self.refresh_preview)
        self.crossing = QButtonGroup(self)
        cross_box = QGroupBox(L('التسطير', 'Crossing'))
        cl = QVBoxLayout(cross_box)
        for key, (ar, en) in CROSSINGS.items():
            rb = QRadioButton(L(ar, en))
            rb.setProperty('key', key)
            self.crossing.addButton(rb)
            cl.addWidget(rb)
            if key == 'none':
                rb.setChecked(True)
        self.crossing.buttonToggled.connect(lambda *_: self.refresh_preview())
        self.status = QLabel()
        self.status.setObjectName('status')

        g = QGridLayout()
        r = 0
        g.addWidget(QLabel(L('الحساب', 'Account')), r, 0)
        g.addWidget(self.account, r, 1, 1, 2)
        g.addWidget(QLabel(L('التاريخ', 'Date')), r, 3)
        g.addWidget(self.date, r, 4)
        r += 1
        g.addWidget(QLabel(L('رقم الشيك', 'Cheque no.')), r, 0)
        g.addWidget(self.number, r, 1)
        g.addWidget(find_no, r, 2)
        g.addWidget(cross_box, r, 3, 4, 2)
        r += 1
        g.addWidget(QLabel(L('اسم المستفيد', 'Payee')), r, 0)
        g.addWidget(self.payee, r, 1)
        g.addWidget(find_payee, r, 2)
        r += 1
        g.addWidget(QLabel(L('المبلغ', 'Amount')), r, 0)
        g.addWidget(self.amount, r, 1, 1, 2)
        r += 1
        g.addWidget(QLabel(L('المبلغ كتابةً', 'In words')), r, 0)
        g.addWidget(self.words, r, 1, 1, 2)
        r += 1
        g.addWidget(QLabel(''), r, 0)
        g.addWidget(self.words_manual, r, 1, 1, 2)
        r += 1
        g.addWidget(QLabel(L('البيان', 'Memo')), r, 0)
        g.addWidget(self.memo, r, 1, 1, 4)
        g.setColumnStretch(1, 3)
        g.setColumnStretch(4, 1)

        btns = QHBoxLayout()
        self.b_save = QPushButton(L('حفظ البيانات', 'Save'))
        self.b_print = QPushButton(L('حفظ وطباعة', 'Save && print'))
        self.b_print.setProperty('primary', True)
        self.b_reprint = QPushButton(L('إعادة طباعة', 'Reprint'))
        self.b_preview = QPushButton(L('معاينة الطباعة', 'Print preview'))
        self.b_new = QPushButton(L('شيك جديد', 'New cheque'))
        self.b_save.clicked.connect(lambda: self.save(print_after=False))
        self.b_print.clicked.connect(lambda: self.save(print_after=True))
        self.b_reprint.clicked.connect(self.reprint)
        self.b_preview.clicked.connect(self.preview)
        self.b_new.clicked.connect(self.new)
        for b in (self.b_save, self.b_print, self.b_reprint, self.b_preview, self.b_new):
            btns.addWidget(b)

        self.preview_w = ChequePreview()
        lay = QVBoxLayout(self)
        lay.addLayout(g)
        lay.addLayout(btns)
        lay.addWidget(self.status)
        lay.addWidget(self.preview_w, 1)
        self.reload_lists()
        self.new()

    # ── lists ────────────────────────────────────────────────────────
    def reload_lists(self):
        cur = self.account.currentData()
        self.account.blockSignals(True)
        self.account.clear()
        for a in self.db.accounts(active_only=True):
            self.account.addItem(f'{a["bank_name"]} — {a["name"]}' + (f' ({a["number"]})' if a.get('number') else ''), a['id'])
        default = cur or (int(self.db.get('default_account')) if (self.db.get('default_account') or '').isdigit() else None)
        i = self.account.findData(default)
        self.account.setCurrentIndex(i if i >= 0 else 0)
        self.account.blockSignals(False)
        text = self.payee.currentText()
        self.payee.blockSignals(True)
        self.payee.clear()
        names = [p['name'] for p in self.db.payees(active_only=True)]
        self.payee.addItems(names)
        comp = QCompleter(names, self)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        comp.setFilterMode(Qt.MatchContains)
        self.payee.setCompleter(comp)
        self.payee.setEditText(text)
        self.payee.blockSignals(False)
        self.refresh_preview()

    def _account_changed(self, *_):
        if self.cheque_id is None and self.account.currentData():
            self.number.blockSignals(True)
            self.number.setValue(self.db.next_cheque_no(self.account.currentData()))
            self.number.blockSignals(False)
        self._number_changed()

    def _number_changed(self, *_):
        acc = self.account.currentData()
        if acc and self.cheque_id is None:
            dup = self.db.find_cheque(acc, self.number.value())
            self._status(L(f'تنبيه: الشيك رقم {self.number.value()} محفوظ مسبقاً — اضغط «؟» لفتحه.',
                           f'Note: cheque {self.number.value()} is already saved — press «?» to open it.')
                         if dup else L('شيك جديد', 'New cheque'), warn=bool(dup))
        self.refresh_preview()

    def _amount_changed(self, *_):
        if not self.words_manual.isChecked():
            self.words.setText(self._auto_words())
        self.refresh_preview()

    def _manual_toggled(self, on):
        self.words.setReadOnly(not on)
        if not on:
            self.words.setText(self._auto_words())
        self.refresh_preview()

    def _template(self):
        acc = self.db.account(self.account.currentData()) if self.account.currentData() else None
        if not acc:
            return None, None, None
        return self.db.template(acc['bank_id']), self.db.bank(acc['bank_id']), acc

    def _auto_words(self):
        tpl, _b, acc = self._template()
        a = to_decimal(self.amount.text())
        if not tpl or a is None or a <= 0:
            return ''
        return amount_words(a, tpl.get('words_lang', 'ar'), currency=acc['currency'],
                            sub_as_digits=tpl.get('sub_as_digits', False), hundred=tpl.get('hundred', 'مئة'))

    def crossing_key(self):
        b = self.crossing.checkedButton()
        return b.property('key') if b else 'none'

    def data(self):
        return {'account_id': self.account.currentData(), 'cheque_no': self.number.value(),
                'cheque_date': self.date.date().toString('yyyy-MM-dd'), 'payee': self.payee.currentText().strip(),
                'amount': self.amount.text(), 'crossing': self.crossing_key(), 'memo': self.memo.text().strip() or None,
                'words': self.words.text().strip() if self.words_manual.isChecked() else None}

    def _values(self, d=None):
        tpl, bank, acc = self._template()
        d = d or self.data()
        a = to_decimal(d.get('amount'))
        vals = dict(d, amount=str(a) if a and a > 0 else '0', currency=acc['currency'] if acc else 'JOD')
        return tpl, bank, cheque_values(tpl, vals, self.ctx.crossing_texts()) if tpl else {}

    def refresh_preview(self, *_):
        tpl, bank, values = self._values()
        if tpl:
            acc = self.db.account(self.account.currentData())
            self.preview_w.show_cheque(tpl, values, load_background(bank.get('background')),
                                       labels={'bank': bank.get('name'), 'holder': acc.get('name') if acc else '',
                                               'account': acc.get('number') if acc else ''})

    def _status(self, text, warn=False):
        self.status.setText(text)
        self.status.setProperty('warn', warn)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    # ── actions ──────────────────────────────────────────────────────
    def new(self):
        self.cheque_id = None
        self.payee.setEditText('')
        self.amount.clear()
        self.memo.clear()
        self.words_manual.setChecked(False)
        self.words.clear()
        for b in self.crossing.buttons():
            if b.property('key') == (self.db.get('default_crossing') or 'none'):
                b.setChecked(True)
        self.date.setDate(QDate.currentDate())
        self.b_reprint.setEnabled(False)
        self._account_changed()
        self.payee.setFocus()

    def load(self, cheque_id):
        c = self.db.cheque(cheque_id)
        if not c:
            return
        self.cheque_id = c['id']
        i = self.account.findData(c['account_id'])
        if i < 0:
            self.account.addItem(f'{c["bank_name"]} — {c["account_name"]}', c['account_id'])
            i = self.account.count() - 1
        self.account.blockSignals(True)
        self.account.setCurrentIndex(i)
        self.account.blockSignals(False)
        self.number.blockSignals(True)
        self.number.setValue(int(c['cheque_no']))
        self.number.blockSignals(False)
        self.date.setDate(QDate.fromString(c['cheque_date'], 'yyyy-MM-dd'))
        self.payee.setEditText(c['payee'])
        self.amount.setText(c['amount'])
        self.memo.setText(c.get('memo') or '')
        for b in self.crossing.buttons():
            b.setChecked(b.property('key') == c['crossing'])
        auto = self._auto_words()
        manual = bool(c.get('words')) and c['words'] != auto
        self.words_manual.setChecked(manual)
        self.words.setText(c['words'] if manual else auto)
        st = STATUSES.get(c['status'], (c['status'],) * 2)
        self._status(L(f'الشيك رقم {c["cheque_no"]} — {st[0]} (طُبع {c["print_count"]} مرة)',
                       f'Cheque {c["cheque_no"]} — {st[1]} (printed {c["print_count"]} times)'),
                     warn=c['status'] == 'cancelled')
        self.b_reprint.setEnabled(c['status'] != 'cancelled')
        self.refresh_preview()

    def save(self, print_after=False):
        d = self.data()
        if self.cheque_id:
            cur = self.db.cheque(self.cheque_id)
            if cur and cur['status'] == 'printed' and not confirm(self, L(
                    'هذا الشيك مطبوع. هل تريد حفظ التعديل عليه؟', 'This cheque has been printed. Save the change?')):
                return
        if print_after and not self.ctx.license().can_print:
            self.ctx.license_blocked(self)
            return
        try:
            self.cheque_id = self.db.save_cheque(d, self.cheque_id)
        except ValueError as e:
            ar, en = ERRORS.get(str(e), (str(e), str(e)))
            error(self, L(ar, en))
            return
        self.saved.emit()
        self.reload_lists()
        if print_after:
            self._print(self.cheque_id)
        self.load(self.cheque_id)
        if not print_after:
            self._status(L(f'حُفظ الشيك رقم {d["cheque_no"]}.', f'Cheque {d["cheque_no"]} saved.'))

    def _print(self, cheque_id):
        c = self.db.cheque(cheque_id)
        tpl = self.db.template(c['bank_id'])
        values = cheque_values(tpl, c, self.ctx.crossing_texts())
        if print_jobs(self, [(tpl, values)], self.db.get, self.db.set, ask=self.db.get('ask_printer', '1') == '1'):
            self.db.mark_printed(cheque_id)
            self.saved.emit()
            return True
        return False

    def reprint(self):
        if not self.cheque_id:
            return
        if not self.ctx.license().can_print:
            self.ctx.license_blocked(self)
            return
        if confirm(self, L('إعادة طباعة هذا الشيك برقمه نفسه؟ (عند تلف الشيك المطبوع يُفضَّل إلغاؤه وإصدار شيك جديد)',
                           'Reprint this cheque with the same number? (If the printed cheque was spoiled, cancelling it and issuing a new one is better.)')):
            self._print(self.cheque_id)
            self.load(self.cheque_id)

    def preview(self):
        tpl, _bank, values = self._values()
        if tpl:
            preview_jobs(self, [(tpl, values)], self.db.get)

    def pick_cheque(self):
        acc = self.account.currentData()
        if not acc:
            return
        rows = [(c['id'], [(c['cheque_no'], int(c['cheque_no'])), c['cheque_date'], c['payee'],
                           (c['amount'], float(c['amount'])), L(*STATUSES.get(c['status'], (c['status'],) * 2))])
                for c in self.db.cheques('c.account_id = ?', (acc,))]
        dlg = PickDialog(self, L('الشيكات المحفوظة', 'Saved cheques'),
                         [(L('الرقم', 'No.'), 'num'), (L('التاريخ', 'Date'), 'text'), (L('المستفيد', 'Payee'), 'text'),
                          (L('المبلغ', 'Amount'), 'num'), (L('الحالة', 'Status'), 'select')], rows)
        if dlg.exec() and dlg.chosen():
            self.load(dlg.chosen())

    def pick_payee(self):
        rows = [(p['id'], [p['name'], p.get('name_en') or '', p.get('phone') or '', (p['cheques'], p['cheques'])])
                for p in self.db.payees(active_only=True)]
        dlg = PickDialog(self, L('المستفيدون', 'Payees'),
                         [(L('الاسم', 'Name'), 'text'), (L('الاسم بالإنجليزية', 'English name'), 'text'),
                          (L('الهاتف', 'Phone'), 'text'), (L('عدد الشيكات', 'Cheques'), 'num')], rows)
        if dlg.exec() and dlg.chosen():
            p = next((x for x in self.db.payees() if x['id'] == dlg.chosen()), None)
            if p:
                self.payee.setEditText(p['name'])
