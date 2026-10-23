import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ['CHEQUE_TEST'] = '1'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication  # noqa: E402

_APP = QApplication.instance() or QApplication([])   # widgets need a QApplication, created before any test
