import yaml
from pathlib import Path
from typing import Any, Dict


class ConfigManager:
    def __init__(self, config_path: Path):
        self.config_path = config_path.expanduser()
        self._config_raw: Dict[str, Any] = {}
        self._config_flat: Dict[str, Any] = {}

    def load(self):
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        with open(self.config_path, 'r') as f:
            self._config_raw = yaml.safe_load(f)
        self._flatten_config()

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