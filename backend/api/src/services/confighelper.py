from pathlib import Path
from typing import Dict
import yaml
import logging

log = logging.getLogger("protsearch")

def load_config() -> Dict:
    try:
        config_path = Path(__file__).resolve().parents[1] / "config.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        log.warning(f"Error loading config: {e}")
        return {"num_papers": 25, "start_year": 1900}