"""The whole window offscreen: issue → save → register → print to PDF; template editor round trip."""
import os

import pytest

from PySide6.QtWidgets import QApplication, QMessageBox


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, 'information', staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, 'warning', staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, 'question', staticmethod(lambda *a, **k: QMessageBox.Yes))
    app = QApplication.instance() or QApplication([])  # noqa: F841
    from cheque_app.main import AppContext
    c = AppContext(str(tmp_path))
    c.db.save_account({'bank_id': c.db.banks()[0]['id'], 'name': 'الجاري', 'next_no': 100})
    yield c
    c.db.close()


def test_issue_save_and_register(ctx, monkeypatch):
    from cheque_app.ui import issue as issue_mod
    from cheque_app.ui.main_window import MainWindow
    printed = []
    monkeypatch.setattr(issue_mod, 'print_jobs', lambda parent, jobs, *a, **k: printed.append(jobs) or True)
    MainWindow.showEvent = lambda self, e: None
    w = MainWindow(ctx)
    t = w.issue
    assert t.number.value() == 100
    t.payee.setEditText('مؤسسة النور')
    t.amount.setText('1250.750')
    assert t.words.text() == 'فقط ألف ومئتان وخمسون دينارًا وسبعمئة وخمسون فلسًا لا غير'
    t.crossing.buttons()[1].setChecked(True)
    t.save(print_after=True)
    c = ctx.db.cheques()[0]
    assert c['cheque_no'] == 100 and c['status'] == 'printed' and c['crossing'] == 'first' and printed
    assert printed[0][0][1]['payee'] == 'مؤسسة النور'
    t.new()
    assert t.number.value() == 101 and t.payee.currentText() == ''
    w.register.reload()
    assert w.register.table.model.rowCount() == 1
    w.register.table.view.selectAll()
    w.register._cancel(w.register.table.selected_ids())
    assert ctx.db.cheques()[0]['status'] == 'cancelled'
    # the filter row filters
    w.register.table.filter_widgets[2].setText('النور')
    assert w.register.table.proxy.rowCount() == 1
    w.register.table.filter_widgets[2].setText('غير موجود')
    assert w.register.table.proxy.rowCount() == 0


def test_template_editor_and_pdf(ctx, tmp_path):
    from cheque_app.core.render import cheque_values
    from cheque_app.ui.printing import save_pdf
    from cheque_app.ui.template_editor import TemplateEditor
    bank = ctx.db.banks()[0]['id']
    ed = TemplateEditor(None, ctx, bank)
    ed.items['date'].setPos(50 * 5, 10 * 5)          # drag the date to 50 mm, 10 mm
    ed.dx.setValue(2)
    ed.shift_all()
    ed.save()
    t = ctx.db.template(bank)
    assert t['fields']['date']['x'] == 52 and t['fields']['date']['y'] == 10
    out = str(tmp_path / 'c.pdf')
    assert save_pdf(out, [(t, cheque_values(t, {'cheque_date': '2026-01-01', 'payee': 'x', 'amount': '5'}))])
    assert os.path.getsize(out) > 1000


def test_dialogs_open(ctx):
    from cheque_app.ui.issue import PickDialog
    from cheque_app.ui.lists import AccountDialog, PayeeDialog
    from cheque_app.ui.main_window import LicenseDialog, MainWindow
    MainWindow.showEvent = lambda self, e: None
    w = MainWindow(ctx)
    PickDialog(w, 't', [('a', 'text')], [(1, ['x'])])
    AccountDialog(w, ctx.db)
    PayeeDialog(w)
    LicenseDialog(w, ctx)
    w.settings.backup_now()
    assert os.listdir(os.path.join(ctx.data_dir, 'backups'))


def test_issue_form_finish(ctx):
    """One control height, numbers left to right, the amount right-aligned and formatted with thousands."""
    from PySide6.QtCore import Qt
    from cheque_app.ui.main_window import MainWindow
    from cheque_app.ui.theme import CONTROL_H
    MainWindow.showEvent = lambda self, e: None
    w = MainWindow(ctx)
    w.show()
    QApplication.processEvents()
    t = w.issue
    for wd in (t.account, t.number, t.date, t.amount, t.words, t.memo, t.b_print, t.b_save, t.b_new):
        assert wd.height() == CONTROL_H, wd.accessibleName()
    assert t.amount.layoutDirection() == Qt.LeftToRight and t.amount.alignment() & Qt.AlignRight
    assert t.amount.width() < 250 and t.date.width() < 200
    t.amount.setText('1250.75')
    t.amount.editingFinished.emit()
    assert t.amount.text() == '1,250.750'
    assert t.words.text() == 'فقط ألف ومئتان وخمسون دينارًا وسبعمئة وخمسون فلسًا لا غير'
    assert '1,250.750' not in t.preview_w.accessibleDescription() and 'مؤسسة' not in t.preview_w.accessibleDescription()
    t.payee.setEditText('مؤسسة النور')
    assert 'مؤسسة النور' in t.preview_w.accessibleDescription()
    w.close()


def test_editor_alignment_tools(ctx):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent
    from cheque_app.ui.template_editor import TemplateEditor
    ed = TemplateEditor(None, ctx, ctx.db.banks()[0]['id'])
    f = ed.tpl['fields']
    assert set(ed.states) >= {'date', 'payee', 'words1', 'amount_dinar'} and ed.states['payee'] == 'ok'
    for k in ('date', 'payee', 'words1'):
        ed.items[k].setSelected(True)
    ed.align('left')
    assert f['date']['x'] == f['payee']['x'] == f['words1']['x'] == 12.0
    ed.align('bottom')
    assert f['date']['y'] + f['date']['h'] == f['payee']['y'] + f['payee']['h'] == f['words1']['y'] + f['words1']['h']
    ed.fields.setCurrentRow(1)                                   # payee is the reference for «same width»
    for k in ('date', 'payee', 'words1'):
        ed.items[k].setSelected(True)
    ed.same('w')
    assert f['date']['w'] == f['words1']['w'] == f['payee']['w']
    ed.scene.clearSelection()
    ed.items['amount_fils'].setSelected(True)
    x0 = f['amount_fils']['x']
    ed.view.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Right, Qt.NoModifier))
    ed.view.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Left, Qt.ShiftModifier))
    assert f['amount_fils']['x'] == round(x0 + 0.5 - 5, 1)
    f['payee']['w'] = 10                                         # too narrow → flagged red
    ed._render()
    assert ed.states['payee'] == 'overflow' and ed.items['payee'].state == 'overflow'


def _interactive(w):
    from PySide6.QtWidgets import (QAbstractButton, QAbstractItemView, QAbstractSpinBox, QComboBox, QGraphicsView,
                                   QHeaderView, QLineEdit, QPlainTextEdit, QScrollBar, QTabBar)
    if not isinstance(w, (QAbstractButton, QLineEdit, QComboBox, QAbstractSpinBox, QAbstractItemView,
                          QGraphicsView, QPlainTextEdit)) or isinstance(w, QHeaderView):
        return False
    if w.objectName().startswith('qt_') or w.isHidden():
        return False
    p = w.parentWidget()
    while p is not None:          # parts of a composite control (a combo's line edit, a tab bar's arrows, a search icon)
        if isinstance(p, (QComboBox, QAbstractSpinBox, QAbstractItemView, QTabBar, QScrollBar, QLineEdit)):
            return False
        p = p.parentWidget()
    return True


def test_every_control_has_an_accessible_name(ctx):
    """Alt text: every interactive control in every window has an accessible name (both languages), icon-only
    buttons have a tooltip, and the cheque pictures describe what they show."""
    from PySide6.QtWidgets import QWidget
    from cheque_app.ui import common
    from cheque_app.ui.issue import PickDialog
    from cheque_app.ui.lists import AccountDialog, ImportPayeesDialog, PayeeDialog
    from cheque_app.ui.main_window import LicenseDialog, MainWindow
    from cheque_app.ui.printing import ChequePreview
    from cheque_app.ui.template_editor import TemplateEditor
    MainWindow.showEvent = lambda self, e: None
    for lang in ('ar', 'en'):
        common.set_lang(lang)
        try:
            w = MainWindow(ctx)
            windows = [w, TemplateEditor(None, ctx, ctx.db.banks()[0]['id']), LicenseDialog(w, ctx),
                       AccountDialog(w, ctx.db), PayeeDialog(w), ImportPayeesDialog(w),
                       PickDialog(w, 't', [('a', 'text'), ('b', 'select')], [(1, ['x', 'y'])])]
            missing = []
            for win in windows:
                for wd in [win] + win.findChildren(QWidget):
                    if not _interactive(wd):
                        continue
                    if not wd.accessibleName().strip():
                        missing.append(f'{type(win).__name__}: {type(wd).__name__} «{getattr(wd, "text", lambda: "")()}»')
                    if hasattr(wd, 'icon') and not wd.icon().isNull() and not wd.text().strip() and not wd.toolTip():
                        missing.append(f'{type(win).__name__}: icon-only button without tooltip')
                for pv in win.findChildren(ChequePreview):
                    assert pv.accessibleName() and pv.accessibleDescription()
            assert not missing, '\n'.join(missing)
            ed = windows[1]
            assert ed.view.accessibleDescription()
        finally:
            common.set_lang('ar')
