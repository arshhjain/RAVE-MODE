# Rave Mode — Build Instructions

## Project layout expected before building

```
your-project-folder/
│
├── main.py
├── state.py
├── requirements.txt
├── rave_mode.spec          ← from this package
├── build.bat               ← from this package
│
└── ui/
    └── index.html          ← your frontend file goes HERE
```

> ⚠️ The `ui/` folder and `index.html` **must** be present before you build.
> The spec bundles them automatically; at runtime the app reads them from
> `ui/index.html` relative to the executable.

---

## How to build

1. Install Python 3.10+ (64-bit) and make sure it's on your `PATH`.
2. Place `rave_mode.spec` and `build.bat` in the project root (same level as `main.py`).
3. Put `index.html` inside the `ui/` subfolder.
4. Double-click **`build.bat`**.

The script will:
- Install / upgrade PyInstaller and all requirements.
- Run `pyinstaller rave_mode.spec --noconfirm --clean`.
- Print the output location when done.

---

## Output

```
dist/
└── RaveMode/           ← distribute this whole folder
    ├── RaveMode.exe
    ├── ui/
    │   └── index.html
    └── ... (DLLs, pywebview resources, etc.)
```

**To share the app:** zip or copy the entire `dist\RaveMode\` folder.  
The `.exe` alone will not run — it needs the sibling files.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError` at startup | Add the module to `hiddenimports` in `rave_mode.spec` and rebuild. |
| Blank/white webview window | CEF resources missing — check that `collect_data_files('webview')` ran without errors during build. |
| Audio device not found | This is a runtime issue, not a build issue — check soundcard / WASAPI loopback availability. |
| `winsdk` import errors | Requires Windows 10 build 19041+ and the matching `winsdk` pip package version. |
| App opens then immediately closes | Run from a cmd window (`RaveMode.exe` in the dist folder) to see crash output, or temporarily set `console=True` in the spec. |

---

## Adding a custom icon

1. Create a 256×256 `.ico` file and save it as `ui/icon.ico`.
2. In `rave_mode.spec`, uncomment the `icon=` line in the `EXE(...)` block:
   ```python
   icon='ui/icon.ico',
   ```
3. Rebuild.
