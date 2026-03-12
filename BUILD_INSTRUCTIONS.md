# PDF Invoice Splitter - Build Instructions (PyInstaller)

## Step 1: Install PyInstaller

Open PowerShell or Command Prompt and run:

```powershell
pip install pyinstaller
```

## Step 2: Build the Executable

Navigate to your Splitter folder:

```powershell
cd c:\Users\kkaushalendra\Splitter
```

Then run the build command:

```powershell
pyinstaller --onefile --windowed --name "PDF_Invoice_Splitter" splitter.py
```

## What This Does:

- `--onefile`: Creates a single .exe file (not a folder with many files)
- `--windowed`: Hides the console window (GUI-only)
- `--name`: Names the executable "PDF_Invoice_Splitter.exe"

## Build Output:

After building, you'll find:

```
your_folder/
├── build/              (temporary files, can be deleted)
├── dist/
│   └── PDF_Invoice_Splitter.exe    ✅ This is your executable!
├── splitter.spec       (build specification file)
└── splitter.py
```

## Step 3: Distribute the Executable

The file `dist\PDF_Invoice_Splitter.exe` is now **portable**:

1. Copy just this `.exe` file to a USB drive
2. Run it on any Windows computer (Windows 7 and newer)
3. **No Python installation needed!**

## Optional: Create an Icon

For a custom icon, place an `icon.ico` file in your Splitter folder and modify the build command:

```powershell
pyinstaller --onefile --windowed --icon=icon.ico --name "PDF_Invoice_Splitter" splitter.py
```

---

## Quick Start (Copy-Paste)

```powershell
cd c:\Users\kkaushalendra\Splitter
pip install pyinstaller
pyinstaller --onefile --windowed --name "PDF_Invoice_Splitter" splitter.py
```

Your executable will be ready in `dist\PDF_Invoice_Splitter.exe`

---

## Notes:

- First build may take 2-5 minutes
- Subsequent builds will be faster
- The .exe file will be ~200-300 MB (includes Python runtime)
- It's completely self-contained and portable
