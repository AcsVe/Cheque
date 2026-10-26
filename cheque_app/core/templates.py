"""Cheque templates: where each value is printed on a bank's cheque, in millimetres from the cheque's top-left
corner. Every bank gets its own copy, calibrated once with a test print."""
import copy

# key: (Arabic label, English label)
FIELDS = {
    'date':         ('التاريخ', 'Date'),
    'payee':        ('اسم المستفيد', 'Payee'),
    'words1':       ('المبلغ كتابةً — السطر الأول', 'Amount in words — line 1'),
    'words2':       ('المبلغ كتابةً — السطر الثاني', 'Amount in words — line 2'),
    'amount_dinar': ('المبلغ — الدنانير', 'Amount — dinars'),
    'amount_fils':  ('المبلغ — الفلوس', 'Amount — fils'),
    'amount_full':  ('المبلغ كاملاً (رقم واحد)', 'Amount — single figure'),
    'crossing':     ('ختم التسطير', 'Crossing stamp'),
    'memo':         ('البيان', 'Memo'),
    'cheque_no':    ('رقم الشيك', 'Cheque number'),
}

_DEFAULT = {
    'width_mm': 175.0, 'height_mm': 80.0,
    'font': 'Arial',
    'words_lang': 'ar',             # amount in words: 'ar' | 'en'
    'sub_as_digits': False,         # «و750 فلسًا» instead of words
    'date_format': 'yyyy/MM/dd',
    'amount_wrap': '#{}#',          # around the dinars figure
    'thousands': False,             # 1,250 instead of 1250
    'hundred': 'مئة',               # spelling in words: 'مئة' (ثلاثمئة) | 'مائة' (ثلاثمائة)
    'digits': 'latin',              # figures on the cheque: 'latin' 1250 | 'arabic' ١٢٥٠
    'zero_fils': '---',             # what the fils box shows when there are no fils
    # how the printer takes the cheque: paper = 'cheque' (its own size, manual feed) | 'A4' | 'Letter';
    # rotate = 0 (fed lengthwise, «أفقي») | 90 / 270 (fed short edge first, «عامودي»)
    'feed': {'paper': 'cheque', 'rotate': 0, 'align': 'center', 'offset_x': 0.0, 'offset_y': 0.0},
    'layout': 2,                    # 2 = a field's box ends on the cheque's line (text sits on it); see upgrade_saved
    # every field: x, y = top-left of its box in mm; w, h = the box (its bottom edge is the printed line);
    # size = font size in points (shrinks automatically to fit the box, never below MIN_SIZE);
    # valign = 'bottom' (on the line) | 'center' (inside a framed box); align = 'right' | 'center' | 'left'
    'fields': {
        'date':         {'x': 18.0, 'y': 13.5, 'w': 36.0, 'h': 6.5, 'size': 11, 'align': 'center', 'valign': 'bottom',
                         'bold': True, 'visible': True, 'spacing': 0.0},
        'payee':        {'x': 12.0, 'y': 26.0, 'w': 150.0, 'h': 7.0, 'size': 11, 'align': 'center', 'valign': 'bottom',
                         'bold': True, 'visible': True},
        'words1':       {'x': 24.0, 'y': 34.0, 'w': 77.0, 'h': 7.0, 'size': 11, 'align': 'right', 'valign': 'bottom',
                         'bold': True, 'visible': True},
        'words2':       {'x': 6.0, 'y': 42.0, 'w': 115.0, 'h': 7.0, 'size': 11, 'align': 'right', 'valign': 'bottom',
                         'bold': True, 'visible': True},
        'amount_dinar': {'x': 125.0, 'y': 40.5, 'w': 28.0, 'h': 7.5, 'size': 11, 'align': 'center', 'valign': 'center',
                         'bold': True, 'visible': True},
        'amount_fils':  {'x': 154.0, 'y': 40.5, 'w': 17.0, 'h': 7.5, 'size': 11, 'align': 'center', 'valign': 'center',
                         'bold': True, 'visible': True},
        'amount_full':  {'x': 125.0, 'y': 40.5, 'w': 46.0, 'h': 7.5, 'size': 11, 'align': 'center', 'valign': 'center',
                         'bold': True, 'visible': False},
        'crossing':     {'x': 62.5, 'y': 2.0, 'w': 50.0, 'h': 9.0, 'size': 10, 'align': 'center', 'valign': 'center',
                         'bold': True, 'visible': True, 'angle': 0.0},
        'memo':         {'x': 6.0, 'y': 51.0, 'w': 115.0, 'h': 6.0, 'size': 10, 'align': 'right', 'valign': 'bottom',
                         'bold': False, 'visible': False},
        'cheque_no':    {'x': 140.0, 'y': 58.0, 'w': 31.0, 'h': 6.0, 'size': 10, 'align': 'center', 'valign': 'bottom',
                         'bold': False, 'visible': False},
    },
}

MIN_SIZE = 6.0          # a field's text never shrinks below this (points), nor below 60 % of its set size

# fields of version 1.0.0 (no 'layout' key): text was centred in a box whose height defaulted to 1.6 × the font
_V1_FIELDS = {
    'date': (17.0, 17.0, 40.0, 11), 'payee': (12.0, 30.0, 150.0, 12), 'words1': (26.0, 38.0, 78.0, 10),
    'words2': (8.0, 46.0, 114.0, 10), 'amount_dinar': (127.0, 44.0, 26.0, 12), 'amount_fils': (154.0, 44.0, 16.0, 12),
    'amount_full': (127.0, 44.0, 43.0, 12), 'crossing': (66.0, 8.0, 50.0, 10), 'memo': (8.0, 54.0, 110.0, 9),
    'cheque_no': (140.0, 70.0, 30.0, 9),
}


def upgrade_saved(saved):
    """A bank template saved by version 1.0.0 (no 'layout' key) is brought to the current layout:
    - never calibrated (every field still at the 1.0.0 default and no printer shift): its fields are dropped so
      the current default positions apply;
    - calibrated: every field keeps its position, its old box height and its centred text, so the print does
      not move on the cheque."""
    if not isinstance(saved, dict) or 'layout' in saved:
        return saved
    t = dict(saved)
    fields = {k: dict(v) for k, v in (t.get('fields') or {}).items()}
    feed = t.get('feed') or {}

    def same(k, f):
        d = _V1_FIELDS.get(k)
        return d is not None and all(abs(float(f.get(a) or 0) - b) < 0.01 for a, b in zip(('x', 'y', 'w', 'size'), d))
    untouched = all(same(k, f) for k, f in fields.items()) and not float(feed.get('offset_x') or 0) \
        and not float(feed.get('offset_y') or 0)
    if untouched:
        t['fields'] = {k: {a: f[a] for a in ('visible', 'bold', 'align', 'spacing', 'angle') if a in f}
                       for k, f in fields.items()}
    else:
        for k, f in fields.items():
            f.setdefault('valign', 'center')
            if 'h' not in f:
                f['h'] = round(float(f.get('size') or 10) * 0.3528 * 1.6, 2)
        t['fields'] = fields
    t['layout'] = 2
    return t


CROSSING_TEXT = {
    'none': '',
    'first': 'يصرف للمستفيد الأول',
    'account': 'يصرف في الحساب',
    'both': 'للمستفيد الأول — في الحساب',
}


def default_template():
    return copy.deepcopy(_DEFAULT)
