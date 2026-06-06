from __future__ import annotations

import html
import logging
import platform
import re
import urllib.request
from pathlib import Path
from typing import Optional

from app.core.configmanager import config

BETA_KEY_URL = "https://forum.makemkv.com/forum/viewtopic.php?t=1053"
KEY_RE = re.compile(r"\bT-[A-Za-z0-9_@-]{40,}\b")


class BetaKeyError(RuntimeError):
    pass


def _settings_path() -> Path:
    system = platform.system()
    if system == "Darwin":
        return Path("~/Library/MakeMKV/settings.conf").expanduser()
    if system == "Windows":
        import os

        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "MakeMKV" / "settings.conf"
    return Path("~/.MakeMKV/settings.conf").expanduser()


def fetch_latest_beta_key(url: str = BETA_KEY_URL, timeout: int = 15) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "TKAutoRipper beta-key fetcher (+https://github.com/TKtheDEV/TKAutoRipper)"
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        raise BetaKeyError(f"Could not fetch MakeMKV beta key page: {exc}") from exc

    body = html.unescape(body)

    code_blocks = re.findall(r"<code[^>]*>(.*?)</code>", body, flags=re.I | re.S)
    for block in code_blocks:
        match = KEY_RE.search(re.sub(r"<[^>]+>", "", block))
        if match:
            return match.group(0)

    match = KEY_RE.search(body)
    if match:
        return match.group(0)

    raise BetaKeyError("No MakeMKV beta key found on the official forum page")


def write_makemkv_app_key(key: str, settings_path: Optional[Path] = None) -> Path:
    path = settings_path or _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    if path.exists():
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()

    key_line = f'app_Key = "{key}"'
    replaced = False
    next_lines = []
    for line in lines:
        if re.match(r"\s*app_Key\s*=", line):
            if not replaced:
                next_lines.append(key_line)
                replaced = True
            continue
        next_lines.append(line)

    if not replaced:
        next_lines.append(key_line)

    path.write_text("\n".join(next_lines) + "\n", encoding="utf-8")
    return path


def refresh_beta_key_if_enabled(force: bool = False) -> Optional[str]:
    enabled = bool(config.get("General", "makemkvautobetakeyrenewal"))
    if not enabled and not force:
        return None

    key = fetch_latest_beta_key()
    config.set("General", "makemkvlicensekey", key)
    config.save()
    settings_path = write_makemkv_app_key(key)
    logging.info("Updated MakeMKV beta key from official forum into %s", settings_path)
    return key
