import os

def get_connected_drives():
    """Detect connected drives. This can be extended to detect more specific drive types."""
    drives = []
    for drive in os.listdir('/dev'):
        if drive.startswith('sr'):  # CD/DVD drives typically appear as 'sr0', 'sr1', etc.
            drives.append(f"/dev/{drive}")
    return drives
