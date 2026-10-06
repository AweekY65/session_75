"""命令行入口：python -m rule_engine rules.yaml facts.json"""

import argparse
import sys

from .engine import result_to_json, run_engine
from .errors import RuleEngineError
from .loader import load_facts, load_rules


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="rule_engine",
        description="本地规则引擎：加载 JSON/YAML 规则与 facts 并执行",
    )
    parser.add_argument("rules", help="规则文件（JSON/YAML）")
    parser.add_argument("facts", help="facts 文件（JSON/YAML）")
    parser.add_argument("--max-steps", type=int, default=1000, help="最大执行步数（默认 1000）")
    parser.add_argument("-o", "--output", help="将执行结果（含 trace）写入本地 JSON 文件")
    args = parser.parse_args(argv)

    try:
        rules = load_rules(args.rules)
        facts = load_facts(args.facts)
    except RuleEngineError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    result = run_engine(rules, facts, max_steps=args.max_steps)
    payload = result_to_json(result)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(payload + "\n")
    print(payload)
    return 0 if result.status == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
