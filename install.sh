#!/bin/bash

# Install system dependencies
echo -e "\nInstalling system dependencies..."
sudo apt update
sudo apt install -y abcde flac handbrake-cli python3 python3-venv

# Clone the repository
echo -e "\nCloning the TKAutoRipper repository..."
git clone https://github.com/TKtheDEV/TKAutoRipper.git ~/TKAutoRipper

# Set up directories
echo -e "\nSetting up directory structure..."
mkdir -p ~/TKAutoRipper/Temp ~/TKAutoRipper/Output/Music ~/TKAutoRipper/Output/Movies ~/TKAutoRipper/Output/Shows

# Set up Python virtual environment
echo -e "\nSetting up Python environment..."
cd ~/TKAutoRipper/Program
python3 -m venv venv
source venv/bin/activate
pip install flask

# Finish setup
echo -e "\nTKAutoRipper installation completed!"
# Prompt user to install MakeMKV manually
echo -e "\nMakeMKV cannot be installed by this script!"
echo -e "Please install MakeMKV manually from:\nhttps://forum.makemkv.com/forum/viewtopic.php?f=3&t=224."