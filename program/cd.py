import subprocess
import os
from utils import ConfigLoader
from job_tracker import job_tracker  # In both api.py and cd.py

class CDRipper:
    def __init__(self, config_file, drive):
        # Initialize configuration and drive
        self.drive = drive
        self.config_loader = ConfigLoader(config_file)
        self.cd_config = self.config_loader.get_cd_config()

    def rip_cd(self):
        """Run the abcde command to rip a CD and capture output in real-time."""
        output_dir = os.path.expanduser(self.cd_config['cdoutputdirectory'])
        output_format = self.cd_config['cdoutputformat']
        config_path = os.path.expanduser(self.cd_config['cdconfigpath'])
        additional_options = self.cd_config['cdadditionaloptions']

        # Ensure the output directory exists
        os.makedirs(output_dir, exist_ok=True)

        # Construct the drive path and the abcde command
        drive_path = f"/dev/{self.drive}"
        cmd = f"abcde -d {drive_path} -c {config_path} -o {output_format} -N -f -x {additional_options}"

        # Log the command for debugging
        print(f"Running command: {cmd}")

        logs = []  # List to store logs
        try:
            process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            # Read stdout line by line
            for line in process.stdout:
                print(line.strip())  # Print to console
                logs.append(line.strip())  # Append to logs

                # Update the logs in job tracker
                job_tracker.update_job(self.drive, "Ripping CD in progress", logs=logs)

            # Wait for the process to finish
            process.wait()

            # Handle process completion
            if process.returncode == 0:
                print("Ripping completed successfully.")
                job_tracker.update_job(self.drive, "Ripping CD completed", logs=logs)
            else:
                error_log = process.stderr.read().strip()
                print(f"Ripping failed: {error_log}")
                logs.append(f"Error: {error_log}")
                job_tracker.update_job(self.drive, "Ripping CD failed", logs=logs)

        except Exception as e:
            error_msg = f"Error during ripping: {str(e)}"
            print(error_msg)
            logs.append(error_msg)
            job_tracker.update_job(self.drive, "Ripping CD failed", logs=logs)
