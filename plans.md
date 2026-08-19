# DDWriter — Windows Compatibility Plan

## Overview

Cross-platform rewrite supporting Linux + Windows using tkinter/customtkinter with conditional backends.

## Approach: Cross-Platform Rewrite (Recommended)

### 1. GUI Framework — Switch to `tkinter` or `customtkinter`

- `tkinter` is built-in with Python (no extra install)
- `customtkinter` provides modern dark/light themes
- Both work identically on Linux, Windows, macOS

### 2. Device Detection

```bash
# Linux (current)
lsblk -J -o NAME,MODEL,SIZE,RM,TYPE

# Windows (new)
wmic diskdrive get DeviceID,Model,Size,MediaType
# or PowerShell: Get-Disk | Select-Object Number,FriendlyName,Size,PartitionStyle
```

### 3. Write Backend

```bash
# Linux (current)
sudo dd if=<iso> of=/dev/sdX bs=4M status=progress

# Windows (new)
Option A: Bundle dd.exe from MSYS2 (easiest, most compatible)
Option B: Use ctypes to call DeviceIoControl (no external deps, complex)
Option C: Use raw disk access via \\.\PhysicalDriveN (moderate complexity)
```

### 4. Permissions

```bash
# Linux (current)
sudo -S dd ...

# Windows (new)
- Embed manifest requiring Administrator
- Or: ctypes.windll.shell32.ShellExecuteW(None, "runas", "python", script, None, 1)
```

### 5. Eject

```bash
# Linux (current)
sudo udisksctl power-off -b /dev/sdX

# Windows (new)
- ctypes: DeviceIoControl with IOCTL_STORAGE_EJECT_MEDIA
- Or: powershell "Dismount-Volume -DriveLetter X"
```

## File Structure (Cross-Platform)

```
ddwriter/
├── ddwriter.py          # Main app (tkinter)
├── backends/
│   ├── linux.py         # lsblk, dd, udisksctl
│   └── windows.py       # wmic, dd.exe, eject
├── gui/
│   └── app.py           # Cross-platform GUI
├── install.sh           # Linux installer
├── install.bat          # Windows installer
└── requirements.txt     # customtkinter (optional)
```

## Estimated Effort

| Component       | Linux (done) | Windows | Total |
|-----------------|--------------|---------|-------|
| GUI             | ✓            | Rewrite (~200 LOC) | 200 |
| Device detection| ✓            | New (~50 LOC) | 50 |
| Write backend   | ✓            | New (~80 LOC) | 80 |
| Permissions     | ✓            | New (~30 LOC) | 30 |
| Eject           | ✓            | New (~40 LOC) | 40 |
| **Total**       |              |         | **~400 LOC** |

## Distribution

- Windows: Bundle with PyInstaller → single `.exe`
- Or: `pip install ddwriter` + `python -m ddwriter`
