"""
Shared utilities for SmartTrader-AI
"""

import json
import os
from datetime import datetime
from colorama import Fore, Style, init

init(autoreset=True)

CONFIG_FILE = "config.json"
LOG_FILE = "logs/smarttrader.log"


def load_config():
    """Load configuration from config.json"""
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except Exception as e:
        print(f"{Fore.RED}ERROR loading config: {e}")
        return {}


def save_config(config):
    """Save configuration to config.json"""
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"{Fore.RED}ERROR saving config: {e}")


def log(message, level="INFO", color=None):
    """Log message to console and file"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] [{level}] {message}"

    # Console color
    if color:
        print(color + log_line + Style.RESET_ALL)
    elif level == "ERROR":
        print(Fore.RED + log_line)
    elif level == "SUCCESS":
        print(Fore.GREEN + log_line)
    elif level == "WARNING":
        print(Fore.YELLOW + log_line)
    elif level == "INFO":
        print(Fore.CYAN + log_line)
    else:
        print(log_line)

    # Write to log file
    os.makedirs("logs", exist_ok=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(log_line + "\n")
    except Exception:
        pass


def save_json(path, data):
    """Save data to JSON file"""
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def load_json(path, default=None):
    """Load data from JSON file"""
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def pct(value):
    """Format as percentage"""
    return f"{value * 100:.2f}%"


def currency(value):
    """Format as currency"""
    return f"${value:,.2f}"
