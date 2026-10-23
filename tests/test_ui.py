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
