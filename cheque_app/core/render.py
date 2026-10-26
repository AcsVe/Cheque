"""Drawing a cheque with QPainter in millimetres — the same code for the printer, the PDF, the on-screen preview
and the calibration sheet, so what is previewed is what is printed."""
from decimal import Decimal

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPen, QTextLayout, QTextOption

from .tafqeet import amount_words, split_amount, CURRENCIES
from .templates import CROSSING_TEXT, FIELDS, MIN_SIZE


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


NUMERIC = ('date', 'amount_dinar', 'amount_fils', 'amount_full', 'cheque_no')   # drawn left-to-right


def _tabular(font):
    """Ask for tabular (equal-width) digits where Qt lets us; Arial, Segoe UI and Tahoma use them by default."""
    try:
        tag = QFont.Tag.fromString('tnum')       # Qt ≥ 6.7 in builds that expose it
        font.setFeature(tag, 1)
    except Exception:  # noqa: BLE001
        pass
    return font


def _font(tpl, f, scale_pt, size=None, stretch=100, numeric=False):
    font = QFont(tpl.get('font') or 'Arial')
    font.setPointSizeF(max(1.0, float(size if size is not None else (f.get('size') or 10))) * scale_pt)
    font.setBold(bool(f.get('bold')))
    font.setHintingPreference(QFont.PreferNoHinting)      # metrics scale exactly from screen to printer
    font.setKerning(True)
    if stretch != 100:
        font.setStretch(int(stretch))
    return _tabular(font) if numeric else font


def _align(f):
    return {'left': Qt.AlignLeft, 'center': Qt.AlignHCenter, 'right': Qt.AlignRight}.get(f.get('align'), Qt.AlignHCenter)


def min_size(f):
    size = float(f.get('size') or 10)
    return min(size, max(MIN_SIZE, size * 0.6))


def _sizes(f):
    """Font sizes to try, largest first: the set size, then down in 0.25 pt steps to the minimum."""
    size, low = float(f.get('size') or 10), min_size(f)
    out = [size]
    while out[-1] - 0.25 >= low - 1e-9:
        out.append(round(out[-1] - 0.25, 2))
    return out


def split_words(text, font, width_px, device=None):
    """Break the amount in words into (line 1, line 2) at a word boundary so line 1 fits ``width_px``
    (measured with the real font on the real device)."""
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


class Placed:
    """One field laid out: its box (device units), the text, the font that fits, and how it fits:
    state 'ok' (set size), 'shrunk' (smaller or narrower to fit) or 'overflow' (too long even at the minimum)."""
    __slots__ = ('key', 'rect', 'text', 'font', 'state', 'size')

    def __init__(self, key, rect, text, font, state, size):
        self.key, self.rect, self.text, self.font, self.state, self.size = key, rect, text, font, state, size


def _fits(fm, text, w, h, spacing_px=0.0):
    tall = fm.ascent() + fm.descent() <= h + 0.01
    if spacing_px:
        return tall and all(fm.horizontalAdvance(ch) <= spacing_px + 0.01 for ch in text)
    return tall and fm.horizontalAdvance(text) <= w + 0.01


def _fit(tpl, f, texts, widths, height, ratio, device, numeric=False, spacing_px=0.0):
    """The largest font (same for every text given) that puts each text inside its width and the height:
    the set size, else smaller down to the minimum, else at the minimum slightly condensed."""
    tries = [(s, 100) for s in _sizes(f)] + [(min_size(f), st) for st in (95, 90, 85, 80)]
    for i, (size, stretch) in enumerate(tries):
        font = _font(tpl, f, ratio, size, stretch, numeric)
        fm = QFontMetricsF(font, device) if device is not None else QFontMetricsF(font)
        if all(_fits(fm, t, w, height, spacing_px) for t, w in zip(texts, widths)):
            return font, size, ('ok' if i == 0 else 'shrunk')
    size, stretch = tries[-1]
    return _font(tpl, f, ratio, size, stretch, numeric), size, 'overflow'


def layout_cheque(tpl, values, origin_mm, k, ratio, device=None):
    """{field key: Placed} — every visible field with text, fitted to its box. ``k`` = device units per mm,
    ``ratio`` scales points so a 10 pt field is 10 pt on paper whatever the device."""
    ox, oy = origin_mm
    fields = tpl['fields']
    out = {}

    def box(f):
        return QRectF((ox + float(f.get('x') or 0)) * k, (oy + float(f.get('y') or 0)) * k,
                      float(f.get('w') or 30) * k, float(f.get('h') or 7) * k)

    # amount in words over two lines: one font for both, line 1 broken at a word boundary by its measured width
    w1, w2 = fields.get('words1') or {}, fields.get('words2') or {}
    words = (values.get('words') or '').strip()
    if words and w1.get('visible', True):
        r1, two = box(w1), w2.get('visible', True)
        r2 = box(w2) if two else None
        best = None
        tries = [(s, 100) for s in _sizes(w1)] + [(min_size(w1), st) for st in (95, 90, 85, 80)]
        for i, (size, stretch) in enumerate(tries):
            font = _font(tpl, w1, ratio, size, stretch)
            fm = QFontMetricsF(font, device) if device is not None else QFontMetricsF(font)
            if two:
                first, rest = split_words(words, font, r1.width(), device)
                ok = _fits(fm, first, r1.width(), min(r1.height(), r2.height())) and \
                    (not rest or fm.horizontalAdvance(rest) <= r2.width() + 0.01)
            else:
                first, rest = words, ''
                ok = _fits(fm, first, r1.width(), r1.height())
            best = (font, size, first, rest, 'ok' if i == 0 else 'shrunk')
            if ok:
                break
        else:
            best = best[:4] + ('overflow',)
        font, size, first, rest, state = best
        out['words1'] = Placed('words1', r1, first, font, state, size)
        if two and rest:
            out['words2'] = Placed('words2', r2, rest, font, state, size)

    for key in ('date', 'payee', 'amount_dinar', 'amount_fils', 'amount_full', 'memo', 'cheque_no', 'crossing'):
        f = fields.get(key) or {}
        text = values.get(key) or ''
        if not f.get('visible', True) or not text:
            continue
        r = box(f)
        spacing_px = float(f.get('spacing') or 0) * k
        if key == 'crossing':       # text between the stamp's two lines, 1 mm from each end
            font, size, state = _fit(tpl, f, [text], [r.width() - 2 * k], r.height() - 1.2 * k, ratio, device)
        else:
            if spacing_px:
                r = QRectF(r.left(), r.top(), spacing_px * len(text), r.height())
            font, size, state = _fit(tpl, f, [text], [r.width()], r.height(), ratio, device, key in NUMERIC,
                                     spacing_px)
            if spacing_px and spacing_px * len(text) > float(f.get('w') or 30) * k + 0.01:
                state = 'overflow'
        out[key] = Placed(key, r, text, font, state, size)
    return out


def fit_report(tpl, values, dpi=300):
    """{field key: 'ok' | 'shrunk' | 'overflow'} measured as on a printer of ``dpi`` — for the template editor."""
    img = QImage(8, 8, QImage.Format_ARGB32)
    img.setDotsPerMeterX(round(dpi / 0.0254))
    img.setDotsPerMeterY(round(dpi / 0.0254))
    k = dpi / 25.4
    return {key: pl.state for key, pl in layout_cheque(tpl, values, (0, 0), k, k * 25.4 / img.logicalDpiY(), img).items()}


def _baseline(r, fm, valign):
    if valign == 'center':
        return r.center().y() + (fm.ascent() - fm.descent()) / 2
    if valign == 'top':
        return r.top() + fm.ascent()
    return r.bottom() - fm.descent()        # on the line: descenders end on the box's bottom edge


def _draw_text(p, pl, f, numeric, device):
    fm = QFontMetricsF(pl.font, device) if device is not None else QFontMetricsF(pl.font)
    r = pl.rect
    base = _baseline(r, fm, f.get('valign') or 'bottom')
    p.setFont(pl.font)
    spacing = float(f.get('spacing') or 0)
    if spacing > 0:                         # boxed digits (a date printed in separate squares), left to right
        cell = pl.rect.width() / max(1, len(pl.text))
        x = r.left()
        for ch in pl.text:
            p.drawText(QPointF(x + (cell - fm.horizontalAdvance(ch)) / 2, base), ch)
            x += cell
        return
    layout = QTextLayout(pl.text, pl.font, device)
    opt = QTextOption()
    opt.setWrapMode(QTextOption.NoWrap)
    if numeric:
        opt.setTextDirection(Qt.LeftToRight)
    layout.setTextOption(opt)
    layout.beginLayout()
    line = layout.createLine()
    layout.endLayout()
    if not line.isValid():
        return
    width = line.naturalTextWidth()
    al = _align(f)
    x = r.left() if al == Qt.AlignLeft else (r.right() - width if al == Qt.AlignRight else r.center().x() - width / 2)
    line.setPosition(QPointF(0, 0))
    layout.draw(p, QPointF(x, base - line.ascent()))


def draw_cheque(p, tpl, values, origin_mm=(0.0, 0.0), px_per_mm=1.0, frame=False, background=None, ink=None,
                highlight=None, simulate=False, labels=None, report=None):
    """Paint on QPainter ``p``. ``px_per_mm`` converts mm to the device; fonts are scaled so a 10 pt field is
    10 pt on paper whatever the device. Every text is fitted to its field's box (see layout_cheque); ``report``
    (a dict) receives each field's fit state."""
    ox, oy = origin_mm
    k = px_per_mm
    w_mm, h_mm = float(tpl['width_mm']), float(tpl['height_mm'])
    rect = QRectF(ox * k, oy * k, w_mm * k, h_mm * k)
    p.save()
    p.setLayoutDirection(Qt.LeftToRight)     # mm are measured from the cheque's left edge, also in an RTL window
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
    device = p.device()
    dpi = device.logicalDpiY() if device else 96
    ratio = k * 25.4 / dpi if dpi else 1.0
    color = QColor(ink or '#000000')
    fields = tpl['fields']
    placed = layout_cheque(tpl, values, origin_mm, k, ratio, device)
    p.setPen(color)
    for key, pl in placed.items():
        f = fields.get(key) or {}
        if key == 'crossing':       # two parallel lines with the text between them, optionally rotated
            r = pl.rect
            p.save()
            p.translate(r.center())
            p.rotate(float(f.get('angle') or 0))
            local = QRectF(-r.width() / 2, -r.height() / 2, r.width(), r.height())
            p.setPen(QPen(color, max(1.0, 0.35 * k)))
            p.drawLine(local.topLeft(), local.topRight())
            p.drawLine(local.bottomLeft(), local.bottomRight())
            p.setPen(color)
            _draw_text(p, Placed(key, local, pl.text, pl.font, pl.state, pl.size), dict(f, valign='center'),
                       False, device)
            p.restore()
        else:
            _draw_text(p, pl, f, key in NUMERIC, device)
    if report is not None:
        report.update({key: pl.state for key, pl in placed.items()})
    if highlight:
        p.setPen(QPen(QColor('#0C67EC'), max(1.0, 0.3 * k), Qt.DotLine))
        for key in highlight:
            ff = fields.get(key)
            if ff:
                p.drawRect(QRectF((ox + float(ff['x'])) * k, (oy + float(ff['y'])) * k, float(ff.get('w') or 30) * k,
                                  float(ff.get('h') or 7) * k))
    p.restore()
    return rect


def draw_calibration(p, tpl, origin_mm, px_per_mm, sample_values):
    """Calibration sheet: the cheque outline, a 10 mm grid, every field's box with its name, and sample text.
    Print it on plain paper, lay a real cheque on it against the light, and adjust the positions."""
    k = px_per_mm
    ox, oy = origin_mm
    w_mm, h_mm = float(tpl['width_mm']), float(tpl['height_mm'])
    p.save()
    p.setLayoutDirection(Qt.LeftToRight)
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
        name = FIELDS.get(key, (key,))[0]
        if float(f['y']) < 4:          # no room above the box (top edge of the cheque): name it under the box
            p.drawText(QPointF(r.left(), r.bottom() + 2.6 * k), name)
        else:
            p.drawText(QPointF(r.left(), r.top() - 0.6 * k), name)
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

    def lab(text, x, base_y, w=30, align=Qt.AlignLeft, size=7.5, bold=True, color=None):
        """A printed caption whose text ends on the line at ``base_y`` mm."""
        p.setFont(font(size, bold))
        p.setPen(color or ink)
        p.drawText(R(x, base_y - 5, w, 4.6), int(align | Qt.AlignBottom), text)

    def line(x, y, w, dotted=False):
        p.setPen(QPen(QColor('#8c93a3'), max(1.0, 0.25 * k), Qt.DotLine if dotted else Qt.SolidLine))
        p.drawLine(R(x, y, w, 0).topLeft(), R(x, y, w, 0).topRight())

    def bottom(key, default):
        return g(key, 'y', default) + g(key, 'h', 7)

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
    # header: bank (right), second logo (left), crossing stamp area (centre)
    p.setPen(QPen(QColor('#c9c2a2'), max(1.0, 0.3 * k)))
    p.setBrush(QColor('#fffdf6'))
    p.drawRoundedRect(R(w_mm - 50, 1.5, 47, 9.5), 1.5 * k, 1.5 * k)
    p.drawRoundedRect(R(3, 1.5, 47, 9.5), 1.5 * k, 1.5 * k)
    p.setBrush(Qt.NoBrush)
    lab(labels.get('bank') or 'البنك', w_mm - 49, 8.6, 45, Qt.AlignHCenter, 8.5, color=QColor('#1f4e3d'))
    cx, cy, cw, ch = g('crossing', 'x', 62.5), g('crossing', 'y', 2), g('crossing', 'w', 50), g('crossing', 'h', 9)
    p.fillRect(R(cx, cy, cw, ch), QColor(200, 200, 205, 70))
    # date row: «Date ……… التاريخ», branch on the right
    dx, dw, dl = g('date', 'x', 18), g('date', 'w', 36), bottom('date', 13.5)
    lab('Date', 3, dl, max(5, dx - 4))
    lab('التاريخ', dx + dw + 2, dl, 16)
    line(dx, dl, dw, dotted=True)
    lab('الفرع', w_mm - 33, dl, 30, Qt.AlignRight)
    # pay to
    px, pw, pl = g('payee', 'x', 12), g('payee', 'w', 150), bottom('payee', 26)
    lab('Pay Against This Cheque', 3, pl - 7.5, 60)
    lab('ادفعوا بموجب هذا الشيك', w_mm - 63, pl - 7.5, 60, Qt.AlignRight)
    lab('To', 3, pl, max(5, px - 4))
    lab('لأمر', px + pw + 2, pl, max(5, w_mm - px - pw - 4), Qt.AlignRight)
    line(px, pl, pw, dotted=True)
    # the sum of: line 1 between «The Sum Of» and «مبلغ وقدره», line 2 below it
    wx, ww, wl = g('words1', 'x', 24), g('words1', 'w', 77), bottom('words1', 34)
    lab('The Sum Of', 3, wl, max(5, wx - 4))
    lab('مبلغ وقدره', wx + ww + 2, wl, 19)
    line(wx, wl, ww, dotted=True)
    line(g('words2', 'x', 6), bottom('words2', 42), g('words2', 'w', 115), dotted=True)
    if (f.get('memo') or {}).get('visible'):
        line(g('memo', 'x', 6), bottom('memo', 51), g('memo', 'w', 115), dotted=True)
    # amount box: a caption row, fils on the right and dinars to its left, as printed by Jordanian banks
    ad, af = f.get('amount_dinar', {}), f.get('amount_fils', {})
    full_f = f.get('amount_full', {})
    if ad.get('visible', True) or af.get('visible', True) or full_f.get('visible'):
        src_d = 'amount_dinar' if ad.get('visible', True) or not full_f.get('visible') else 'amount_full'
        x0 = g(src_d, 'x', 125) - 0.5
        y_top = g(src_d, 'y', 40.5)
        y1 = y_top + g(src_d, 'h', 7.5) + 0.5
        y0 = y_top - 5
        if af.get('visible', True) and src_d == 'amount_dinar':
            xf = g('amount_fils', 'x', 154) - 0.5
            x1 = g('amount_fils', 'x', 154) + g('amount_fils', 'w', 17) + 0.5
        else:
            x1 = g(src_d, 'x', 125) + g(src_d, 'w', 46) + 0.5
            xf = None
        p.setPen(QPen(QColor('#55596b'), max(1.0, 0.35 * k)))
        p.drawRect(R(x0, y0, x1 - x0, y1 - y0))
        p.drawLine(R(x0, y0 + 4.5, x1 - x0, 0).topLeft(), R(x0, y0 + 4.5, x1 - x0, 0).topRight())
        if xf is not None:
            p.drawLine(R(xf, y0, 0, 1).topLeft(), R(xf, y1, 0, 1).topLeft())
            lab('J.D.  دينار', x0, y0 + 4.2, xf - x0, Qt.AlignHCenter, 6.5)
            lab('Fils  فلس', xf, y0 + 4.2, x1 - xf, Qt.AlignHCenter, 6.5)
        else:
            lab('J.D.  المبلغ  Amount', x0, y0 + 4.2, x1 - x0, Qt.AlignHCenter, 6.5)
        holder = labels.get('holder')
        lab(('السادة ' + holder) if holder else 'اسم صاحب الحساب', x0 - 10, y1 + 6, x1 - x0 + 10, Qt.AlignRight, 8)
    # signature, footer, MICR line
    sy = h_mm - 13
    lab('التوقيع', 3, sy - 4, 20)
    lab('Sign', 3, sy, 14)
    line(18, sy, 50)
    line(3, h_mm - 9.5, w_mm - 6)
    lab('Please do not write under this line — الرجاء عدم الكتابة تحت هذا الخط', 0, h_mm - 6.6, w_mm,
        Qt.AlignHCenter, 5, False, QColor('#7a8090'))
    mono = QFont('Courier New')
    mono.setPointSizeF(10 * scale)
    mono.setBold(True)
    p.setFont(mono)
    p.setPen(QColor('#22252e'))
    acct = ''.join(ch for ch in (labels.get('account') or '') if ch.isdigit()) or '0000000000'
    opt = QTextOption(Qt.AlignHCenter | Qt.AlignVCenter)
    opt.setTextDirection(Qt.LeftToRight)
    p.drawText(R(8, h_mm - 6.2, w_mm - 16, 5.5), f'⑈000000⑈  ⑆00⑉000⑆  {acct}⑈', opt)
    p.restore()
