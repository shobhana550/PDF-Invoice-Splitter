"""
Build script for creating standalone PDF Invoice Splitter executable.
Run this script to create the executable: python build_exe.py
"""

import subprocess
import sys
import os

def build_executable():
    """Build the standalone executable using PyInstaller."""

    # PyInstaller command with all necessary options
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--onefile',                    # Single executable file
        '--windowed',                   # No console window (GUI app)
        '--name', 'PDF_Invoice_Splitter',

        # Hidden imports that PyInstaller might miss
        '--hidden-import=pdfplumber',
        '--hidden-import=pdfplumber.page',
        '--hidden-import=pdfplumber.pdf',
        '--hidden-import=pdfplumber.utils',
        '--hidden-import=pdfminer',
        '--hidden-import=pdfminer.pdfparser',
        '--hidden-import=pdfminer.pdfdocument',
        '--hidden-import=pdfminer.pdfpage',
        '--hidden-import=pdfminer.pdfinterp',
        '--hidden-import=pdfminer.converter',
        '--hidden-import=pdfminer.layout',
        '--hidden-import=pdfminer.image',
        '--hidden-import=PyPDF2',
        '--hidden-import=pandas',
        '--hidden-import=pandas.core',
        '--hidden-import=rapidfuzz',
        '--hidden-import=rapidfuzz.fuzz',
        '--hidden-import=rapidfuzz.process',
        '--hidden-import=PIL',
        '--hidden-import=PIL.Image',
        '--hidden-import=PIL.ImageTk',
        '--hidden-import=pytesseract',
        '--hidden-import=spacy',
        '--hidden-import=tkinter',
        '--hidden-import=tkinter.ttk',
        '--hidden-import=tkinter.filedialog',
        '--hidden-import=tkinter.messagebox',
        '--hidden-import=tkinter.scrolledtext',
        '--hidden-import=typing_extensions',
        '--hidden-import=charset_normalizer',
        '--hidden-import=numpy',
        '--hidden-import=dateutil',
        '--hidden-import=pytz',

        # Collect all submodules for these packages
        '--collect-all=pdfplumber',
        '--collect-all=pdfminer',
        '--collect-all=rapidfuzz',

        # Don't confirm overwrite
        '--noconfirm',

        # Clean build
        '--clean',

        # Main script
        'splitter.py'
    ]

    print("Building PDF Invoice Splitter executable...")
    print("This may take several minutes...")
    print("-" * 50)

    try:
        result = subprocess.run(cmd, check=True)
        print("-" * 50)
        print("BUILD SUCCESSFUL!")
        print("")
        print("Executable created at: dist/PDF_Invoice_Splitter.exe")
        print("")
        print("IMPORTANT NOTES:")
        print("1. The executable includes all Python dependencies.")
        print("2. For OCR functionality (scanned PDFs), Tesseract OCR must be")
        print("   installed separately on the target system.")
        print("   Download from: https://github.com/UB-Mannheim/tesseract/wiki")
        print("3. For advanced NLP features, spaCy models may need to be available.")
        print("   The app will fall back to regex-only mode if spaCy is unavailable.")
        print("")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Build failed with error: {e}")
        return False
    except FileNotFoundError:
        print("PyInstaller not found. Installing...")
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'pyinstaller'], check=True)
        print("Please run this script again.")
        return False

if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    success = build_executable()
    sys.exit(0 if success else 1)
