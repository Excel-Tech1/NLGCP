"""Run corrected real-data CLI stages and retain command/exit evidence.

Requires the documented external enclave and RTKLIB. Does not remove history.
Use --vrs after the reviewed Phase 6 derive/fit/validate commands complete.
"""

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
logs = repo / "build/scientific-validation/logs"
logs.mkdir(parents=True, exist_ok=True)
root = Path(os.environ.get("NLGCP_DATA_ROOT", "/home/excellence/nlgcp-data"))
env = dict(os.environ, NLGCP_DATA_ROOT=str(root), RTKLIB_SOURCE="/home/excellence/RTKLIB")
parser = argparse.ArgumentParser()
parser.add_argument("--vrs", action="store_true")
args = parser.parse_args()
records = []


def run(script, stage, definition=None, label=None):
    cmd = [str(repo / ".venv/bin/python"), str(repo / "scripts" / script), stage]
    if definition:
        cmd.extend(
            ["--definition", str(repo / "research/scientific_validation/config" / definition)]
        )
    name = label or stage
    start = time.monotonic()
    result = subprocess.run(cmd, cwd=repo, env=env, text=True, capture_output=True)
    (logs / (name + ".json")).write_text(result.stdout)
    (logs / (name + ".err")).write_text(result.stderr)
    row = {
        "command": cmd,
        "returncode": result.returncode,
        "duration_s": time.monotonic() - start,
        "stdout": str((logs / (name + ".json")).relative_to(repo)),
    }
    records.append(row)
    (logs / "regeneration-commands.json").write_text(json.dumps(records, indent=2) + "\n")
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    payload = json.loads(result.stdout)
    if payload.get("status") == "BLOCKED":
        raise RuntimeError(result.stdout)
    print(name, payload.get("status", payload.get("execution_status")), flush=True)
    return payload


if args.vrs:
    # Preserve the previous cross-experiment summary before the CLI refresh.
    old = root / "processed/atmospheric-model/summaries"
    snapshot = repo / "research/scientific_validation/evidence/historical-summaries"
    snapshot.mkdir(exist_ok=True)
    for p in old.glob("*.csv"):
        dest = snapshot / p.name
        if not dest.exists():
            dest.write_bytes(p.read_bytes())
    run("run_atmospheric_model.py", "summarize", label="phase6-summarize")
    for station in ("phri", "abfc", "ekak", "mgbo"):
        for stage in ("generate", "validate", "summarize"):
            run("run_vrs_generator.py", stage, station + "-geometry-v3.json", station + "-" + stage)
    resume = run("run_vrs_generator.py", "generate", "phri-geometry-v3.json", "phri-resume")
    assert resume["reused"] is True
else:
    for stage in ("inspect", "plan", "derive", "fit", "validate"):
        run("run_atmospheric_model.py", stage, "phase6-geometry-v3.json", "phase6-" + stage)
