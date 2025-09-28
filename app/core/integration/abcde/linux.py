from typing import List


def run_abcde(
    drive_path: str,
    output_format: str,
    config_path: str,
    additional_options: str
) -> List[str]:
    """
    Constructs the abcde command for ripping an audio CD.

    :param drive_path: The device path (e.g., /dev/sr1)
    :param output_format: Audio format like 'flac', 'mp3', etc.
    :param config_path: Path to abcde configuration file
    :param additional_options: Additional CLI options as a string
    :return: List of strings representing the command to run
    """
    additional_args = additional_options.split() if additional_options else []

    command = [
        "abcde",
        "-d", drive_path,
        "-o", output_format,
        "-c", config_path,
        "-N",
        *additional_args
    ]
    return command
