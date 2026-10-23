"""Main window: tabs for issuing, the register, payees, banks/accounts and settings, plus the licence dialog."""
import os
from datetime import date, datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QGuiApplication, QIcon
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
                               QTabWidget, QVBoxLayout, QWidget)

from .. import __version__
from ..core import license as lic
from ..core.db import CROSSINGS
from ..core.templates import CROSSING_TEXT
from .common import L, confirm, error, info, lang
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
        fp = QLineEdit(st.fingerprint)
        fp.setReadOnly(True)
        fp.setAlignment(Qt.AlignCenter)
        fp.setLayoutDirection(Qt.LeftToRight)
        copy_btn = QPushButton(L('نسخ', 'Copy'))
        copy_btn.clicked.connect(lambda: (QGuiApplication.clipboard().setText(st.fingerprint),
                                          copy_btn.setText(L('نُسخت ✓', 'Copied ✓'))))
        self.key = QLineEdit()
        self.key.setLayoutDirection(Qt.LeftToRight)
        self.key.setPlaceholderText('YYYYMMDD:…')
        act = QPushButton(L('تفعيل', 'Activate'))
        act.setProperty('primary', True)
        act.clicked.connect(self.activate)
        f = QFormLayout(self)
        f.addRow(L('الحالة', 'Status'), self.state)
        row = QHBoxLayout()
        row.addWidget(fp, 1)
        row.addWidget(copy_btn)
        f.addRow(L('بصمة هذا الجهاز', 'This computer\'s fingerprint'), row)
        f.addRow(QLabel(L('أرسل البصمة إلى مزوّد البرنامج ليرسل لك مفتاح الترخيص لهذا الجهاز.',
                          'Send the fingerprint to the supplier to receive the licence key for this computer.')))
        f.addRow(L('مفتاح الترخيص', 'Licence key'), self.key)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.button(QDialogButtonBox.Close).setText(L('إغلاق', 'Close'))
        bb.rejected.connect(self.reject)
        row2 = QHBoxLayout()
        row2.addWidget(act)
        row2.addStretch(1)
        row2.addWidget(bb)
        f.addRow(row2)
        self.resize(620, 230)

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
        self.default_crossing = QComboBox()
        for k, (ar, en) in CROSSINGS.items():
            self.default_crossing.addItem(L(ar, en), k)
        self.default_crossing.setCurrentIndex(max(0, self.default_crossing.findData(self.db.get('default_crossing') or 'none')))
        self.ask_printer = QCheckBox(L('اختيار الطابعة عند كل طباعة', 'Choose the printer at every print'))
        self.ask_printer.setChecked(self.db.get('ask_printer', '1') == '1')
        self.cross = {}
        cf = QFormLayout()
        for k in ('first', 'account', 'both'):
            e = QLineEdit(self.db.get(f'crossing_text_{k}') or CROSSING_TEXT[k])
            self.cross[k] = e
            cf.addRow(L(*CROSSINGS[k]), e)
        g_cross = QGroupBox(L('نص ختم التسطير المطبوع', 'Printed crossing text'))
        g_cross.setLayout(cf)

        self.backup_dir = QLineEdit(self.db.get('backup_dir') or os.path.join(ctx.data_dir, 'backups'))
        pick = QPushButton(L('اختيار…', 'Choose…'))
        pick.clicked.connect(self._pick_backup)
        bnow = QPushButton(L('نسخة احتياطية الآن', 'Back up now'))
        bnow.clicked.connect(self.backup_now)
        rest = QPushButton(L('استرجاع نسخة…', 'Restore a backup…'))
        rest.clicked.connect(self.restore)
        bl = QHBoxLayout()
        bl.addWidget(self.backup_dir, 1)
        bl.addWidget(pick)
        bl2 = QHBoxLayout()
        bl2.addWidget(bnow)
        bl2.addWidget(rest)
        bl2.addStretch(1)
        g_bk = QGroupBox(L('النسخ الاحتياطي (يومياً عند فتح البرنامج، وتُحفظ آخر 30 نسخة)',
                           'Backups (daily when the program opens; the last 30 are kept)'))
        vb = QVBoxLayout(g_bk)
        vb.addLayout(bl)
        vb.addLayout(bl2)
        vb.addWidget(QLabel(L(f'مجلد البيانات: {ctx.data_dir}', f'Data folder: {ctx.data_dir}')))

        lic_btn = QPushButton(L('ترخيص الاستخدام…', 'Licence…'))
        lic_btn.clicked.connect(lambda: LicenseDialog(self, ctx).exec())
        save = QPushButton(L('حفظ الإعدادات', 'Save settings'))
        save.setProperty('primary', True)
        save.clicked.connect(self.save)
        f = QFormLayout()
        f.addRow(L('لغة البرنامج', 'Language'), self.lang)
        f.addRow(L('التسطير الافتراضي', 'Default crossing'), self.default_crossing)
        f.addRow('', self.ask_printer)
        lay = QVBoxLayout(self)
        lay.addLayout(f)
        lay.addWidget(g_cross)
        lay.addWidget(g_bk)
        row = QHBoxLayout()
        row.addWidget(save)
        row.addWidget(lic_btn)
        row.addStretch(1)
        row.addWidget(QLabel(L(f'الإصدار {__version__}', f'Version {__version__}')))
        lay.addLayout(row)
        lay.addStretch(1)

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
        self.issue = IssueTab(ctx)
        self.register = RegisterTab(ctx)
        self.payees = PayeesTab(ctx)
        self.banks = BanksTab(ctx)
        self.settings = SettingsTab(ctx)
        self.tabs.addTab(self.issue, L('إصدار شيك', 'Issue a cheque'))
        self.tabs.addTab(self.register, L('سجل الشيكات', 'Cheque register'))
        self.tabs.addTab(self.payees, L('المستفيدون', 'Payees'))
        self.tabs.addTab(self.banks, L('البنوك والحسابات', 'Banks & accounts'))
        self.tabs.addTab(self.settings, L('الإعدادات', 'Settings'))
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
