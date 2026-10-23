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


class ChequePreview(QWidget):
    """The cheque as it will print, scaled to the widget (with the bank's scanned blank cheque behind it)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tpl, self.values, self.bg, self.highlight = None, {}, None, None
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def show_cheque(self, tpl, values, background=None, highlight=None):
        self.tpl, self.values, self.bg, self.highlight = tpl, values, background, highlight
        self.update()

    def heightForWidth(self, w):
        if not self.tpl:
            return 200
        return int(w * float(self.tpl['height_mm']) / float(self.tpl['width_mm']))

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#eef1f5'))
        if not self.tpl:
            p.end()
            return
        w_mm, h_mm = float(self.tpl['width_mm']), float(self.tpl['height_mm'])
        k = min((self.width() - 16) / w_mm, (self.height() - 16) / h_mm)
        ox = (self.width() / k - w_mm) / 2
        oy = (self.height() / k - h_mm) / 2
        p.fillRect(int(ox * k), int(oy * k), int(w_mm * k), int(h_mm * k), QColor('#fffaf3'))
        draw_cheque(p, self.tpl, self.values, (ox, oy), k, frame=True, background=self.bg,
                    ink='#0b2a6b', highlight=self.highlight)
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


def _render(printer, jobs, calibration=False):
    p = QPainter()
    if not p.begin(printer):
        return False
    for i, (tpl, values) in enumerate(jobs):
        if i:
            printer.newPage()
        rect = printer.pageLayout().fullRect(QPageLayout.Millimeter)
        paint_page(p, rect.width(), rect.height(), printer.resolution() / 25.4, tpl, values, calibration)
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
    dlg.resize(1000, 700)
    dlg.exec()


def save_pdf(path, jobs, calibration=False):
    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(path)
    _setup_printer(printer, jobs[0][0], None)
    return _render(printer, jobs, calibration)
