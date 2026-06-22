"""Run from promptfoo/ folder: python scripts/generate_conversation_eval_cases.py"""
import runpy
from pathlib import Path

runpy.run_path(
    str(Path(__file__).resolve().parent.parent.parent / "scripts" / "generate_conversation_eval_cases.py"),
    run_name="__main__",
)
