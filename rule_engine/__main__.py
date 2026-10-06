"""CLI: python -m rule_engine RULES_FILE FACTS_FILE [options]"""

import argparse
import json
import sys

from .engine import RuleEngine
from .errors import RuleEngineError
from .loader import load_facts, load_rules
from .validation import validate_rules


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="rule_engine",
        description="Local JSON/YAML business rule engine",
    )
    parser.add_argument("rules", help="rules file (JSON or YAML)")
    parser.add_argument("facts", nargs="?", help="facts file (JSON or YAML)")
    parser.add_argument("--max-steps", type=int, default=1000,
                        help="maximum number of rule firings (default: 1000)")
    parser.add_argument("--validate-only", action="store_true",
                        help="only run static validation on the rules file")
    parser.add_argument("--trace-out", help="write execution trace JSON here")
    parser.add_argument("--facts-out", help="write final facts JSON here")
    args = parser.parse_args(argv)

    try:
        rules = load_rules(args.rules)
        validate_rules(rules)
        if args.validate_only:
            print(f"OK: {len(rules)} rule(s) valid")
            return 0
        if not args.facts:
            parser.error("facts file is required unless --validate-only")
        facts = load_facts(args.facts)
        result = RuleEngine(rules, max_steps=args.max_steps).run(facts)
    except RuleEngineError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    output = {
        "status": result.status,
        "steps": result.steps,
        "fired_rules": result.fired_rules,
        "cycle_candidates": result.cycle_candidates,
        "facts": result.facts,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    if args.trace_out:
        with open(args.trace_out, "w", encoding="utf-8") as fh:
            json.dump(result.trace, fh, indent=2, ensure_ascii=False)
    if args.facts_out:
        with open(args.facts_out, "w", encoding="utf-8") as fh:
            json.dump(result.facts, fh, indent=2, ensure_ascii=False)
    return 0 if result.ok else 2


if __name__ == "__main__":
    sys.exit(main())
