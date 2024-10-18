import os
import subprocess

def rip_dvd(drive, config):
    temp_dir = config['General']['TempDirectory']
    makemkv_output = os.path.join(temp_dir, 'makemkv')
    os.makedirs(makemkv_output, exist_ok=True)

    # Run MakeMKV to rip DVD
    makemkv_command = f"makemkvcon mkv dev:{drive} all {makemkv_output}"
    subprocess.run(makemkv_command, shell=True)
    print(f"DVD ripped to {makemkv_output}")
    
    # Run HandBrake to transcode
    handbrake_preset = config['Video']['HandBrakePresetDVD']
    handbrake_output = os.path.join(config['General']['OutputDirectory'], 'output.mp4')
    handbrake_command = f"HandBrakeCLI -i {makemkv_output} -o {handbrake_output} --preset {handbrake_preset}"
    subprocess.run(handbrake_command, shell=True)
    print(f"DVD transcoded and saved to {handbrake_output}")
