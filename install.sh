#!/bin/bash

# Function to exit on error after echo
error_exit() {
    echo "$1" 1>&2
    exit 1
}

# Install system dependencies
echo -e "\nInstalling system dependencies..."
sudo apt update && sudo apt install -y abcde flac git handbrake-cli python3 python3-venv || error_exit "Failed to install dependencies!"

# Clone the repository
echo -e "\nCloning the TKAutoRipper repository..."
git clone https://github.com/TKtheDEV/TKAutoRipper.git ~/TKAutoRipper || error_exit "Failed to clone repository!"

# Set up directories
echo -e "\nSetting up directory structure..."
mkdir -p ~/TKAutoRipper/temp/CD ~/TKAutoRipper/output/CD ~/TKAutoRipper/output/DVD ~/TKAutoRipper/output/BLURAY

# Set up Python virtual environment
echo -e "\nSetting up Python environment..."
cd ~/TKAutoRipper/program
python3 -m venv venv
source venv/bin/activate
echo "# Activate TKAutoRipper environment" >> ~/.bashrc
echo "source ~/TKAutoRipper/program/venv/bin/activate" >> ~/.bashrc
pip install -r requirements.txt

# Check for MakeMKV installation
if ! command -v makemkvcon &> /dev/null; then
    echo -e "\nMakeMKV is not installed. Please install MakeMKV manually from:\nhttps://forum.makemkv.com/forum/viewtopic.php?f=3&t=224."
    echo -e "After installing MakeMKV, TKAutoRipper will be ready to use."
else
    echo -e "\nTKAutoRipper installation completed successfully. Ready to rip!"
fi
