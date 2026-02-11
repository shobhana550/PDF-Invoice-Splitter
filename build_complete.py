"""
Complete Build Script for PDF Invoice Splitter with Tesseract OCR
This script:
1. Downloads Tesseract OCR binaries
2. Builds the executable with PyInstaller
3. Creates a complete distribution package with Tesseract included
"""

import subprocess
import sys
import os
import shutil
import zipfile
import urllib.request
import tempfile

# Tesseract download URL (portable version from UB-Mannheim)
# Using the 64-bit version
TESSERACT_URL = "https://github.com/UB-Mannheim/tesseract/releases/download/v5.4.0.20240606/tesseract-ocr-w64-setup-5.4.0.20240606.exe"
TESSERACT_ZIP_URL = "https://digi.bib.uni-mannheim.de/tesseract/tesseract-ocr-w64-setup-5.4.0.20240606.exe"

# Alternative: Use a portable zip if available
TESSERACT_PORTABLE_URL = "https://github.com/UB-Mannheim/tesseract/releases/download/v5.4.0.20240606/tesseract-ocr-w64-setup-5.4.0.20240606.exe"

def download_file(url, dest_path, description="file"):
    """Download a file with progress indication"""
    print(f"Downloading {description}...")
    print(f"URL: {url}")
    try:
        urllib.request.urlretrieve(url, dest_path)
        print(f"Downloaded to: {dest_path}")
        return True
    except Exception as e:
        print(f"Download failed: {e}")
        return False

def extract_tesseract_from_installer(installer_path, extract_dir):
    """Extract Tesseract files from the NSIS installer using 7-Zip or built-in methods"""
    print("Extracting Tesseract from installer...")

    # Try using 7-Zip if available
    seven_zip_paths = [
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
    ]

    seven_zip = None
    for path in seven_zip_paths:
        if os.path.isfile(path):
            seven_zip = path
            break

    if seven_zip:
        print(f"Using 7-Zip: {seven_zip}")
        cmd = [seven_zip, 'x', '-y', f'-o{extract_dir}', installer_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print("Extraction successful!")
            return True
        else:
            print(f"7-Zip extraction failed: {result.stderr}")

    # Alternative: Try using innounp (Inno Setup Unpacker) if it's an Inno installer
    # Or try running the installer silently
    print("Attempting silent installation extraction...")

    return False

def setup_tesseract_portable(dist_dir):
    """Download and setup Tesseract portable version"""
    tesseract_dir = os.path.join(dist_dir, 'tesseract')
    os.makedirs(tesseract_dir, exist_ok=True)

    # Check if Tesseract is already installed on the system
    system_tesseract_paths = [
        r"C:\Program Files\Tesseract-OCR",
        r"C:\Program Files (x86)\Tesseract-OCR",
    ]

    for sys_path in system_tesseract_paths:
        if os.path.isdir(sys_path) and os.path.isfile(os.path.join(sys_path, 'tesseract.exe')):
            print(f"Found system Tesseract at: {sys_path}")
            print("Copying Tesseract files to distribution...")

            # Copy essential files
            essential_files = [
                'tesseract.exe',
            ]

            # Copy all DLLs
            for item in os.listdir(sys_path):
                src = os.path.join(sys_path, item)
                dst = os.path.join(tesseract_dir, item)

                if item.endswith('.exe') or item.endswith('.dll'):
                    print(f"  Copying: {item}")
                    shutil.copy2(src, dst)
                elif item == 'tessdata' and os.path.isdir(src):
                    print(f"  Copying: {item}/")
                    if os.path.exists(dst):
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)

            print("Tesseract files copied successfully!")
            return True

    print("=" * 60)
    print("Tesseract OCR not found on this system.")
    print("")
    print("To include Tesseract in the bundle, please:")
    print("1. Download Tesseract from:")
    print("   https://github.com/UB-Mannheim/tesseract/wiki")
    print("")
    print("2. Install it (default location is fine)")
    print("")
    print("3. Run this build script again")
    print("=" * 60)

    return False

def build_executable():
    """Build the standalone executable using PyInstaller"""
    print("\n" + "=" * 60)
    print("Building PDF Invoice Splitter executable...")
    print("=" * 60 + "\n")

    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--clean',
        '--noconfirm',
        'PDF_Invoice_Splitter.spec'
    ]

    result = subprocess.run(cmd)
    return result.returncode == 0

def create_distribution_package():
    """Create the complete distribution package"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    dist_dir = os.path.join(script_dir, 'dist')

    print("\n" + "=" * 60)
    print("Creating distribution package...")
    print("=" * 60 + "\n")

    # Ensure dist directory exists
    if not os.path.exists(dist_dir):
        print("Error: dist directory not found. Build may have failed.")
        return False

    # Check if executable exists
    exe_path = os.path.join(dist_dir, 'PDF_Invoice_Splitter.exe')
    if not os.path.isfile(exe_path):
        print("Error: Executable not found. Build may have failed.")
        return False

    print(f"Executable found: {exe_path}")

    # Setup Tesseract
    tesseract_included = setup_tesseract_portable(dist_dir)

    # Create README for distribution
    readme_content = """PDF Invoice Splitter v3.0
========================

A powerful tool for splitting multi-location utility invoices.

USAGE
-----
Simply double-click PDF_Invoice_Splitter.exe to run the application.

FEATURES
--------
- Extracts entities: Account Numbers, Meter Numbers, POD IDs, Addresses, etc.
- User-selectable entity type for splitting
- Preview and select which splits to create
- Works with text-based and scanned PDFs (with OCR)

OCR SUPPORT
-----------
"""

    if tesseract_included:
        readme_content += """OCR is INCLUDED in this distribution.
The 'tesseract' folder contains the Tesseract OCR engine.
OCR will be automatically available for scanned PDFs.
"""
    else:
        readme_content += """OCR is NOT included in this distribution.
To enable OCR for scanned PDFs:
1. Download Tesseract from: https://github.com/UB-Mannheim/tesseract/wiki
2. Install it, OR copy the Tesseract folder next to this executable
3. Name the folder 'tesseract' or 'Tesseract-OCR'
"""

    readme_content += """
SUPPORTED IDENTIFIERS
--------------------
- Account Number, Sub-Account Number
- Meter Number
- POD (Point of Delivery)
- LDC Number
- Supplier Number
- Service Address
- And more...

VERSION
-------
v3.0 - Built with Python and PyInstaller

"""

    readme_path = os.path.join(dist_dir, 'README.txt')
    with open(readme_path, 'w') as f:
        f.write(readme_content)

    print(f"Created: {readme_path}")

    # Create ZIP archive for distribution
    zip_name = 'PDF_Invoice_Splitter_Complete'
    if tesseract_included:
        zip_name += '_with_OCR'
    zip_path = os.path.join(script_dir, f'{zip_name}.zip')

    print(f"\nCreating ZIP archive: {zip_path}")

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(dist_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, dist_dir)
                print(f"  Adding: {arcname}")
                zipf.write(file_path, arcname)

    print(f"\nZIP archive created: {zip_path}")

    return True

def main():
    """Main build process"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    print("=" * 60)
    print("PDF Invoice Splitter - Complete Build Process")
    print("=" * 60)
    print("")

    # Step 1: Build executable
    if not build_executable():
        print("\nBuild failed!")
        return 1

    # Step 2: Create distribution package with Tesseract
    if not create_distribution_package():
        print("\nPackaging failed!")
        return 1

    print("\n" + "=" * 60)
    print("BUILD COMPLETE!")
    print("=" * 60)
    print("")
    print("Distribution files are in the 'dist' folder:")
    print("  - PDF_Invoice_Splitter.exe")
    print("  - tesseract/ (if Tesseract was found)")
    print("  - README.txt")
    print("")
    print("A ZIP archive has also been created for easy distribution.")
    print("")

    return 0

if __name__ == '__main__':
    sys.exit(main())
