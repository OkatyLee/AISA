import logging
from pathlib import Path
from typing import Optional


def setup_logger(
    name: str = "default_logger",
    log_file: Optional[str] = None,
    level: int = logging.INFO,
    format_str: Optional[str] = None,
    console_output: bool = True
) -> logging.Logger:
    """
    
    Args:
        name: Name of the logger
        log_file: Path to the log file (if None, logs are not written to a file)
        level: Logging level
        format_str: Log message format
        console_output: Whether to output logs to the console

    Returns:
        Configured logger
    """
    if format_str is None:
        format_str = '[%(asctime)s] %(name)s - %(levelname)s - %(message)s'
    
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    logger.handlers.clear()
    
    formatter = logging.Formatter(format_str)
    
    if console_output:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    logger.info(f"Logger '{name}' initialized with level {logging.getLevelName(level)}")
    
    return logger