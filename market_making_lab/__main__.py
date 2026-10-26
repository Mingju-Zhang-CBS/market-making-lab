import argparse
import json
from pathlib import Path
from .core import run_demo


def main():
    parser = argparse.ArgumentParser(description="Independent offline market-making demonstration")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--demand-study", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("local-runs/demo"))
    args = parser.parse_args()
    if args.demand_study:
        from .demand_study import run
        result = run(args.output)
    else:
        result = run_demo(args.output)
    print(json.dumps({key: value for key, value in result.items() if key != "comparison"}, indent=2))


if __name__ == "__main__":
    main()
