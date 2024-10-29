import logging
import os
import subprocess

from job_tracker import job_tracker
from utils import ConfigLoader

class CDRipper:
    def __init__(self, config_file, drive, job_tracker):
        # Initialize configuration and drive
        self.drive = drive
        self.job_tracker = job_tracker
        self.config_loader = ConfigLoader(config_file)
        self.cd_config = self.config_loader.get_cd_config()

    def rip_cd(self):
        """Run the abcde command to rip a CD and capture output in real-time."""
        output_dir = os.path.expanduser(self.cd_config['cdoutputdirectory'])
        os.makedirs(output_dir, exist_ok=True)
        cmd = f"stdbuf -oL abcde -d /dev/{self.drive} -c {self.cd_config['cdconfigpath']} -o {self.cd_config['cdoutputformat']} -N -f -x {self.cd_config['cdadditionaloptions']}"

        logs = []
        try:
            process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            for line in process.stdout:
                logs.append(line.strip())
                if len(logs) > 15:
                    logs = logs[-15:]
                self.job_tracker.update_job(self.drive, "Ripping CD in progress", logs=logs)

            process.wait()
            if process.returncode == 0:
                self.job_tracker.update_job(self.drive, "Ripping CD completed", logs=logs)
            else:
                error_log = process.stderr.read().strip()
                logs.append(f"Error: {error_log}")
                self.job_tracker.update_job(self.drive, "Ripping CD failed", logs=logs)

        except Exception as e:
            logs.append(f"Error: {str(e)}")
            self.job_tracker.update_job(self.drive, "Ripping CD failed", logs=logs)
