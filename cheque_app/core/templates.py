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
    'fields': {
        'date':         {'x': 17.0, 'y': 17.0, 'w': 40.0, 'size': 11, 'align': 'center', 'bold': True, 'visible': True,
                         'spacing': 0.0},
        'payee':        {'x': 12.0, 'y': 30.0, 'w': 150.0, 'size': 12, 'align': 'center', 'bold': True, 'visible': True},
        'words1':       {'x': 26.0, 'y': 38.0, 'w': 78.0, 'size': 10, 'align': 'right', 'bold': True, 'visible': True},
        'words2':       {'x': 8.0, 'y': 46.0, 'w': 114.0, 'size': 10, 'align': 'right', 'bold': True, 'visible': True},
        'amount_dinar': {'x': 127.0, 'y': 44.0, 'w': 26.0, 'size': 12, 'align': 'center', 'bold': True, 'visible': True},
        'amount_fils':  {'x': 154.0, 'y': 44.0, 'w': 16.0, 'size': 12, 'align': 'center', 'bold': True, 'visible': True},
        'amount_full':  {'x': 127.0, 'y': 44.0, 'w': 43.0, 'size': 12, 'align': 'center', 'bold': True, 'visible': False},
        'crossing':     {'x': 66.0, 'y': 8.0, 'w': 50.0, 'h': 9.0, 'size': 10, 'align': 'center', 'bold': True,
                         'visible': True, 'angle': 0.0},
        'memo':         {'x': 8.0, 'y': 54.0, 'w': 110.0, 'size': 9, 'align': 'right', 'bold': False, 'visible': False},
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
