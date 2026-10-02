"""Command-line interface: python3 -m sat_solver <file.cnf>"""

import sys

from . import DPLLSolver, DimacsError, parse_dimacs, verify


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: python3 -m sat_solver <file.cnf>", file=sys.stderr)
        return 2
    path = argv[0]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        return 2
    try:
        num_vars, clauses = parse_dimacs(text)
    except DimacsError as exc:
        print(f"error: invalid DIMACS input: {exc}", file=sys.stderr)
        return 2

    solver = DPLLSolver(num_vars, clauses)
    model = solver.solve()
    stats = solver.stats

    if model is None:
        print("UNSAT")
    else:
        print("SAT")
        assert verify(clauses, model), "internal error: model does not verify"
        assignment = " ".join(
            str(var if model[var] else -var) for var in range(1, num_vars + 1)
        )
        print(f"v {assignment} 0" if assignment else "v 0")
    print(
        f"stats: propagations={stats.propagations} "
        f"pure_literals={stats.pure_literals} "
        f"decisions={stats.decisions} backtracks={stats.backtracks}"
    )
    return 0 if model is not None else 1


if __name__ == "__main__":
    sys.exit(main())
