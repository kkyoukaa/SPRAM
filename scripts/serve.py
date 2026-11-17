#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1]))
from backend.app import create_app

create_app().run(host="0.0.0.0", port=5000)
