# configmanager.py
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


class ConfigManager:
    def __init__(self, config_path: Path, default_path: Optional[Path] = None):
        self.config_path = config_path.expanduser()
        self.default_path = default_path
        self._config_raw: Dict[str, Any] = {}
        self._config_flat: Dict[str, Any] = {}

    def load(self):
        if not self.config_path.exists() and self.default_path and self.default_path.exists():
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text(
                self.default_path.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        with open(self.config_path, 'r') as f:
            self._config_raw = yaml.safe_load(f) or {}
        self._merge_default_config()
        self._flatten_config()

    def _merge_default_config(self):
        default_path = self.default_path or Path(__file__).resolve().parents[2] / "config" / "TKAutoRipper.conf"
        if default_path == self.config_path or not default_path.exists():
            return
        try:
            with open(default_path, "r", encoding="utf-8") as f:
                defaults = yaml.safe_load(f) or {}
        except Exception:
            return
        changed = False
        for section, entries in defaults.items():
            if section not in self._config_raw:
                self._config_raw[section] = entries
                changed = True
                continue
            for key, entry in entries.items():
                if key not in self._config_raw[section]:
                    self._config_raw[section][key] = entry
                    changed = True
        if changed:
            self.save()

    def _flatten_config(self):
        flat = {}
        for section, entries in self._config_raw.items():
            flat[section] = {}
            for key, entry in entries.items():
                value = entry.get("value")
                if isinstance(value, str) and value.startswith("~/"):
                    value = str(Path(value).expanduser())
                flat[section][key] = value
        self._config_flat = flat

    def get(self, section: str, key: str) -> Any:
        return self._config_flat.get(section, {}).get(key)

    def set(self, section: str, key: str, value: Any):
        if section in self._config_raw and key in self._config_raw[section]:
            self._config_raw[section][key]["value"] = value
            self._flatten_config()
        else:
            raise KeyError(f"{section}.{key} not found in config")

    def save(self):
        from collections import OrderedDict
        import yaml

        class OrderedDumper(yaml.SafeDumper):
            pass

        def _dict_representer(dumper, data):
            return dumper.represent_dict(data.items())

        OrderedDumper.add_representer(OrderedDict, _dict_representer)

        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(self._config_raw, f, Dumper=OrderedDumper, sort_keys=False)

    def section(self, section: str) -> Dict[str, Any]:
        return self._config_flat.get(section, {})

    @property
    def all(self) -> Dict[str, Dict[str, Any]]:
        return self._config_flat

config_path = Path("~/TKAutoRipper/config/TKAutoRipper.conf")
config = ConfigManager(config_path)
config.load()
