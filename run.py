"""Start the program from source: python run.py (PyInstaller builds ChequePrinter.exe from this file)."""
import sys

from cheque_app.main import main

if __name__ == '__main__':
    sys.exit(main())
