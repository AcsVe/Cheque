"""ChequePrinter — entry point. Data folder: %ProgramData%\\ChequePrinter on Windows (shared by the PC's users;
the installer gives users write access), ~/.cheque_printer elsewhere; CHEQUE_DATA overrides it."""
import os
import sys
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from . import __version__
from .core import license as lic
from .core.db import Database
from .core.templates import CROSSING_TEXT

STYLE = """
QWidget { font-size: 10.5pt; }
QMainWindow, QDialog { background: #f4f6f9; }
QTabWidget::pane { border: 1px solid #d9dee6; background: #fff; border-radius: 6px; }
QTabBar::tab { padding: 8px 18px; margin: 2px; border-radius: 6px; background: #e6ebf2; color: #1c2533; }
QTabBar::tab:selected { background: #12305e; color: #fff; }
QPushButton { padding: 6px 14px; border: 1px solid #1d5fbf; border-radius: 6px; background: #fff; color: #1d5fbf; }
QPushButton:hover { background: #eef4fd; }
QPushButton:disabled { color: #9aa4b2; border-color: #c9d0da; }
QPushButton[primary="true"] { background: #1d5fbf; color: #fff; font-weight: bold; }
QPushButton[danger="true"] { color: #b42318; border-color: #f1b8b2; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QPlainTextEdit { padding: 4px 6px; border: 1px solid #c9d0da; border-radius: 5px; background: #fff; }
QLineEdit:read-only { background: #f3f5f8; }
QHeaderView::section { background: #12305e; color: #fff; padding: 6px; border: 0; border-left: 1px solid #2b4a7c; font-weight: bold; }
QTableView { gridline-color: #e3e7ee; selection-background-color: #cfe0fb; selection-color: #000; alternate-background-color: #f8fafd; }
QGroupBox { font-weight: bold; border: 1px solid #d9dee6; border-radius: 6px; margin-top: 10px; padding-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; padding: 0 6px; }
QLabel#status { padding: 6px 10px; border-radius: 6px; background: #e6f5ed; color: #14532d; }
QLabel#status[warn="true"] { background: #fff4e0; color: #8a5a00; }
"""


def data_dir():
    if os.environ.get('CHEQUE_DATA'):
        return os.environ['CHEQUE_DATA']
    if sys.platform.startswith('win'):
        base = os.environ.get('PROGRAMDATA') or os.environ.get('APPDATA') or os.path.expanduser('~')
        return os.path.join(base, 'ChequePrinter')
    return os.path.join(os.path.expanduser('~'), '.cheque_printer')


def resource(name):
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, 'assets', name)


class AppContext:
    def __init__(self, folder):
        self.data_dir = folder
        os.makedirs(folder, exist_ok=True)
        self.db = Database(os.path.join(folder, 'cheques.db'))
        self.window = None
        self._license = None

    def license(self, refresh=False):
        if refresh or self._license is None:
            self._license = lic.current_state(self.data_dir)
        return self._license

    def license_blocked(self, parent):
        from .ui.common import L
        from .ui.main_window import LicenseDialog
        st = self.license(refresh=True)
        QMessageBox.warning(parent, L('الترخيص', 'Licence'),
                            st.describe(L) + '\n\n' + L('أدخل مفتاح الترخيص لهذا الجهاز لمتابعة الطباعة. البيانات محفوظة ويمكن عرضها.',
                                                        'Enter the licence key for this computer to continue printing. Your data is kept and can be viewed.'))
        LicenseDialog(parent, self).exec()

    def crossing_texts(self):
        return {k: self.db.get(f'crossing_text_{k}') or v for k, v in CROSSING_TEXT.items()}

    def daily_backup(self):
        today = date.today().isoformat()
        if self.db.get('last_backup') == today:
            return
        try:
            self.db.backup(self.db.get('backup_dir') or os.path.join(self.data_dir, 'backups'))
            self.db.set('last_backup', today)
        except OSError:
            pass


def selftest(out):
    import tempfile
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    app = QApplication.instance() or QApplication([])  # noqa: F841
    from .core.render import cheque_values
    from .core.tafqeet import words_ar
    from .ui.printing import save_pdf
    folder = tempfile.mkdtemp(prefix='cheque-selftest-')
    ctx = AppContext(folder)
    acc = ctx.db.save_account({'bank_id': ctx.db.banks()[0]['id'], 'name': 'test', 'next_no': 1})
    cid = ctx.db.save_cheque({'account_id': acc, 'cheque_no': 1, 'cheque_date': '2026-01-01', 'payee': 'اختبار',
                              'amount': '1250.750', 'crossing': 'first'})
    c = ctx.db.cheque(cid)
    tpl = ctx.db.template(c['bank_id'])
    pdf = os.path.join(folder, 'test.pdf')
    ok = save_pdf(pdf, [(tpl, cheque_values(tpl, c))]) and os.path.getsize(pdf) > 1000
    ok = ok and words_ar('1250.750').startswith('فقط ألف')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(('ok ' if ok else 'FAILED ') + lic.machine_fingerprint(folder) + '\n')
    ctx.db.close()
    return 0 if ok else 1


def main(argv=None):
    argv = argv if argv is not None else sys.argv
    if '--fingerprint' in argv:
        print(lic.machine_fingerprint(data_dir()))
        return 0
    if '--selftest' in argv:          # used by the build: render a cheque to PDF with a throw-away database
        return selftest(argv[argv.index('--selftest') + 1] if len(argv) > argv.index('--selftest') + 1 else 'selftest.txt')
    app = QApplication(argv)
    app.setApplicationName('ChequePrinter')
    app.setApplicationVersion(__version__)
    if os.path.isfile(resource('icon.ico')):
        app.setWindowIcon(QIcon(resource('icon.ico')))
    try:
        ctx = AppContext(data_dir())
    except Exception as e:  # noqa: BLE001 — folder not writable, damaged database…
        QMessageBox.critical(None, 'ChequePrinter', f'تعذّر فتح مجلد البيانات / Cannot open the data folder:\n{data_dir()}\n\n{e}')
        return 1
    from .ui.common import set_lang
    set_lang(ctx.db.get('lang', 'ar'))
    if ctx.db.get('lang', 'ar') != 'en':
        app.setLayoutDirection(Qt.RightToLeft)
    font = QFont('Segoe UI' if sys.platform.startswith('win') else app.font().family())
    font.setPointSizeF(10.5)
    app.setFont(font)
    app.setStyleSheet(STYLE)
    ctx.daily_backup()
    from .ui.main_window import MainWindow
    w = MainWindow(ctx)
    w.show()
    code = app.exec()
    ctx.db.close()
    return code


if __name__ == '__main__':
    sys.exit(main())
