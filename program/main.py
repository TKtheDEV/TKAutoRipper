import time
from utils import get_available_drives, detect_media_type, load_config
from cd import rip_cd
from dvd import rip_dvd
from bluray import rip_bluray

ongoing_jobs = {}

def poll_for_disks(config):
    while True:
        drives = get_available_drives()
        for drive in drives:
            # Check if a ripping job is already in progress for this drive
            if ongoing_jobs.get(drive, False):
                continue  # Skip if a job is ongoing

            media_type = detect_media_type(drive)
            if media_type == "CD":
                process = rip_cd(drive, config)
                ongoing_jobs[drive] = process  # Track the process
            elif media_type == "DVD":
                process = rip_dvd(drive, config)
                ongoing_jobs[drive] = process
            elif media_type == "BLURAY":
                process = rip_bluray(drive, config)
                ongoing_jobs[drive] = process
            else:
                print(f"No media detected in drive: {drive}")

        time.sleep(10)  # Poll every 10 seconds (adjust this as needed)


if __name__ == '__main__':
    config = load_config('~/TKAutoRipper/config/TKAutoRipper.conf')
    poll_for_disks(config)
