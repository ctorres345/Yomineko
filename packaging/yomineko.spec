# PyInstaller spec: one folder holding the command-line program (yomineko) and the windowed
# desktop app (yomineko-app), sharing one set of libraries.
#
#   pip install -e ".[app,analyze]" pyinstaller
#   pyinstaller --noconfirm --distpath dist --workpath build packaging/yomineko.spec
#
# The Sudachi tokenizer and its dictionary are bundled (Apache-2.0). Nothing else from outside
# the project is: no ROMs, no game text, no JMdict (the app downloads that when the user asks).
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

HERE = SPECPATH  # the folder this file is in

datas, binaries, hiddenimports = [], [], []
for package in ("sudachipy", "sudachidict_core"):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h
# templates, vendored htmx and Pico CSS, profiles, reviews and schemas are package data
datas += collect_data_files("yomineko")
datas += collect_data_files("webview")
# certifi's trusted certificates: a frozen Python cannot find the system's on macOS
datas += collect_data_files("certifi")
# loaded by name at run time, so the analysis cannot see them
for package in ("yomineko", "uvicorn", "webview", "multipart", "python_multipart"):
    hiddenimports += collect_submodules(package)

EXCLUDES = ["tkinter", "pytest", "mypy", "ruff"]


def analysis(script):
    return Analysis(
        [f"{HERE}/{script}"],
        pathex=[],
        binaries=binaries,
        datas=datas,
        hiddenimports=hiddenimports,
        excludes=EXCLUDES,
    )


cli = analysis("cli_entry.py")
gui = analysis("app_entry.py")
MERGE((cli, "cli_entry", "yomineko"), (gui, "app_entry", "yomineko-app"))

cli_exe = EXE(
    PYZ(cli.pure), cli.scripts, [], exclude_binaries=True, name="yomineko", console=True
)
gui_exe = EXE(
    PYZ(gui.pure), gui.scripts, [], exclude_binaries=True, name="yomineko-app", console=False
)
COLLECT(
    cli_exe, cli.binaries, cli.datas,
    gui_exe, gui.binaries, gui.datas,
    name="yomineko",
)
