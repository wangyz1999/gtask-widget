"""Write GitHub release notes for a version: its CHANGELOG section plus install steps.

    python tools/release_notes.py 0.1.0 [notes.md]
"""

import re
import sys
from pathlib import Path

version = sys.argv[1].lstrip("v")
changelog = (Path(__file__).resolve().parents[1] / "CHANGELOG.md").read_text(encoding="utf-8")
match = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## |\Z)", changelog, re.S | re.M)
section = match.group(1).strip() if match else "See CHANGELOG.md."

notes = f"""{section}

### Install

| File | What it is |
| --- | --- |
| `GTaskWidget-Setup-{version}.exe` | **Recommended.** Installer for your user only (no admin rights needed). Optionally starts with Windows. |
| `GTaskWidget-{version}-portable.zip` | No install: unzip anywhere and run `GTaskWidget.exe`. |
| `SHA256SUMS.txt` | Checksums to verify your download. |

On first run, Windows SmartScreen may say *"Windows protected your PC"* because the app isn't code-signed yet. Click **More info → Run anyway**.
If Google shows *"Google hasn't verified this app"*, click **Advanced → Go to GTask Widget**. The app only requests access to Google Tasks.
"""

if len(sys.argv) > 2:
    Path(sys.argv[2]).write_text(notes, encoding="utf-8")
else:
    sys.stdout.reconfigure(encoding="utf-8")
    print(notes)
