import subprocess

def get_available_drives():
    # Use lsblk to detect optical drives
    result = subprocess.run(['lsblk', '-rno', 'NAME,TYPE'], stdout=subprocess.PIPE, text=True)
    drives = []
    for line in result.stdout.splitlines():
        name, type_ = line.split()
        if type_ == 'rom':  # Optical drive type is 'rom'
            drives.append(f"/dev/{name}")
    return drives

def filter_drives(available_drives, config):
    # Filter drives based on the blacklist in the config
    blacklist = config['Drives'].get('Blacklist', '').split(',')
    filtered_drives = [drive for drive in available_drives if drive not in blacklist]
    return filtered_drives
