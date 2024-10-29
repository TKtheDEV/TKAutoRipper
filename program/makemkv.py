import logging
import os
import subprocess

from utils import ConfigLoader

class MakeMKVRipper:
    def __init__(self, drive, config_file):
        self.drive = drive
        self.config_loader = ConfigLoader(config_file)
        self.general_settings = self.config_loader.get_general_settings()

    def rip_disc(self):
        mode = self.auto_detect_mode()
        output_dir = os.path.join(self.general_settings['TempDirectory'], mode)
        os.makedirs(output_dir, exist_ok=True)

        cmd = f"makemkvcon mkv disc:{self.get_disc_number()} mainfeature {output_dir}"
        self.run_makemkv(cmd)

    def run_makemkv(self, cmd):
        try:
            subprocess.run(cmd, shell=True, check=True)
            logging.info("MakeMKV completed successfully.")
        except subprocess.CalledProcessError as e:
            logging.error(f"MakeMKV encountered an error: {e}")
            raise RuntimeError("MakeMKV command failed")
