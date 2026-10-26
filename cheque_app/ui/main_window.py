"""Main window: tabs for issuing, the register, payees, banks/accounts and settings, plus the licence dialog."""
import os
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont, QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel,
                               QLineEdit, QMainWindow, QTabWidget, QVBoxLayout, QWidget)

from .. import __version__
from ..core import license as lic
from ..core.db import CROSSINGS
from ..core.templates import CROSSING_TEXT
from .common import L, confirm, error, info
from .theme import a11y, button, card, field, form_grid, icon, icon_button, ltr, muted, name_buttons
from .issue import IssueTab
from .lists import BanksTab, PayeesTab, RegisterTab


class LicenseDialog(QDialog):
    def __init__(self, parent, ctx):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle(L('ترخيص الاستخدام', 'Licence'))
        st = ctx.license(refresh=True)
        self.state = QLabel(st.describe(L))
        self.state.setObjectName('status')
        self.state.setProperty('warn', st.mode not in ('licensed',))
        a11y(self.state, L('حالة الترخيص', 'Licence status'))
        mono = QFont('Consolas')
        mono.setStyleHint(QFont.Monospace)
        mono.setPointSizeF(11)
        fp = ltr(QLineEdit(st.fingerprint), 240)
        fp.setReadOnly(True)
        fp.setFont(mono)
        fp.setAlignment(Qt.AlignCenter)
        copy_btn = icon_button('copy', L('نسخ البصمة', 'Copy the fingerprint'))
        copy_btn.clicked.connect(lambda: (QGuiApplication.clipboard().setText(st.fingerprint),
                                          copy_btn.setIcon(icon('check', '#166534')),
                                          copy_btn.setToolTip(L('نُسخت البصمة', 'Fingerprint copied'))))
        self.key = ltr(QLineEdit())
        self.key.setFont(mono)
        self.key.setPlaceholderText('YYYYMMDD:…')
        self.key.setMinimumWidth(380)
        act = button(L('تفعيل', 'Activate'), 'key', 'primary')
        act.clicked.connect(self.activate)
        g = form_grid()
        field(g, 0, 0, L('الحالة', 'Status'), self.state, 2)
        fp_row = QHBoxLayout()
        fp_row.setSpacing(6)
        fp_row.addWidget(fp)
        fp_row.addWidget(copy_btn)
        fp_row.addStretch(1)
        a11y(fp, L('بصمة هذا الجهاز', 'This computer\'s fingerprint'))
        field(g, 1, 0, L('بصمة هذا الجهاز', 'This computer\'s fingerprint'), fp_row, 2)
        note = muted(L('أرسل البصمة إلى مزوّد البرنامج ليرسل لك مفتاح الترخيص لهذا الجهاز.',
                       'Send the fingerprint to the supplier to receive the licence key for this computer.'))
        note.setWordWrap(True)
        g.addWidget(note, 2, 1, 1, 2)
        field(g, 3, 0, L('مفتاح الترخيص', 'Licence key'), self.key, 2)
        g.setColumnStretch(1, 1)
        box = card()
        box.setLayout(g)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.button(QDialogButtonBox.Close).setText(L('إغلاق', 'Close'))
        name_buttons(bb)
        bb.rejected.connect(self.reject)
        row2 = QHBoxLayout()
        row2.addWidget(act)
        row2.addStretch(1)
        row2.addWidget(bb)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 8, 18, 18)
        lay.setSpacing(14)
        lay.addWidget(box)
        lay.addLayout(row2)
        self.resize(max(640, self.sizeHint().width()), self.sizeHint().height())

    def activate(self):
        key = ''.join(self.key.text().split())
        ok, expired, exp = lic.check_license(key, self.ctx.license().fingerprint, date.today())
        if not ok:
            error(self, L('المفتاح غير صحيح لهذا الجهاز. تأكد من نسخه كاملاً، وأنه صادر لبصمة هذا الجهاز.',
                          'The key is not valid for this computer. Make sure it is copied in full and issued for this fingerprint.'))
            return
        if expired:
            error(self, L(f'هذا المفتاح انتهى في {exp}.', f'This key expired on {exp}.'))
            return
        lic.save_key(self.ctx.data_dir, key)
        st = self.ctx.license(refresh=True)
        self.state.setText(st.describe(L))
        self.state.setProperty('warn', False)
        self.state.style().polish(self.state)
        info(self, L('تم تفعيل الترخيص. شكراً لك.', 'The licence is active. Thank you.'))
        self.ctx.window.update_title()


class SettingsTab(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx, self.db = ctx, ctx.db
        self.lang = QComboBox()
        self.lang.addItem('العربية', 'ar')
        self.lang.addItem('English', 'en')
        self.lang.setCurrentIndex(max(0, self.lang.findData(self.db.get('lang', 'ar'))))
        self.lang.setFixedWidth(220)
        self.default_crossing = QComboBox()
        for k, (ar, en) in CROSSINGS.items():
            self.default_crossing.addItem(L(ar, en), k)
        self.default_crossing.setCurrentIndex(max(0, self.default_crossing.findData(self.db.get('default_crossing') or 'none')))
        self.default_crossing.setFixedWidth(260)
        self.ask_printer = a11y(QCheckBox(L('اختيار الطابعة عند كل طباعة', 'Choose the printer at every print')),
                                L('اختيار الطابعة عند كل طباعة', 'Choose the printer at every print'))
        self.ask_printer.setChecked(self.db.get('ask_printer', '1') == '1')
        g0 = form_grid()
        field(g0, 0, 0, L('لغة البرنامج', 'Language'), self.lang)
        field(g0, 1, 0, L('التسطير الافتراضي', 'Default crossing'), self.default_crossing)
        g0.addWidget(self.ask_printer, 2, 1)
        g0.setColumnStretch(2, 1)
        g_gen = card(L('عام', 'General'))
        g_gen.setLayout(g0)

        self.cross = {}
        cf = form_grid()
        for i, k in enumerate(('first', 'account', 'both')):
            e = QLineEdit(self.db.get(f'crossing_text_{k}') or CROSSING_TEXT[k])
            e.setMinimumWidth(380)
            self.cross[k] = e
            field(cf, i, 0, L(*CROSSINGS[k]), e)
            a11y(e, L('نص ختم التسطير: ', 'Crossing text: ') + L(*CROSSINGS[k]))
        cf.setColumnStretch(2, 1)
        g_cross = card(L('نص ختم التسطير المطبوع', 'Printed crossing text'))
        g_cross.setLayout(cf)

        self.backup_dir = ltr(QLineEdit(self.db.get('backup_dir') or os.path.join(ctx.data_dir, 'backups')))
        pick = icon_button('folder', L('اختيار مجلد النسخ الاحتياطية', 'Choose the backup folder'))
        pick.clicked.connect(self._pick_backup)
        bnow = button(L('نسخة احتياطية الآن', 'Back up now'), 'save')
        bnow.clicked.connect(self.backup_now)
        rest = button(L('استرجاع نسخة…', 'Restore a backup…'), 'reset')
        rest.clicked.connect(self.restore)
        bl = QHBoxLayout()
        bl.setSpacing(6)
        bl.addWidget(self.backup_dir, 1)
        bl.addWidget(pick)
        a11y(self.backup_dir, L('مجلد النسخ الاحتياطية', 'Backup folder'))
        bl2 = QHBoxLayout()
        bl2.addWidget(bnow)
        bl2.addWidget(rest)
        bl2.addStretch(1)
        gb = form_grid()
        field(gb, 0, 0, L('المجلد', 'Folder'), bl)
        gb.addLayout(bl2, 1, 1)
        data = muted(L(f'مجلد البيانات: {ctx.data_dir}', f'Data folder: {ctx.data_dir}'))
        data.setTextInteractionFlags(Qt.TextSelectableByMouse)
        gb.addWidget(data, 2, 1)
        gb.setColumnStretch(1, 1)
        g_bk = card(L('النسخ الاحتياطي (يومياً عند فتح البرنامج، وتُحفظ آخر 30 نسخة)',
                      'Backups (daily when the program opens; the last 30 are kept)'))
        g_bk.setLayout(gb)

        lic_btn = button(L('ترخيص الاستخدام…', 'Licence…'), 'key')
        lic_btn.clicked.connect(lambda: LicenseDialog(self, ctx).exec())
        save = button(L('حفظ الإعدادات', 'Save settings'), 'save', 'primary')
        save.clicked.connect(self.save)
        inner = QWidget()
        inner.setMaximumWidth(900)
        il = QVBoxLayout(inner)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(4)
        il.addWidget(g_gen)
        il.addWidget(g_cross)
        il.addWidget(g_bk)
        row = QHBoxLayout()
        row.setContentsMargins(0, 12, 0, 0)
        row.addWidget(save)
        row.addWidget(lic_btn)
        row.addStretch(1)
        row.addWidget(muted(L(f'الإصدار {__version__}', f'Version {__version__}')))
        il.addLayout(row)
        il.addStretch(1)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 14, 14)
        lay.addWidget(inner, 1)
        lay.addStretch(0)

    def _pick_backup(self):
        d = QFileDialog.getExistingDirectory(self, L('مجلد النسخ الاحتياطية', 'Backup folder'), self.backup_dir.text())
        if d:
            self.backup_dir.setText(d)

    def save(self):
        old_lang = self.db.get('lang', 'ar')
        self.db.set('lang', self.lang.currentData())
        self.db.set('default_crossing', self.default_crossing.currentData())
        self.db.set('ask_printer', '1' if self.ask_printer.isChecked() else '0')
        for k, e in self.cross.items():
            self.db.set(f'crossing_text_{k}', e.text().strip() or CROSSING_TEXT[k])
        self.db.set('backup_dir', self.backup_dir.text().strip())
        if old_lang != self.lang.currentData():
            info(self, L('تُطبَّق اللغة الجديدة عند إعادة فتح البرنامج.', 'The new language applies when the program is reopened.'))
        else:
            info(self, L('حُفظت الإعدادات.', 'Settings saved.'))
        self.ctx.window.refresh_all()

    def backup_now(self):
        try:
            path = self.db.backup(self.backup_dir.text().strip() or os.path.join(self.ctx.data_dir, 'backups'))
        except OSError as e:
            error(self, str(e))
            return
        self.db.set('last_backup', date.today().isoformat())
        info(self, L(f'حُفظت النسخة:\n{path}', f'Backup saved:\n{path}'))

    def restore(self):
        path, _ = QFileDialog.getOpenFileName(self, L('اختر نسخة احتياطية', 'Choose a backup'),
                                              self.backup_dir.text(), 'Backup (*.db)')
        if not path or not confirm(self, L('ستُستبدل البيانات الحالية بهذه النسخة (تُحفظ نسخة من الحالية أولاً). متابعة؟',
                                            'The current data will be replaced by this backup (a copy of it is saved first). Continue?')):
            return
        try:
            safety = self.db.restore(path)
        except Exception as e:  # noqa: BLE001
            error(self, L('ليست نسخة احتياطية صالحة لهذا البرنامج.', 'Not a valid backup of this program.') + f'\n{e}')
            return
        info(self, L(f'تم الاسترجاع. نسخة البيانات السابقة:\n{safety}', f'Restored. The previous data was saved to:\n{safety}'))
        self.ctx.window.refresh_all()


class MainWindow(QMainWindow):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        ctx.window = self
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(False)
        a11y(self.tabs, L('أقسام البرنامج', 'Program sections'))
        self.issue = IssueTab(ctx)
        self.register = RegisterTab(ctx)
        self.payees = PayeesTab(ctx)
        self.banks = BanksTab(ctx)
        self.settings = SettingsTab(ctx)
        for wdg, ic, ar, en in ((self.issue, 'print', 'إصدار شيك', 'Issue a cheque'),
                                (self.register, 'grid', 'سجل الشيكات', 'Cheque register'),
                                (self.payees, 'edit', 'المستفيدون', 'Payees'),
                                (self.banks, 'bank', 'البنوك والحسابات', 'Banks && accounts'),
                                (self.settings, 'calibrate', 'الإعدادات', 'Settings')):
            self.tabs.addTab(wdg, icon(ic, '#64748b'), L(ar, en))
            a11y(wdg, L(ar, en).replace('&&', '&'))
        self.setCentralWidget(self.tabs)
        self.issue.saved.connect(self.register.reload)
        self.issue.saved.connect(self.payees.reload)
        self.issue.saved.connect(self.banks.reload)
        self.register.open_cheque.connect(self.open_cheque)
        self.register.changed.connect(self.issue.reload_lists)
        self.payees.changed.connect(self.issue.reload_lists)
        self.banks.changed.connect(self.refresh_all)
        self.tabs.currentChanged.connect(self._tab_changed)
        lic_act = QAction(L('الترخيص', 'Licence'), self)
        lic_act.triggered.connect(lambda: LicenseDialog(self, ctx).exec())
        self.menuBar().addAction(lic_act)
        self.update_title()
        self.resize(1180, 820)

    def update_title(self):
        st = self.ctx.license(refresh=True)
        self.setWindowTitle(L('طباعة الشيكات', 'Cheque Printer') + f' {__version__} — ' + st.describe(L))

    def open_cheque(self, cid):
        self.issue.load(cid)
        self.tabs.setCurrentWidget(self.issue)

    def refresh_all(self):
        self.issue.reload_lists()
        self.register.reload()
        self.payees.reload()
        self.banks.reload()

    def _tab_changed(self, i):
        if self.tabs.widget(i) is self.register:
            self.register.reload()

    def showEvent(self, e):
        super().showEvent(e)
        if not self.ctx.db.accounts():
            info(self, L('مرحباً! ابدأ بإضافة حسابك البنكي (البنك، اسم الحساب، رقم الشيك التالي)، ثم عاير قالب البنك بطباعة تجريبية.',
                         'Welcome! Start by adding your bank account (bank, account name, next cheque number), then calibrate the bank template with a test print.'))
            self.tabs.setCurrentWidget(self.banks)
            self.banks.edit_account(None)
        st = self.ctx.license()
        if st.mode in ('expired', 'trial_over'):
            self.ctx.license_blocked(self)
