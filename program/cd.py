import subprocess

def rip_cd(drive, config):
    output_dir = config['General']['OutputDirectory']
    format_ = config['Audio']['Format']
    
    # Example abcde command
    abcde_command = f"abcde -d {drive} -o {format_} -N -x -o {output_dir}"
    
    # Execute ripping
    subprocess.run(abcde_command, shell=True)
    print(f"CD ripping started on {drive}...")
