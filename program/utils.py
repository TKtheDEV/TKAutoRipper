import configparser
import logging
import os
import subprocess

class ConfigLoader:
    _cached_config = None  # Static variable for caching config in memory

    def __init__(self, config_file):
        self.config_file = os.path.expanduser(config_file)
        self._config = ConfigLoader._load_config(self.config_file)

    @staticmethod
    def _load_config(config_file):
        """Load the configuration file and cache it if not already cached."""
        if ConfigLoader._cached_config is None:
            config = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
            if not os.path.exists(config_file):
                raise FileNotFoundError(f"Configuration file '{config_file}' not found.")
            config.read(config_file)
            ConfigLoader._cached_config = config
        return ConfigLoader._cached_config

    def get(self, section, option, fallback=None):
        """Get a configuration option with optional fallback."""
        try:
            return self._config.get(section, option)
        except (configparser.NoSectionError, configparser.NoOptionError):
            if fallback is not None:
                logging.warning(f"Missing '{option}' in section '{section}', using fallback: {fallback}")
                return fallback
            raise

    def save(self):
        """Save the cached configuration back to the file."""
        with open(self.config_file, 'w') as configfile:
            self._config.write(configfile)

    def get_general_settings(self):
        """Fetch general settings, using environment variable for sensitive info if available."""
        return {
            'OutputDirectory': self._config.get('General', 'OutputDirectory'),
            'TempDirectory': self._config.get('General', 'TempDirectory'),
            'MakeMKVLicenseKey': os.getenv("MAKEMKV_LICENSE_KEY", self._config.get('General', 'MakeMKVLicenseKey'))
        }

    def get_cd_config(self):
        """Retrieve CD ripping configuration from the config file."""
        try:
            cd_config = {
                'cdoutputdirectory': self._config.get('CD', 'OutputDirectory'),
                'cdoutputformat': self._config.get('CD', 'OutputFormat'),
                'cdconfigpath': self._config.get('CD', 'ConfigPath'),
                'cdadditionaloptions': self._config.get('CD', 'AdditionalOptions', fallback='')
            }
            return cd_config
        except (configparser.NoSectionError, configparser.NoOptionError) as e:
            logging.error(f"Missing CD configuration option: {e}")
            raise



def check_hardware_encoders():
    """Check if NVENC, QSV, or VCE hardware encoders are available in HandBrake."""
    try:
        # Run HandBrakeCLI help command and capture the output
        result = subprocess.run(["HandBrakeCLI", "-h"], capture_output=True, text=True)
        output = result.stdout.splitlines()

        # Match lines that contain 'nvenc_', 'qsv_', or 'vce_' as a substring
        encoders = {
            "nvenc": [line.strip() for line in output if "nvenc_" in line],
            "qsv": [line.strip() for line in output if "qsv_" in line],
            "vce": [line.strip() for line in output if "vce_" in line],
        }
        
        # Determine if each encoder type is supported based on the presence of matching lines
        encoder_status = {
            "nvenc_supported": bool(encoders["nvenc"]),
            "qsv_supported": bool(encoders["qsv"]),
            "vce_supported": bool(encoders["vce"]),
            "encoders": encoders,
        }

        return encoder_status
    except subprocess.CalledProcessError:
        # Return empty results if an error occurs (e.g., if HandBrakeCLI isn't installed)
        return {
            "nvenc_supported": False,
            "qsv_supported": False,
            "vce_supported": False,
            "encoders": {
                "nvenc": [],
                "qsv": [],
                "vce": []
            }
        }
