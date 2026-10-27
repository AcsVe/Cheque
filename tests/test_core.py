import base64
from datetime import date
from decimal import Decimal

import pytest

from cheque_app.core import license as lic
from cheque_app.core.db import Database
from cheque_app.core.tafqeet import words_ar, words_en, number_ar


@pytest.mark.parametrize('amount,text', [
    ('1', 'فقط دينار واحد لا غير'),
    ('2', 'فقط ديناران لا غير'),
    ('7', 'فقط سبعة دنانير لا غير'),
    ('15', 'فقط خمسة عشر دينارًا لا غير'),
    ('100', 'فقط مئة دينار لا غير'),
    ('200', 'فقط مئتا دينار لا غير'),
    ('2000', 'فقط ألفا دينار لا غير'),
    ('3000', 'فقط ثلاثة آلاف دينار لا غير'),
    ('11000', 'فقط أحد عشر ألف دينار لا غير'),
    ('1250.750', 'فقط ألف ومئتان وخمسون دينارًا وسبعمئة وخمسون فلسًا لا غير'),
    ('0.005', 'فقط خمسة فلوس لا غير'),
    ('1000000', 'فقط مليون دينار لا غير'),
])
def test_words_ar(amount, text):
    assert words_ar(amount) == text


def test_words_misc():
    assert words_ar('300', hundred='مائة') == 'فقط ثلاثمائة دينار لا غير'
    assert words_ar('200', hundred='مائة') == 'فقط مائتا دينار لا غير'
    assert number_ar(21) == 'واحد وعشرون'
    assert number_ar(3500) == 'ثلاثة آلاف وخمسمئة'
    assert words_ar('1250.750', sub_as_digits=True) == 'فقط ألف ومئتان وخمسون دينارًا و750 فلسًا لا غير'
    assert words_en('1250.75') == 'One Thousand Two Hundred Fifty Jordanian Dinars and Seven Hundred Fifty Fils Only'
    assert words_en('21.001', sub_as_digits=True) == 'Twenty-One Jordanian Dinars and 1/1000 Fils Only'


@pytest.fixture
def db(tmp_path):
    d = Database(str(tmp_path / 'c.db'))
    yield d
    d.close()


def _account(db, **kw):
    bank = db.banks()[0]['id']
    return db.save_account(dict({'bank_id': bank, 'name': 'الحساب الجاري', 'number': '0012', 'next_no': 559}, **kw))


def test_cheque_flow(db):
    acc = _account(db, last_no=561)
    assert db.next_cheque_no(acc) == 559
    cid = db.save_cheque({'account_id': acc, 'cheque_no': 559, 'cheque_date': '2026-06-25', 'payee': 'مؤسسة البريد',
                          'amount': '1,250.750', 'crossing': 'first'})
    assert db.cheque(cid)['amount'] == '1250.750' and db.next_cheque_no(acc) == 560
    assert [p['name'] for p in db.payees()] == ['مؤسسة البريد']           # payee remembered
    with pytest.raises(ValueError, match='duplicate'):
        db.save_cheque({'account_id': acc, 'cheque_no': 559, 'cheque_date': '2026-06-25', 'payee': 'x', 'amount': 5})
    with pytest.raises(ValueError, match='beyond_book'):
        db.save_cheque({'account_id': acc, 'cheque_no': 562, 'cheque_date': '2026-06-25', 'payee': 'x', 'amount': 5})
    with pytest.raises(ValueError, match='amount'):
        db.save_cheque({'account_id': acc, 'cheque_no': 560, 'cheque_date': '2026-06-25', 'payee': 'x', 'amount': '0'})
    db.mark_printed(cid)
    assert db.cheque(cid)['status'] == 'printed' and db.cheque(cid)['print_count'] == 1
    cid2 = db.save_cheque({'account_id': acc, 'cheque_no': 560, 'cheque_date': '2026-06-26', 'payee': 'ب', 'amount': '٣٥٫٥'})
    assert db.cheque(cid2)['amount'] == '35.5'
    done, kept = db.delete_cheques([cid, cid2])                         # printed cheques are kept
    assert done == 1 and kept == [559]
    assert db.set_status([cid], 'cancelled') == 1
    with pytest.raises(ValueError, match='cancelled'):
        db.save_cheque({'account_id': acc, 'cheque_no': 559, 'cheque_date': '2026-06-25', 'payee': 'x', 'amount': 5}, cid)


def test_guards_and_backup(db, tmp_path):
    acc = _account(db)
    db.save_cheque({'account_id': acc, 'cheque_no': 1, 'cheque_date': '2026-01-01', 'payee': 'أ', 'amount': 10})
    bank = db.account(acc)['bank_id']
    done, kept = db.delete_rows('banks', [bank], guard=lambda i: 'used' if db.bank_in_use(i) else None)
    assert done == 0 and kept == ['used']
    path = db.backup(str(tmp_path / 'bk'))
    db.save_cheque({'account_id': acc, 'cheque_no': 2, 'cheque_date': '2026-01-02', 'payee': 'ب', 'amount': 20})
    db.restore(path)
    assert [c['cheque_no'] for c in db.cheques()] == [1]


def test_template_merge_keeps_new_fields(db):
    import json
    bank = db.banks()[0]
    t = json.loads(bank['template'])
    del t['fields']['memo']
    t['fields']['date']['x'] = 99
    db.save_bank({'name': bank['name'], 'template': t}, bank['id'])
    merged = db.template(bank['id'])
    assert merged['fields']['date']['x'] == 99 and 'memo' in merged['fields']


def _keypair():
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.public_key().public_bytes(serialization.Encoding.PEM,
                                        serialization.PublicFormat.SubjectPublicKeyInfo).decode()

    def sign(fp, exp):
        sig = key.sign(f'{fp}|{exp}'.encode(), ec.ECDSA(hashes.SHA256()))
        return f'{exp}:' + base64.urlsafe_b64encode(sig).decode().rstrip('=')
    return pem, sign


def test_license(tmp_path, monkeypatch):
    pem, sign = _keypair()
    monkeypatch.setattr(lic, 'LICENSE_PUBLIC_KEY_PEM', pem)
    d = str(tmp_path)
    fp = 'ABCDEF0123456789'
    st = lic.current_state(d, today=date(2026, 1, 1), fingerprint=fp)
    assert st.mode == 'trial' and st.can_print and st.days_left == lic.TRIAL_DAYS
    assert lic.current_state(d, today=date(2026, 3, 1), fingerprint=fp).mode == 'trial_over'
    lic.save_key(d, sign(fp, '20261231'))
    st = lic.current_state(d, today=date(2026, 3, 1), fingerprint=fp)
    assert st.mode == 'licensed' and st.expires == '2026-12-31'
    assert lic.current_state(d, today=date(2027, 1, 1), fingerprint=fp).mode == 'expired'
    lic.save_key(d, sign('OTHERMACHINE0000', 'PERMANENT'))                  # key for another computer
    assert not lic.current_state(d, today=date(2026, 3, 1), fingerprint=fp).can_print
    lic.save_key(d, sign(fp, 'PERMANENT'))
    assert lic.current_state(d, today=date(2030, 1, 1), fingerprint=fp).expires == 'PERMANENT'


def test_real_public_key_accepts_existing_generator_keys():
    """The bell key issued by the same generator verifies → the generator works for this program too."""
    key = '20271021:MEQCIEyKqeeDvRy2D-1Kq_VgSC3FFCmDtzm_0nLTn1leL5rPAiAd3poKPHFSqodIBs5oxjo3HcdXNtStgPUoQHLOkrFdHA'
    assert lic.check_license(key, '4C7758C688A6DE55', date(2026, 10, 1)) == (True, False, '2027-10-21')


def test_render_pdf(tmp_path):
    from PySide6.QtCore import QMarginsF, QSizeF
    from PySide6.QtGui import QGuiApplication, QPageSize, QPainter, QPdfWriter
    from cheque_app.core.render import cheque_values, paint_page, page_size_mm
    from cheque_app.core.templates import default_template
    pass
    t = default_template()
    for rot in (0, 90):
        t['feed']['rotate'] = rot
        w, h = page_size_mm(t)
        pdf = QPdfWriter(str(tmp_path / f'c{rot}.pdf'))
        pdf.setResolution(300)
        pdf.setPageSize(QPageSize(QSizeF(w, h), QPageSize.Millimeter))
        pdf.setPageMargins(QMarginsF(0, 0, 0, 0))
        p = QPainter(pdf)
        v = cheque_values(t, {'cheque_date': '2026-06-25', 'payee': 'مؤسسة', 'amount': '1250.750', 'crossing': 'both'})
        paint_page(p, w, h, 300 / 25.4, t, v)
        p.end()
        assert (tmp_path / f'c{rot}.pdf').stat().st_size > 1000
    assert v['amount_dinar'] == '#1250#' and v['amount_fils'] == '750' and v['date'] == '2026/06/25'
    t.update({'digits': 'arabic', 'hundred': 'مائة'})
    v = cheque_values(t, {'cheque_date': '2026-03-19', 'payee': 'x', 'amount': '500000', 'crossing': 'first'})
    assert v['amount_dinar'] == '#٥٠٠٠٠٠#' and v['amount_fils'] == '---' and v['date'] == '٢٠٢٦/٠٣/١٩'
    assert v['words'] == 'فقط خمسمائة ألف دينار لا غير'


def _layout(t, v, dpi=300):
    from PySide6.QtGui import QImage
    from cheque_app.core.render import layout_cheque
    img = QImage(8, 8, QImage.Format_ARGB32)
    img.setDotsPerMeterX(round(dpi / 0.0254))
    img.setDotsPerMeterY(round(dpi / 0.0254))
    k = dpi / 25.4
    return layout_cheque(t, v, (0, 0), k, k * 25.4 / img.logicalDpiY(), img), img


def test_fields_fit_their_boxes():
    """Every text is fitted to its field: words split at a word boundary by the measured width, long text shrinks
    (never below the minimum), both lines of the words share one font, and nothing is drawn wider than its box."""
    from PySide6.QtGui import QFontMetricsF
    from cheque_app.core.render import cheque_values, min_size
    from cheque_app.core.templates import default_template
    t = default_template()
    v = cheque_values(t, {'cheque_date': '2026-10-26', 'payee': 'مؤسسة النور للتجارة', 'amount': '1250.750',
                          'crossing': 'first'})
    placed, dev = _layout(t, v)
    states = {k: (pl.state, round(pl.font.pointSizeF(), 2)) for k, pl in placed.items() if pl.state != 'ok'}
    assert not states, states
    assert (placed['words1'].text + ' ' + placed['words2'].text).split() == v['words'].split()
    assert placed['words1'].font.pointSizeF() == placed['words2'].font.pointSizeF()
    for pl in placed.values():
        fm = QFontMetricsF(pl.font, dev)
        if pl.key != 'crossing':
            assert fm.horizontalAdvance(pl.text) <= pl.rect.width() + 0.5, pl.key
            assert fm.ascent() + fm.descent() <= pl.rect.height() + 0.5, pl.key
    # the same size by default for the date, payee, words and figures
    assert len({t['fields'][k]['size'] for k in ('date', 'payee', 'words1', 'words2', 'amount_dinar', 'amount_fils')}) == 1

    long = cheque_values(t, {'cheque_date': '2026-10-26', 'amount': '987654321.999', 'crossing': 'both',
                             'payee': 'شركة الأفق الجديد للتجارة العامة والمقاولات والاستثمارات العقارية والصناعية المحدودة'})
    placed, dev = _layout(t, long)
    assert placed['words1'].state == 'shrunk' and placed['payee'].state in ('shrunk', 'ok')
    assert (placed['words1'].text + ' ' + placed['words2'].text).split() == long['words'].split()
    for key in ('words1', 'words2', 'payee'):
        fm = QFontMetricsF(placed[key].font, dev)
        assert fm.horizontalAdvance(placed[key].text) <= placed[key].rect.width() + 0.5
        assert placed[key].size >= min_size(t['fields'][key])
    t['fields']['payee']['w'] = 10                                          # far too small: reported, not hidden
    placed, _ = _layout(t, long)
    assert placed['payee'].state == 'overflow'


def test_old_templates_upgrade():
    """1.0.0 templates: an uncalibrated one takes the new layout; a calibrated one keeps its positions and its
    centred text, so the print does not move on the cheque."""
    from cheque_app.core.templates import default_template, upgrade_saved, _V1_FIELDS
    v1 = {'width_mm': 175.0, 'height_mm': 80.0, 'feed': {'offset_x': 0.0, 'offset_y': 0.0},
          'fields': {k: {'x': x, 'y': y, 'w': w, 'size': s, 'visible': k not in ('amount_full', 'memo', 'cheque_no')}
                     for k, (x, y, w, s) in _V1_FIELDS.items()}}
    up = upgrade_saved(v1)
    assert up['layout'] == 2 and all('x' not in f for f in up['fields'].values())
    v1['fields']['date']['x'] = 20.5
    up = upgrade_saved(v1)
    d = up['fields']['date']
    assert d['x'] == 20.5 and d['y'] == 17.0 and d['valign'] == 'center' and abs(d['h'] - 11 * 0.3528 * 1.6) < 0.01
    assert upgrade_saved(default_template()) == default_template()
