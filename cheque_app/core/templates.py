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
    'date_format': 'dd/MM/yyyy',
    'amount_wrap': '#{}#',          # around the dinars figure
    'thousands': False,             # 1,250 instead of 1250
    # how the printer takes the cheque: paper = 'cheque' (its own size, manual feed) | 'A4' | 'Letter';
    # rotate = 0 (fed lengthwise, «أفقي») | 90 / 270 (fed short edge first, «عامودي»)
    'feed': {'paper': 'cheque', 'rotate': 0, 'align': 'center', 'offset_x': 0.0, 'offset_y': 0.0},
    'fields': {
        'date':         {'x': 20.0, 'y': 22.0, 'w': 36.0, 'size': 11, 'align': 'center', 'bold': False, 'visible': True,
                         'spacing': 0.0},
        'payee':        {'x': 22.0, 'y': 34.0, 'w': 128.0, 'size': 12, 'align': 'center', 'bold': True, 'visible': True},
        'words1':       {'x': 30.0, 'y': 44.0, 'w': 100.0, 'size': 10, 'align': 'right', 'bold': False, 'visible': True},
        'words2':       {'x': 10.0, 'y': 52.0, 'w': 112.0, 'size': 10, 'align': 'right', 'bold': False, 'visible': True},
        'amount_dinar': {'x': 128.0, 'y': 48.0, 'w': 26.0, 'size': 12, 'align': 'center', 'bold': True, 'visible': True},
        'amount_fils':  {'x': 156.0, 'y': 48.0, 'w': 13.0, 'size': 12, 'align': 'center', 'bold': True, 'visible': True},
        'amount_full':  {'x': 128.0, 'y': 48.0, 'w': 41.0, 'size': 12, 'align': 'center', 'bold': True, 'visible': False},
        'crossing':     {'x': 66.0, 'y': 3.0, 'w': 50.0, 'h': 11.0, 'size': 10, 'align': 'center', 'bold': True,
                         'visible': True, 'angle': 0.0},
        'memo':         {'x': 10.0, 'y': 66.0, 'w': 90.0, 'size': 8, 'align': 'right', 'bold': False, 'visible': False},
        'cheque_no':    {'x': 140.0, 'y': 70.0, 'w': 30.0, 'size': 9, 'align': 'center', 'bold': False, 'visible': False},
    },
}

CROSSING_TEXT = {
    'none': '',
    'first': 'يصرف للمستفيد الأول',
    'account': 'يصرف في الحساب',
    'both': 'للمستفيد الأول — في الحساب',
}


def default_template():
    return copy.deepcopy(_DEFAULT)
