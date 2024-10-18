import configparser
from utils import get_available_drives, filter_drives
from cd import rip_cd
from dvd import rip_dvd
from bluray import rip_bluray
from web_ui import start_web_ui


def load_config():
    config_path = "~/TKAutoRipper/config/TKAutoRipper.conf"
    config = configparser.ConfigParser()
    config.read(config_path)
    return config


def main():
    # Load the configuration
    config = load_config()

    # Get the list of available drives
    available_drives = get_available_drives()
    filtered_drives = filter_drives(available_drives, config)
    
    print(f"Drives after applying blacklist: {filtered_drives}")

    # Start Web UI in background
    start_web_ui()

    # Example logic: choose drive and media type
    for drive in filtered_drives:
        media_type = "DVD"  # Example logic, should implement media detection
        if media_type == "CD":
            rip_cd(drive, config)
        elif media_type == "DVD":
            rip_dvd(drive, config)
        elif media_type == "BLURAY":
            rip_bluray(drive, config)

if __name__ == "__main__":
    main()
