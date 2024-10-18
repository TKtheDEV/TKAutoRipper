# utils.py
import configparser
import os
import subprocess
import sys

def load_config(config_path):
    config = configparser.ConfigParser()
    config_path = os.path.expanduser(config_path)
    config.read(config_path)
    return config

def run_command(command):
    try:
        # Start the command and wait for it to complete
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            print(f"Error running command {command}: {stderr.decode()}")
        else:
            print(f"Command output: {stdout.decode()}")
        return process.returncode, stdout.decode(), stderr.decode()
    except Exception as e:
        print(f"Exception while running command: {str(e)}")
        return -1, '', str(e)

def get_available_drives():
    result = subprocess.run(['lsblk', '-rno', 'NAME,TYPE'], stdout=subprocess.PIPE, text=True)
    drives = []
    for line in result.stdout.splitlines():
        name, type_ = line.split()
        if type_ == 'rom':
            drives.append(f"/dev/{name}")
    return drives

def filter_drives(available_drives, config):
    blacklist = config['Drives'].get('Blacklist', '').split(',')
    return [drive for drive in available_drives if drive not in blacklist]

def detect_media_type(drive):
    """
    Detects the type of media in the given drive (CD, DVD, or Blu-ray).
    Returns "CD", "DVD", "BLURAY", or None if the type cannot be determined.
    """
    try:
        # Use blkid to get information about the drive
        result = subprocess.run(['blkid', '-o', 'value', '-s', 'TYPE', drive],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        filesystem_type = result.stdout.strip()

        # Check if the drive contains a CD
        if filesystem_type == '':
            # Empty string usually indicates an audio CD (no filesystem detected)
            return "CD"

        # Check for DVD or Blu-ray based on the filesystem type
        elif filesystem_type == 'udf':
            # UDF is commonly used for DVDs and Blu-rays
            # Further refinement to distinguish between DVD and Blu-ray can be done by checking size
            # Check the size of the disc using 'lsblk'
            size_result = subprocess.run(['lsblk', '-bno', 'SIZE', drive], stdout=subprocess.PIPE, text=True)
            disc_size = int(size_result.stdout.strip())

            # Blu-rays are typically larger than 25GB, while DVDs are much smaller
            if disc_size > 25 * 1024 * 1024 * 1024:  # 25GB in bytes
                return "BLURAY"
            else:
                return "DVD"
        else:
            return None

    except Exception as e:
        print(f"Error detecting media type in {drive}: {e}")
        return None
