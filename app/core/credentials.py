from pathlib import Path

from app.core.configmanager import ConfigManager, config

credentials_path = Path("~/TKAutoRipper/config/credentials.conf")
credentials_default_path = Path(__file__).resolve().parents[2] / "config" / "credentials.example.conf"
credentials = ConfigManager(credentials_path, default_path=credentials_default_path)
credentials.load()


def migrate_legacy_credentials() -> None:
    general = config._config_raw.get("General", {})
    legacy = general.get("omdbapikey")
    if legacy:
        legacy_value = legacy.get("value")
        if legacy_value and not credentials.get("Credentials", "omdbapikey"):
            credentials.set("Credentials", "omdbapikey", legacy_value)
            credentials.save()
        del general["omdbapikey"]
        config._flatten_config()
        config.save()


migrate_legacy_credentials()
