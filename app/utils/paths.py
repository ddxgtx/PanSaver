import os
import sys
from pathlib import Path

def get_data_dir() -> Path:
    """Get the data storage directory based on the environment and platform."""
    # Check if running in Docker or forced server mode
    if os.path.exists('/.dockerenv') or os.environ.get('PANSAVE_MODE') == 'server':
        data_dir = Path('./data')
    else:
        # Desktop Mode
        if sys.platform == 'win32':
            appdata = os.environ.get('APPDATA')
            if appdata:
                data_dir = Path(appdata) / 'PanSave'
            else:
                data_dir = Path.home() / 'AppData' / 'Roaming' / 'PanSave'
        elif sys.platform == 'darwin':
            data_dir = Path.home() / 'Library' / 'Application Support' / 'PanSave'
        else:
            # Linux server fallback
            data_dir = Path('./data')
            
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir.resolve()

def get_log_dir() -> Path:
    """Get the log storage directory."""
    if os.path.exists('/.dockerenv') or os.environ.get('PANSAVE_MODE') == 'server':
        log_dir = Path('./logs')
    else:
        log_dir = get_data_dir() / 'logs'
        
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir.resolve()
