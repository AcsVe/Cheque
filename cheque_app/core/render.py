"""Drawing a cheque with QPainter in millimetres — the same code for the printer, the PDF, the on-screen preview
and the calibration sheet, so what is previewed is what is printed."""
from decimal import Decimal

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen, QTextOption

from .tafqeet import amount_words, split_amount, CURRENCIES
from .templates import CROSSING_TEXT, FIELDS


def cheque_values(tpl, data, crossing_texts=None):
    """{field key: text} for one cheque. data: cheque_date (QDate|str yyyy-mm-dd), payee, amount, crossing,
    memo, cheque_no, currency, words (optional override)."""
    from PySide6.QtCore import QDate
    cur = data.get('currency') or 'JOD'
    per = CURRENCIES.get(cur, CURRENCIES['JOD'])['per']
    amount = Decimal(str(data.get('amount') or 0))
    whole, sub = split_amount(amount, per)
    dinars = f'{whole:,}' if tpl.get('thousands') else str(whole)
    wrap = tpl.get('amount_wrap') or '{}'
    d = data.get('cheque_date')
    qd = d if isinstance(d, QDate) else QDate.fromString(str(d or ''), 'yyyy-MM-dd')
    words = data.get('words') or (amount_words(amount, tpl.get('words_lang', 'ar'), currency=cur,
                                               sub_as_digits=tpl.get('sub_as_digits', False),
                                               hundred=tpl.get('hundred', 'مئة')) if amount else '')
    texts = dict(CROSSING_TEXT)
    texts.update(crossing_texts or {})
    digits = 3 if per == 1000 else 2
    ar = tpl.get('digits') == 'arabic'

    def fig(text):
        return text.translate(str.maketrans('0123456789', '٠١٢٣٤٥٦٧٨٩')) if ar else text
    fils = (f'{sub:0{digits}d}' if sub else (tpl.get('zero_fils') if tpl.get('zero_fils') is not None else '---')) if amount else ''
    return {
        'date': fig(qd.toString(tpl.get('date_format') or 'yyyy/MM/dd')) if qd.isValid() else '',
        'payee': data.get('payee') or '',
        'words': words,
        'amount_dinar': fig(wrap.replace('{}', dinars)) if amount else '',
        'amount_fils': fig(fils),
        'amount_full': fig(wrap.replace('{}', f'{dinars}.{sub:0{digits}d}')) if amount else '',
        'crossing': texts.get(data.get('crossing') or 'none', ''),
        'memo': data.get('memo') or '',
        'cheque_no': fig(str(data.get('cheque_no') or '')),
    }


def _font(tpl, f, scale_pt):
    font = QFont(tpl.get('font') or 'Arial')
    font.setPointSizeF(max(4.0, float(f.get('size') or 10)) * scale_pt)
    font.setBold(bool(f.get('bold')))
    return font


def _align(f):
    return {'left': Qt.AlignLeft, 'center': Qt.AlignHCenter, 'right': Qt.AlignRight}.get(f.get('align'), Qt.AlignHCenter)


def split_words(text, font, width_px, device=None):
    """Break the amount in words into (line 1, line 2) at a word boundary so line 1 fits ``width_px``."""
    fm = QFontMetricsF(font, device) if device is not None else QFontMetricsF(font)
    if fm.horizontalAdvance(text) <= width_px:
        return text, ''
    words, line = text.split(' '), ''
    for i, w in enumerate(words):
        trial = (line + ' ' + w).strip()
        if fm.horizontalAdvance(trial) > width_px and line:
            return line, ' '.join(words[i:])
        line = trial
    return line, ''


def draw_cheque(p, tpl, values, origin_mm=(0.0, 0.0), px_per_mm=1.0, frame=False, background=None, ink=None,
                highlight=None, simulate=False, labels=None):
    """Paint on QPainter ``p``. ``px_per_mm`` converts mm to the device; fonts are scaled so a 10 pt field is
    10 pt on paper whatever the device."""
    ox, oy = origin_mm
    k = px_per_mm
    w_mm, h_mm = float(tpl['width_mm']), float(tpl['height_mm'])
    rect = QRectF(ox * k, oy * k, w_mm * k, h_mm * k)
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    if background is not None and not background.isNull():
        p.drawImage(rect, background)
    elif simulate:
        draw_simulation(p, tpl, origin_mm, px_per_mm, labels)
    if frame:
        p.setPen(QPen(QColor('#9aa4b2'), max(1.0, 0.2 * k), Qt.DashLine))
        p.drawRect(rect)
    # fonts are in points of the paper: on a device with D dots per inch drawn at k px per mm, scale by k·25.4/D
    dpi = p.device().logicalDpiY() if p.device() else 96
    dpi_ratio = k * 25.4 / dpi if dpi else 1.0
    color = QColor(ink or '#000000')
    fields = tpl['fields']

    def box(f, h_mm_default=7.0):
        return QRectF((ox + float(f['x'])) * k, (oy + float(f['y'])) * k, float(f.get('w') or 30) * k,
                      float(f.get('h') or h_mm_default) * k)

    def text_in(key, text):
        f = fields.get(key) or {}
        if not f.get('visible', True) or not text:
            return
        font = _font(tpl, f, dpi_ratio)
        p.setFont(font)
        p.setPen(color)
        r = box(f, (float(f.get('size') or 10) * 0.3528 * 1.6))
        spacing = float(f.get('spacing') or 0)
        if spacing > 0:            # boxed digits (e.g. a date in separate squares)
            x = r.left()
            for ch in text:
                p.drawText(QRectF(x, r.top(), spacing * k, r.height()), Qt.AlignHCenter | Qt.AlignVCenter, ch)
                x += spacing * k
            return
        opt = QTextOption(_align(f) | Qt.AlignVCenter)
        opt.setWrapMode(QTextOption.NoWrap)
        p.drawText(r, text, opt)

    # amount in words over two lines
    w1, w2 = fields.get('words1', {}), fields.get('words2', {})
    words = values.get('words', '')
    if words and w1.get('visible', True):
        font = _font(tpl, w1, dpi_ratio)
        first, rest = split_words(words, font, float(w1.get('w') or 100) * k, p.device())
        if not w2.get('visible', True) and rest:
            first, rest = words, ''
        text_in('words1', first)
        text_in('words2', rest)
    for key in ('date', 'payee', 'amount_dinar', 'amount_fils', 'amount_full', 'memo', 'cheque_no'):
        text_in(key, values.get(key, ''))

    # crossing stamp: two parallel lines with the text between them, optionally rotated
    f = fields.get('crossing') or {}
    if f.get('visible', True) and values.get('crossing'):
        r = box(f, 11.0)
        p.save()
        p.translate(r.center())
        p.rotate(float(f.get('angle') or 0))
        local = QRectF(-r.width() / 2, -r.height() / 2, r.width(), r.height())
        p.setPen(QPen(color, max(1.0, 0.35 * k)))
        p.drawLine(local.topLeft(), local.topRight())
        p.drawLine(local.bottomLeft(), local.bottomRight())
        p.setFont(_font(tpl, f, dpi_ratio))
        opt = QTextOption(Qt.AlignCenter)
        p.drawText(local, values['crossing'], opt)
        p.restore()

    if highlight:
        p.setPen(QPen(QColor('#1d5fbf'), max(1.0, 0.3 * k), Qt.DotLine))
        for key in highlight:
            ff = fields.get(key)
            if ff:
                p.drawRect(box(ff, float(ff.get('h') or 7)))
    p.restore()
    return rect


def draw_calibration(p, tpl, origin_mm, px_per_mm, sample_values):
    """Calibration sheet: the cheque outline, a 10 mm grid, every field's box with its name, and sample text.
    Print it on plain paper, lay a real cheque on it against the light, and adjust the positions."""
    k = px_per_mm
    ox, oy = origin_mm
    w_mm, h_mm = float(tpl['width_mm']), float(tpl['height_mm'])
    p.save()
    p.setPen(QPen(QColor('#d5dae2'), max(1.0, 0.1 * k)))
    x = 0
    while x <= w_mm:
        p.drawLine(QPointF((ox + x) * k, oy * k), QPointF((ox + x) * k, (oy + h_mm) * k))
        x += 10
    y = 0
    while y <= h_mm:
        p.drawLine(QPointF(ox * k, (oy + y) * k), QPointF((ox + w_mm) * k, (oy + y) * k))
        y += 10
    small = QFont('Arial')
    small.setPointSizeF(6 * k * 25.4 / (p.device().logicalDpiY() or 96))
    p.setFont(small)
    p.setPen(QColor('#7a8594'))
    # rulers inside the outline, so they also print on a cheque-size sheet
    for x in range(10, int(w_mm), 10):
        p.drawText(QPointF((ox + x) * k + 0.5 * k, (oy + 2.5) * k), str(x))
    for y in range(10, int(h_mm), 10):
        p.drawText(QPointF((ox + 0.8) * k, (oy + y) * k - 0.5 * k), str(y))
    p.setPen(QPen(QColor('#000000'), max(1.0, 0.3 * k)))
    p.drawRect(QRectF(ox * k, oy * k, w_mm * k, h_mm * k))
    for key, f in tpl['fields'].items():
        if not f.get('visible', True):
            continue
        r = QRectF((ox + float(f['x'])) * k, (oy + float(f['y'])) * k, float(f.get('w') or 30) * k,
                   float(f.get('h') or 7) * k)
        p.setPen(QPen(QColor('#1d5fbf'), max(1.0, 0.2 * k), Qt.DashLine))
        p.drawRect(r)
        p.setPen(QColor('#1d5fbf'))
        p.drawText(QPointF(r.left(), r.top() - 0.6 * k), FIELDS.get(key, (key,))[0])
    p.restore()
    draw_cheque(p, tpl, sample_values, origin_mm, px_per_mm)


def place_on_page(page_w_mm, page_h_mm, tpl):
    """Where the cheque sits on the sheet the printer feeds: (x_mm, y_mm, rotation 0|90|270).
    feed.align centres it (or puts it left/right) across the feed width; offsets fine-tune the position."""
    feed = tpl.get('feed') or {}
    rot = int(feed.get('rotate') or 0) % 360
    cw, ch = float(tpl['width_mm']), float(tpl['height_mm'])
    if rot in (90, 270):
        cw, ch = ch, cw
    align = feed.get('align') or 'center'
    x = {'left': 0.0, 'right': page_w_mm - cw}.get(align, (page_w_mm - cw) / 2)
    y = 0.0
    return x + float(feed.get('offset_x') or 0), y + float(feed.get('offset_y') or 0), rot


def paint_page(p, page_w_mm, page_h_mm, px_per_mm, tpl, values, calibration=False):
    """Draw one cheque (or the calibration sheet) on a printer/PDF page, honouring the feed settings."""
    x, y, rot = place_on_page(page_w_mm, page_h_mm, tpl)
    k = px_per_mm
    p.save()
    if rot:
        cw, ch = float(tpl['width_mm']), float(tpl['height_mm'])
        if rot == 90:
            p.translate((x + ch) * k, y * k)
        else:  # 270
            p.translate(x * k, (y + cw) * k)
        p.rotate(rot)
        x = y = 0.0
    if calibration:
        draw_calibration(p, tpl, (x, y), k, values)
    else:
        draw_cheque(p, tpl, values, (x, y), k)
    p.restore()


def page_size_mm(tpl):
    """The paper size to give the printer: the cheque itself (manual feed) or a standard sheet."""
    paper = (tpl.get('feed') or {}).get('paper') or 'cheque'
    if paper == 'A4':
        return 210.0, 297.0
    if paper == 'Letter':
        return 215.9, 279.4
    cw, ch = float(tpl['width_mm']), float(tpl['height_mm'])
    rot = int((tpl.get('feed') or {}).get('rotate') or 0) % 360
    return (ch, cw) if rot in (90, 270) else (cw, ch)


def draw_simulation(p, tpl, origin_mm, px_per_mm, labels=None):
    """A drawn face of a Jordanian bank cheque, for the ON-SCREEN preview only — never printed, the real cheque
    already carries it. Its labels follow the calibrated fields, so the preview shows where each value lands.
    labels: {'bank', 'holder', 'account'} from the chosen account."""
    from PySide6.QtGui import QLinearGradient
    labels = labels or {}
    ox, oy = origin_mm
    k = px_per_mm
    w_mm, h_mm = float(tpl['width_mm']), float(tpl['height_mm'])
    f = tpl['fields']
    dpi = p.device().logicalDpiY() if p.device() else 96
    scale = k * 25.4 / dpi

    def g(key, attr, default):
        return float((f.get(key) or {}).get(attr, default) or default)

    def R(x, y, w, h):
        return QRectF((ox + x) * k, (oy + y) * k, w * k, h * k)

    def font(size, bold=True):
        fo = QFont('Arial')
        fo.setPointSizeF(size * scale)
        fo.setBold(bold)
        return fo

    ink = QColor('#3b3b4f')

    def lab(text, x, y, w=30, align=Qt.AlignLeft, size=7.5, bold=True, color=None):
        p.setFont(font(size, bold))
        p.setPen(color or ink)
        p.drawText(R(x, y, w, 5), int(align | Qt.AlignVCenter), text)

    def line(x, y, w, dotted=False):
        p.setPen(QPen(QColor('#8c93a3'), max(1.0, 0.25 * k), Qt.DotLine if dotted else Qt.SolidLine))
        p.drawLine(R(x, y, w, 0).topLeft(), R(x, y, w, 0).topRight())

    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    full = R(0, 0, w_mm, h_mm)
    grad = QLinearGradient(full.topLeft(), full.bottomRight())
    grad.setColorAt(0, QColor('#fbf6e3'))
    grad.setColorAt(0.55, QColor('#f6f3e6'))
    grad.setColorAt(1, QColor('#efeedf'))
    p.fillRect(full, grad)
    # watermark seal in the middle
    p.setPen(QPen(QColor(150, 140, 100, 40), max(1.0, 0.6 * k)))
    c = R(w_mm / 2 - 14, h_mm / 2 - 14, 28, 28)
    p.drawEllipse(c)
    p.drawEllipse(c.adjusted(3 * k, 3 * k, -3 * k, -3 * k))
    # header: bank (right), second logo (left), crossing stamp box (centre)
    p.setPen(QPen(QColor('#c9c2a2'), max(1.0, 0.3 * k)))
    p.setBrush(QColor('#fffdf6'))
    p.drawRoundedRect(R(w_mm - 50, 1.5, 47, 9.5), 1.5 * k, 1.5 * k)
    p.drawRoundedRect(R(3, 1.5, 47, 9.5), 1.5 * k, 1.5 * k)
    p.setBrush(Qt.NoBrush)
    lab(labels.get('bank') or 'البنك', w_mm - 49, 3.7, 45, Qt.AlignHCenter, 8.5, color=QColor('#1f4e3d'))
    cr = f.get('crossing') or {}
    p.fillRect(R(g('crossing', 'x', 66), g('crossing', 'y', 8), g('crossing', 'w', 50), g('crossing', 'h', 9)),
               QColor(200, 200, 205, 120))
    lab('ختم التسطير', g('crossing', 'x', 66), g('crossing', 'y', 8) + 2, g('crossing', 'w', 50), Qt.AlignHCenter,
        6.5, False, QColor('#9a9aa5'))
    # date
    dy, dx, dw = g('date', 'y', 17), g('date', 'x', 17), g('date', 'w', 40)
    lab('Date', 3, dy + 1, 14)
    lab('التاريخ', dx + dw + 1, dy + 1, 14)
    line(dx, dy + 6.5, dw, dotted=True)
    lab('الفرع', w_mm - 33, dy - 3, 30, Qt.AlignRight, 7.5)
    # pay to
    py = g('payee', 'y', 30)
    lab('Pay Against This Cheque', 3, py - 6, 50)
    lab('ادفعوا بموجب هذا الشيك', w_mm - 53, py - 4.5, 50, Qt.AlignRight)
    lab('To', 3, py + 1, 10)
    lab('لأمر', w_mm - 12, py + 1, 9, Qt.AlignRight)
    line(10, py + 6.5, w_mm - 22, dotted=True)
    # the sum of
    wy, wx, ww = g('words1', 'y', 38), g('words1', 'x', 26), g('words1', 'w', 90)
    lab('The Sum Of', 3, wy + 1, 22)
    lab('مبلغ وقدره', wx + ww + 1, wy + 1, 20)
    line(wx, wy + 6.5, ww, dotted=True)
    line(g('words2', 'x', 8), g('words2', 'y', 46) + 6.5, g('words2', 'w', 110), dotted=True)
    # amount box: fils on the right, dinars to its left, as printed by Jordanian banks
    ad, af = f.get('amount_dinar', {}), f.get('amount_fils', {})
    if ad.get('visible', True) or af.get('visible', True):
        x0 = g('amount_dinar', 'x', 124) - 1
        xf = g('amount_fils', 'x', 154) - 0.5
        x1 = g('amount_fils', 'x', 154) + g('amount_fils', 'w', 16) + 1
        y0 = g('amount_dinar', 'y', 41) - 5
        p.setPen(QPen(QColor('#55596b'), max(1.0, 0.35 * k)))
        p.drawRect(R(x0, y0, x1 - x0, 13))
        p.drawLine(R(x0, y0 + 4.5, x1 - x0, 0).topLeft(), R(x0, y0 + 4.5, x1 - x0, 0).topRight())
        p.drawLine(R(xf, y0, 0, 13).topLeft(), R(xf, y0, 0, 13).bottomLeft())
        lab('J.D.     دينار', x0, y0 - 0.3, xf - x0, Qt.AlignHCenter, 6.5)
        lab('Fils  فلس', xf, y0 - 0.3, x1 - xf, Qt.AlignHCenter, 6.5)
        holder = labels.get('holder')
        lab(('السادة ' + holder) if holder else 'اسم صاحب الحساب', x0 - 10, y0 + 15, x1 - x0 + 10, Qt.AlignRight, 8)
    # signature, footer, MICR line
    sy = h_mm - 17
    lab('التوقيع', 3, sy - 4, 20)
    lab('Sign', 3, sy, 20)
    line(18, sy + 4, 50)
    line(3, h_mm - 9.5, w_mm - 6)
    lab('Please do not write under this line — الرجاء عدم الكتابة تحت هذا الخط', 0, h_mm - 9.3, w_mm,
        Qt.AlignHCenter, 5, False, QColor('#7a8090'))
    mono = QFont('Courier New')
    mono.setPointSizeF(10 * scale)
    mono.setBold(True)
    p.setFont(mono)
    p.setPen(QColor('#22252e'))
    acct = ''.join(ch for ch in (labels.get('account') or '') if ch.isdigit()) or '0000000000'
    opt = QTextOption(Qt.AlignLeft | Qt.AlignVCenter)
    opt.setTextDirection(Qt.LeftToRight)
    p.drawText(R(8, h_mm - 6.5, w_mm - 16, 5), f'⑈000000⑈  ⑆00⑉000⑆  {acct}⑈', opt)
    p.restore()
