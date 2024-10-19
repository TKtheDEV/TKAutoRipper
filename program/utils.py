import configparser
import os

class ConfigLoader:
    def __init__(self, config_file):
        self.config_file = os.path.expanduser(config_file)
        self.config = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())

        if not os.path.exists(self.config_file):
            raise FileNotFoundError(f"Configuration file '{self.config_file}' not found.")
        
        self.config.read(self.config_file)

    def get(self, section, option, fallback=None):
        """ 
        Get a configuration option from a specific section.
        """
        try:
            return self.config.get(section, option)
        except (configparser.NoSectionError, configparser.NoOptionError):
            if fallback is not None:
                return fallback
            raise

    def get_path(self, section, option, fallback=None):
        """
        Get a path and expand the user's home directory (~).
        """
        try:
            path = self.config.get(section, option)
            return os.path.expanduser(path)
        except (configparser.NoSectionError, configparser.NoOptionError):
            if fallback is not None:
                return os.path.expanduser(fallback)
            raise

    def get_cd_config(self):
        """Get CD ripping configuration from the config file."""
        cd_config = {
            'cdoutputdirectory': self.config.get('CD', 'OutputDirectory'),
            'cdoutputformat': self.config.get('CD', 'OutputFormat'),
            'cdconfigpath': self.config.get('CD', 'ConfigPath'),
            'cdadditionaloptions': self.config.get('CD', 'AdditionalOptions', fallback='')
        }
        return cd_config