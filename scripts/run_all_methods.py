"""
Run all gender classification methods on data/input/schleiermacher_persons.csv.

Each method is run in a subprocess using a wrapper that:
- Sets PYTHONUTF8=1 to handle Unicode output on Windows
- Removes the methods/ directory from sys.path to avoid shadowing installed packages

Usage (run from project root):
    python scripts/run_all_methods.py
    python scripts/run_all_methods.py --skip llm          # skip slow LLM method
    python scripts/run_all_methods.py --only gender_guesser gnd_local_lookup
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# Order: fast deterministic methods first, slow ML/LLM methods last
METHODS = [
    "gender_guesser",
    "gnd_local_lookup",
    "nonquamgender",
    "wiki_gendersort",
    "hivoto",
    "hivoto_xgboost",
    "hf_genderize",
    "hf_gender_classification",
    "llm",
]

# Wrapper that fixes sys.path before executing the method script.
# Also sets __file__ so scripts that use Path(__file__) work correctly.
WRAPPER = """\
import sys, pathlib
methods_dir = str(pathlib.Path({script!r}).parent.resolve())
sys.path = [p for p in sys.path if pathlib.Path(p).resolve() != pathlib.Path(methods_dir)]
exec(open({script!r}, encoding='utf-8').read(), {{'__name__': '__main__', '__file__': {script!r}}})
"""


def run_method(name: str) -> bool:
    script = PROJECT_ROOT / "methods" / f"{name}.py"
    if not script.exists():
        print(f"  [SKIP] {script} not found")
        return False

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"

    code = WRAPPER.format(script=str(script).replace("\\", "/"))

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(PROJECT_ROOT),
        env=env,
    )
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip", nargs="+", default=[], metavar="METHOD",
                        help="Methods to skip")
    parser.add_argument("--only", nargs="+", default=[], metavar="METHOD",
                        help="Run only these methods")
    args = parser.parse_args()

    methods = args.only if args.only else METHODS
    methods = [m for m in methods if m not in args.skip]

    print(f"Running {len(methods)} method(s): {', '.join(methods)}")
    print("=" * 60)

    results = {}
    for name in methods:
        print(f"\n>>> {name}")
        print("-" * 40)
        ok = run_method(name)
        results[name] = "OK" if ok else "FAILED"

    print("\n" + "=" * 60)
    print("Summary:")
    for name, status in results.items():
        mark = "+" if status == "OK" else "x"
        print(f"  [{mark}] {name:<30} {status}")


if __name__ == "__main__":
    main()
