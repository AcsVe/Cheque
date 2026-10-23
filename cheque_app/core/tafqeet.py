"""Amounts in words for cheques — formal Arabic (with the correct counted-noun forms) and English.

    words_ar(Decimal('1250.750'))  →  'فقط ألف ومئتان وخمسون دينارًا وسبعمئة وخمسون فلسًا لا غير'
    words_en(Decimal('1250.750'))  →  'One Thousand Two Hundred Fifty Jordanian Dinars and Seven Hundred Fifty Fils Only'

A currency is (singular, dual, plural 3-10, accusative 11-99, sub-unit…, sub-units per unit, English names).
"""
from decimal import Decimal, ROUND_HALF_UP

ONES = ['', 'واحد', 'اثنان', 'ثلاثة', 'أربعة', 'خمسة', 'ستة', 'سبعة', 'ثمانية', 'تسعة']
TEENS = ['عشرة', 'أحد عشر', 'اثنا عشر', 'ثلاثة عشر', 'أربعة عشر', 'خمسة عشر', 'ستة عشر', 'سبعة عشر',
         'ثمانية عشر', 'تسعة عشر']
TENS = ['', '', 'عشرون', 'ثلاثون', 'أربعون', 'خمسون', 'ستون', 'سبعون', 'ثمانون', 'تسعون']
HUNDREDS = ['', 'مئة', 'مئتان', 'ثلاثمئة', 'أربعمئة', 'خمسمئة', 'ستمئة', 'سبعمئة', 'ثمانمئة', 'تسعمئة']

# (singular, dual, plural 3-10, accusative 11-99)
THOUSAND = ('ألف', 'ألفان', 'آلاف', 'ألفًا')
MILLION = ('مليون', 'مليونان', 'ملايين', 'مليونًا')
BILLION = ('مليار', 'ملياران', 'مليارات', 'مليارًا')

CURRENCIES = {
    'JOD': {'unit': ('دينار', 'ديناران', 'دنانير', 'دينارًا'), 'sub': ('فلس', 'فلسان', 'فلوس', 'فلسًا'),
            'per': 1000, 'en': ('Jordanian Dinar', 'Jordanian Dinars', 'Fils', 'Fils'), 'symbol': 'JOD'},
    'USD': {'unit': ('دولار', 'دولاران', 'دولارات', 'دولارًا'), 'sub': ('سنت', 'سنتان', 'سنتات', 'سنتًا'),
            'per': 100, 'en': ('US Dollar', 'US Dollars', 'Cent', 'Cents'), 'symbol': 'USD'},
    'EUR': {'unit': ('يورو', 'يورو', 'يورو', 'يورو'), 'sub': ('سنت', 'سنتان', 'سنتات', 'سنتًا'),
            'per': 100, 'en': ('Euro', 'Euros', 'Cent', 'Cents'), 'symbol': 'EUR'},
}


def _below_1000(n):
    """0..999 → words ('' for 0)."""
    h, r = divmod(n, 100)
    parts = []
    if h:
        parts.append(HUNDREDS[h])
    if r:
        if r < 10:
            parts.append(ONES[r])
        elif r < 20:
            parts.append(TEENS[r - 10])
        else:
            t, o = divmod(r, 10)
            parts.append(f'{ONES[o]} و{TENS[t]}' if o else TENS[t])
    return ' و'.join(parts)


def _construct(words):
    """«مئتان» before a counted noun becomes «مئتا» (مئتا ألف، مئتا دينار)."""
    return words[:-1] if words.endswith('مئتان') else words


def _counted(c, forms, number_words):
    """c of something with the forms (singular, dual, plural, accusative), using number_words(c) for the count."""
    one, two, plural, acc = forms
    if c == 0:
        return ''
    if c == 1:
        return one
    if c == 2:
        return two
    r = c % 100
    if 3 <= r <= 10:
        return f'{number_words(c)} {plural}'
    if 11 <= r <= 99:
        return f'{number_words(c)} {acc}'
    if r == 0:
        return f'{_construct(number_words(c))} {one}'
    # r in (1, 2) after hundreds: «مئة وألف»، «مئتان وألفان»
    return f'{number_words(c - r)} و{one if r == 1 else two}'


def number_ar(n):
    """Whole number → Arabic words (no counted noun). 0 → 'صفر'."""
    n = int(n)
    if n == 0:
        return 'صفر'
    if n < 0:
        return 'سالب ' + number_ar(-n)
    groups = []
    for size, forms in ((10 ** 9, BILLION), (10 ** 6, MILLION), (1000, THOUSAND)):
        c, n = divmod(n, size)
        if c:
            groups.append(_counted(c, forms, number_ar))
    if n:
        groups.append(_below_1000(n))
    return ' و'.join(g for g in groups if g)


def _money_ar(c, forms):
    """A count of a currency unit: «دينار واحد»، «ديناران»، «ثلاثة دنانير»، «مئة وواحد دينار»…"""
    one, two, plural, acc = forms
    if c == 1:
        return f'{one} واحد' if one not in ('يورو',) else 'يورو واحد'
    if c == 2:
        return two
    r = c % 100
    words = number_ar(c)
    if c >= 1000 and c % 1000 == 0:
        # «ألفا دينار»، «أحد عشر ألف دينار»، «مليونا دينار»: the last big noun goes into the construct state
        for full, short in (('ألفًا', 'ألف'), ('ألفان', 'ألفا'), ('مليونًا', 'مليون'), ('مليونان', 'مليونا'),
                            ('مليارًا', 'مليار'), ('ملياران', 'مليارا')):
            if words.endswith(full):
                words = words[:-len(full)] + short
                break
        return f'{words} {one}'
    if 3 <= r <= 10:
        return f'{words} {plural}'
    if 11 <= r <= 99:
        return f'{words} {acc}'
    if r == 0:
        return f'{_construct(words)} {one}'
    return f'{words} {one}'


def split_amount(amount, per=1000):
    amount = Decimal(str(amount)).quantize(Decimal(1) / per if per else Decimal(1), rounding=ROUND_HALF_UP)
    whole = int(amount)
    sub = int(((amount - whole) * per).to_integral_value(rounding=ROUND_HALF_UP))
    return whole, sub


def words_ar(amount, currency='JOD', sub_as_digits=False, prefix='فقط', suffix='لا غير'):
    cur = CURRENCIES.get(currency, CURRENCIES['JOD'])
    whole, sub = split_amount(amount, cur['per'])
    parts = []
    if whole:
        parts.append(_money_ar(whole, cur['unit']))
    if sub:
        if sub_as_digits:
            one, _two, plural, acc = cur['sub']
            noun = acc if sub % 100 >= 11 else (plural if 3 <= sub % 100 <= 10 else one)
            parts.append(f'{sub} {noun}')
        else:
            parts.append(_money_ar(sub, cur['sub']))
    if not parts:
        parts.append(f'صفر {cur["unit"][0]}')
    text = ' و'.join(parts)
    return ' '.join(p for p in (prefix, text, suffix) if p)


# ── English ───────────────────────────────────────────────────────────────
_EN1 = ['', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten', 'Eleven', 'Twelve',
        'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen', 'Seventeen', 'Eighteen', 'Nineteen']
_EN10 = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety']


def _en_below_1000(n):
    h, r = divmod(n, 100)
    out = []
    if h:
        out.append(f'{_EN1[h]} Hundred')
    if r:
        out.append(_EN1[r] if r < 20 else (_EN10[r // 10] + (f'-{_EN1[r % 10]}' if r % 10 else '')))
    return ' '.join(out)


def number_en(n):
    n = int(n)
    if n == 0:
        return 'Zero'
    out = []
    for size, name in ((10 ** 9, 'Billion'), (10 ** 6, 'Million'), (1000, 'Thousand')):
        c, n = divmod(n, size)
        if c:
            out.append(f'{_en_below_1000(c)} {name}')
    if n:
        out.append(_en_below_1000(n))
    return ' '.join(out)


def words_en(amount, currency='JOD', sub_as_digits=False, prefix='', suffix='Only'):
    cur = CURRENCIES.get(currency, CURRENCIES['JOD'])
    whole, sub = split_amount(amount, cur['per'])
    one, many, sub1, subn = cur['en']
    parts = []
    if whole:
        parts.append(f'{number_en(whole)} {one if whole == 1 else many}')
    if sub:
        if sub_as_digits:
            parts.append(f'{sub}/{cur["per"]} {subn}')
        else:
            parts.append(f'{number_en(sub)} {sub1 if sub == 1 else subn}')
    if not parts:
        parts.append(f'Zero {many}')
    return ' '.join(p for p in (prefix, ' and '.join(parts), suffix) if p)


def amount_words(amount, lang='ar', **kw):
    return words_en(amount, **kw) if lang == 'en' else words_ar(amount, **kw)
