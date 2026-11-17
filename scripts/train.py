#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
from backend.ml import train_stage

parser = argparse.ArgumentParser(description="Train SPRAM LR, RF, XGBoost candidates with calibration")
parser.add_argument("--stage", choices=["intake", "academic_update", "all"], default="all")
parser.add_argument("--dataset", default=str(ROOT.parent / "data.csv"))
parser.add_argument("--artifacts", default=str(ROOT / "artifacts"))
parser.add_argument("--quick", action="store_true")
args = parser.parse_args()
stages = ["intake", "academic_update"] if args.stage == "all" else [args.stage]
for stage in stages:
    result = train_stage(args.dataset, stage, args.artifacts, args.quick)
    print(json.dumps({"stage": stage, "version": result["version"], "algorithm": result["metrics"]["champion_algorithm"], "path": result["path"]}))
