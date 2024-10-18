import subprocess
import os

def rip_cd(drive, config):
    # Ensure the 'CD' section exists in the config
    if 'CD' in config:
        cdconfigpath = os.path.expanduser(config['CD'].get('ConfigPath', ''))  # Path to abcde.conf
        cdoutputformat = config['CD'].get('OutputFormat', '')  # Output format
        cdadditionaloptions = config['CD'].get('AdditionalOptions', '')  # Additional abcde options
    else:
        print("ERROR READING TKAutoRipper.conf!")
        return 1

    # Ensure the abcde configuration file exists
    if not os.path.exists(cdconfigpath):
        print(f"Error: abcde config file not found at {cdconfigpath}")
        return

    # Build the abcde command
    start_abcde = f"abcde -d {drive} -c {cdconfigpath} -o {cdoutputformat} -N -x {cdadditionaloptions}"

    try:
        # Execute the abcde ripping process in the background
        #process = subprocess.Popen(start_abcde)
        process = subprocess.Popen(start_abcde, shell=True)
        print(f"CD ripping started on {drive} using abcde...")
        return process  # Return the process handle if needed for tracking
    except Exception as e:
        print(f"Error: CD ripping failed on {drive}. {e}")
