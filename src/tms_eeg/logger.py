"""
Toggleable logging utility for the TMS-EEG project.
"""
from tms_eeg import config

def log(message, level="INFO"):
    """
    Print the message only if ENABLE_LOGGING is set to True in config.
    
    Parameters
    ----------
    message : str
        The message to print.
    level : str
        The log level/prefix (e.g., INFO, DEBUG, ERROR).
    """
    if getattr(config, "ENABLE_LOGGING", False):
        print(f"[{level}] {message}")
