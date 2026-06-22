"""Run from promptfoo/ folder: python scripts/run_conversation_eval.py"""
import runpy
import sys
from pathlib import Path

# Forward CLI args (e.g. --limit 10, --id en_greet_jaipur_excavator_refine)
sys.argv[0] = str(Path(__file__).resolve().parent.parent.parent / "scripts" / "run_conversation_eval.py")
runpy.run_path(
    str(Path(__file__).resolve().parent.parent.parent / "scripts" / "run_conversation_eval.py"),
    run_name="__main__",
)
