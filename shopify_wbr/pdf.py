"""Optional PDF export using a locally installed Chrome/Chromium (headless)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

CANDIDATES = [
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
]


def find_chrome() -> str | None:
    env = os.environ.get("WBR_CHROME")
    if env:
        return env
    for c in CANDIDATES:
        path = shutil.which(c) or (c if Path(c).exists() else None)
        if path:
            return path
    return None


def html_to_pdf(html_path: Path, pdf_path: Path) -> bool:
    chrome = find_chrome()
    if not chrome:
        print("[shopify-wbr] Chrome/Chromium not found; skipping PDF (set WBR_CHROME to its path).")
        return False
    cmd = [
        chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_path.resolve()}", html_path.resolve().as_uri(),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return result.returncode == 0 and pdf_path.exists()
