import logging
import os
import subprocess
from utils import ConfigLoader

class BluRayRipper:
    def __init__(self, drive, config_file, job_tracker):
        self.drive = drive
        self.job_tracker = job_tracker
        self.config_loader = ConfigLoader(config_file)
        self.general_settings = self.config_loader.get_general_settings()

    def get_disc_number(self):
        # Scan for available drives and detect the Blu-ray drive number
        # This assumes that makemkvcon detects drives as 'disc:N' where N is the index
        cmd = f"makemkvcon -r info disc:9999"  # High number to list all discs
        output = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        # Parse the output to find the disc number for the drive
        for line in output.stdout.splitlines():
            if f"/dev/{self.drive}" in line:
                return line.split(':')[1]  # Extracts the disc number

        raise RuntimeError("Blu-ray disc not found")

    def rip_bluray(self):
        disc_number = self.get_disc_number()
        output_dir = os.path.join(self.general_settings['TempDirectory'], "blu_ray")
        os.makedirs(output_dir, exist_ok=True)

        cmd = f"makemkvcon mkv disc:{disc_number} all {output_dir}"
        self.job_tracker.add_job(self.drive, disc_number, "Ripping Blu-ray in progress")
        self.run_makemkv(cmd)

    def run_makemkv(self, cmd):
        try:
            process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            logs = []

            for line in process.stdout:
                logs.append(line.strip())
                if len(logs) > 15:  # Keep only the last 15 lines
                    logs = logs[-15:]
                self.job_tracker.update_job(self.drive, "Ripping Blu-ray in progress", logs=logs)

            process.wait()
            if process.returncode == 0:
                self.job_tracker.update_job(self.drive, "Ripping Blu-ray completed", logs=logs)
            else:
                error_log = process.stderr.read().strip()
                logs.append(f"Error: {error_log}")
                self.job_tracker.update_job(self.drive, "Ripping Blu-ray failed", logs=logs)
        except Exception as e:
            logs.append(f"Error: {str(e)}")
            self.job_tracker.update_job(self.drive, "Ripping Blu-ray failed", logs=logs)

    def encode_bluray(self, preset_file):
        input_file = f"{self.general_settings['TempDirectory']}/blu_ray/mainfeature.mkv"
        output_file = os.path.join(self.general_settings['OutputDirectory'], "encoded_bluray.mp4")

        cmd = f"HandBrakeCLI -i {input_file} -o {output_file} --preset-import-file {preset_file} --preset '1080pNvEncAV1'"
        try:
            subprocess.run(cmd, shell=True, check=True)
            logging.info("HandBrake encoding completed successfully.")
            self.job_tracker.update_job(self.drive, "Encoding completed", logs=["Encoding completed successfully."])
        except subprocess.CalledProcessError as e:
            error_log = f"Encoding failed: {str(e)}"
            logging.error(error_log)
            self.job_tracker.update_job(self.drive, "Encoding failed", logs=[error_log])
