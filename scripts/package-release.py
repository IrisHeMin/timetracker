"""Create allowlisted public downloads; never read the user's data directory."""

import hashlib
from pathlib import Path
import re
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
DIST.mkdir(exist_ok=True)
source = (ROOT / "dayledger" / "index.html").read_text(encoding="utf-8")
for filename in ("ledger.js", "ui.js"):
    script = (ROOT / "dayledger" / filename).read_text(encoding="utf-8")
    script = re.sub(r"</script", r"<\\/script", script, flags=re.IGNORECASE)
    source = source.replace(f'<script src="{filename}"></script>', f"<script>\n{script}\n</script>")
offline = DIST / "DayLedger-offline.html"
offline.write_text(source, encoding="utf-8")
with zipfile.ZipFile(DIST / "DayLedger-offline.zip", "w", zipfile.ZIP_DEFLATED) as archive:
    archive.write(offline, offline.name)
    archive.write(ROOT / "desktop" / "DOWNLOAD-README.txt", "README.txt")
windows = DIST / "DayLedger"
if not (windows / "DayLedger.exe").is_file():
    raise SystemExit("Build dist\\DayLedger\\DayLedger.exe with PyInstaller first.")
with zipfile.ZipFile(DIST / "DayLedger-Windows-x64.zip", "w", zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(windows.rglob("*")):
        if path.is_file():
            if path.suffix.lower() in (".sqlite3", ".log") or "reports" in path.parts:
                raise SystemExit(f"Unexpected private data in build: {path.name}")
            archive.write(path, path.relative_to(DIST))
    archive.write(ROOT / "desktop" / "DOWNLOAD-README.txt", "DayLedger/README.txt")
    notices = [
        (Path(sys.base_prefix) / "LICENSE.txt", "Python-LICENSE.txt"),
        (Path(sys.base_prefix) / "tcl" / "tk8.6" / "license.terms", "Tk-license.terms"),
    ]
    pyinstaller_notices = list((ROOT / ".build-venv" / "Lib" / "site-packages").glob(
        "pyinstaller-*.dist-info/licenses/COPYING.txt"))
    if not pyinstaller_notices:
        raise SystemExit("PyInstaller runtime notice not found; build using .build-venv.")
    notices.append((pyinstaller_notices[0], "PyInstaller-COPYING.txt"))
    for path, name in notices:
        archive.write(path, f"DayLedger/THIRD-PARTY/{name}")
artifacts = [offline, DIST / "DayLedger-offline.zip", DIST / "DayLedger-Windows-x64.zip"]
(DIST / "SHA256SUMS.txt").write_text("".join(
    f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in artifacts),
    encoding="ascii")
for path in artifacts:
    print(f"{path.name}: {path.stat().st_size:,} bytes")
