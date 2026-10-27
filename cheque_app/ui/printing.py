"""Printing (printer, preview, PDF) and the live on-screen cheque preview."""
import os

from PySide6.QtCore import QMarginsF, QSizeF, Qt
from PySide6.QtGui import QColor, QImage, QPageLayout, QPageSize, QPainter
from PySide6.QtPrintSupport import QPrintDialog, QPrinter, QPrinterInfo, QPrintPreviewDialog
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..core.render import draw_cheque, page_size_mm, paint_page
from .common import L, error


def load_background(path):
    if path and os.path.isfile(path):
        img = QImage(path)
        if not img.isNull():
            return img
    return None


def describe_cheque(values, labels=None):
    """A sentence that tells what the cheque preview shows (its accessible description / alt text)."""
    labels = labels or {}
    parts = []
    for key, ar, en in (('date', 'التاريخ', 'date'), ('payee', 'المستفيد', 'payee'),
                        ('amount_full', 'المبلغ', 'amount'), ('words', 'المبلغ كتابةً', 'amount in words'),
                        ('crossing', 'التسطير', 'crossing'), ('cheque_no', 'رقم الشيك', 'cheque number')):
        v = (values or {}).get(key)
        if v:
            parts.append(f'{L(ar, en)}: {v}')
    head = L('معاينة الشيك', 'Cheque preview') + (f' — {labels["bank"]}' if labels.get('bank') else '')
    return head + ('. ' + '، '.join(parts) if parts else L('. لا توجد بيانات بعد.', '. No data yet.'))


class ChequePreview(QWidget):
    """The cheque as it will print, scaled to the widget keeping its proportions (with the bank's scanned blank
    cheque, or a drawn cheque face, behind it — on screen only)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tpl, self.values, self.bg, self.highlight, self.labels = None, {}, None, None, {}
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAccessibleName(L('معاينة الشيك', 'Cheque preview'))
        self.setAccessibleDescription(describe_cheque({}))
        self.setFocusPolicy(Qt.TabFocus)

    def show_cheque(self, tpl, values, background=None, highlight=None, labels=None):
        self.tpl, self.values, self.bg, self.highlight, self.labels = tpl, values, background, highlight, labels or {}
        self.setAccessibleDescription(describe_cheque(values, self.labels))
        self.setToolTip(L('معاينة: هكذا تقع البيانات على الشيك. الخلفية للعرض فقط ولا تُطبع.',
                          'Preview: this is where the data lands on the cheque. The background is not printed.'))
        self.update()

    def hasHeightForWidth(self):
        # the preview fills the space left under the form (the drawing keeps the cheque's proportions); a height
        # tied to the width made it grow without limit inside the scrolling page
        return False

    def heightForWidth(self, w):
        if not self.tpl:
            return 200
        return int(w * float(self.tpl['height_mm']) / float(self.tpl['width_mm']))

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor('#eef2f7'))
        if not self.tpl:
            p.end()
            return
        w_mm, h_mm = float(self.tpl['width_mm']), float(self.tpl['height_mm'])
        pad = 18
        k = max(0.5, min((self.width() - 2 * pad) / w_mm, (self.height() - 2 * pad) / h_mm))
        ox = (self.width() / k - w_mm) / 2
        oy = (self.height() / k - h_mm) / 2
        # a soft shadow under the paper
        for i, alpha in ((6, 18), (4, 22), (2, 30)):
            p.fillRect(int(ox * k) - i + 3, int(oy * k) - i + 5, int(w_mm * k) + 2 * i, int(h_mm * k) + 2 * i,
                       QColor(15, 23, 42, alpha // 3))
        p.fillRect(int(ox * k), int(oy * k), int(w_mm * k), int(h_mm * k), QColor('#fffaf3'))
        # on screen only: the bank's scanned blank cheque, else a drawn cheque face — the printer prints the data only
        try:
            draw_cheque(p, self.tpl, self.values, (ox, oy), k, frame=False, background=self.bg,
                        ink='#0b2a6b', highlight=self.highlight, simulate=True, labels=self.labels)
            p.setPen(QColor('#c3cddb'))
            p.setBrush(Qt.NoBrush)
            p.drawRect(int(ox * k), int(oy * k), int(w_mm * k), int(h_mm * k))
        finally:
            p.end()


def _setup_printer(printer, tpl, settings_get):
    w, h = page_size_mm(tpl)
    printer.setFullPage(True)
    # a page size is always defined upright; a wide cheque is that size turned to landscape
    size = QPageSize(QSizeF(min(w, h), max(w, h)), QPageSize.Millimeter, 'Cheque', QPageSize.ExactMatch)
    if (tpl.get('feed') or {}).get('paper') == 'A4':
        size = QPageSize(QPageSize.A4)
    elif (tpl.get('feed') or {}).get('paper') == 'Letter':
        size = QPageSize(QPageSize.Letter)
    orient = QPageLayout.Landscape if w > h else QPageLayout.Portrait
    if (tpl.get('feed') or {}).get('paper') in ('A4', 'Letter'):
        orient = QPageLayout.Portrait
    printer.setPageLayout(QPageLayout(size, orient, QMarginsF(0, 0, 0, 0)))
    name = settings_get('printer') if settings_get else None
    if name and name in QPrinterInfo.availablePrinterNames():
        printer.setPrinterName(name)


def _doc_name(jobs, calibration):
    """The document title (shown by the print queue and stored as the PDF's Title)."""
    if calibration:
        return L('صفحة معايرة قالب الشيك', 'Cheque template calibration sheet')
    v = jobs[0][1] if jobs else {}
    name = L('شيك', 'Cheque') + (f' {v["cheque_no"]}' if v.get('cheque_no') else '') + \
        (f' — {v["payee"]}' if v.get('payee') else '')
    return name + (L(f' و{len(jobs) - 1} غيره', f' and {len(jobs) - 1} more') if len(jobs) > 1 else '')


def _render(printer, jobs, calibration=False):
    printer.setDocName(_doc_name(jobs, calibration))
    printer.setCreator('ChequePrinter')
    p = QPainter()
    if not p.begin(printer):
        return False
    try:
        for i, (tpl, values) in enumerate(jobs):
            if i:
                printer.newPage()
            rect = printer.pageLayout().fullRect(QPageLayout.Millimeter)
            paint_page(p, rect.width(), rect.height(), printer.resolution() / 25.4, tpl, values, calibration)
    finally:
        p.end()
    return True


def print_jobs(parent, jobs, settings_get=None, settings_set=None, calibration=False, ask=True):
    """jobs: [(template, values)]. Returns True when sent to the printer."""
    if not jobs:
        return False
    printer = QPrinter(QPrinter.HighResolution)
    _setup_printer(printer, jobs[0][0], settings_get)
    if ask:
        dlg = QPrintDialog(printer, parent)
        dlg.setWindowTitle(L('طباعة الشيك', 'Print cheque'))
        if dlg.exec() != QPrintDialog.Accepted:
            return False
        if settings_set:
            settings_set('printer', printer.printerName())
    if not _render(printer, jobs, calibration):
        error(parent, L('تعذّر بدء الطباعة على الطابعة المختارة.', 'Could not start printing on the chosen printer.'))
        return False
    return True


def preview_jobs(parent, jobs, settings_get=None, calibration=False):
    printer = QPrinter(QPrinter.HighResolution)
    _setup_printer(printer, jobs[0][0], settings_get)
    dlg = QPrintPreviewDialog(printer, parent)
    dlg.setWindowTitle(L('معاينة الطباعة', 'Print preview'))
    dlg.paintRequested.connect(lambda pr: _render(pr, jobs, calibration))
    from .theme import fit_to_screen
    fit_to_screen(dlg, 1000, 700)
    dlg.exec()


def save_pdf(path, jobs, calibration=False):
    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(path)
    _setup_printer(printer, jobs[0][0], None)
    return _render(printer, jobs, calibration)
