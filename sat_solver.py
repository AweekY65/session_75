"""A self-contained local SAT solver based on the DPLL algorithm.

No external SAT libraries (Z3, MiniSat, cloud services) are used; the
core algorithm is implemented from scratch using only the Python
standard library.

Features:
  * DIMACS CNF parsing with strict validation (header, literal ranges,
    clause termination, clause count, end-of-file marker).
  * DPLL with unit propagation, pure literal elimination and a
    DLIS-style variable selection heuristic.
  * Deterministic semantics for empty formulas, empty clauses,
    duplicate literals and tautological clauses.
  * Decision/backtracking statistics (propagations, decisions,
    backtracks).
  * Model verification against the original clauses.

Usage:
    python3 -m sat_solver path/to/formula.cnf
"""

from dataclasses import dataclass, field


class DimacsError(ValueError):
    """Raised when a DIMACS CNF input is malformed."""


@dataclass
class CnfFormula:
    """A parsed CNF formula.

    clauses is a list of frozensets of ints. Normalization applied at
    parse time (deterministic semantics):
      * duplicate literals inside a clause are collapsed,
      * tautological clauses (containing both x and -x) are dropped,
      * an empty clause is kept as an empty frozenset and makes the
        formula trivially UNSAT,
      * an empty clause list is the empty formula, trivially SAT.
    """

    num_vars: int
    clauses: list


@dataclass
class Stats:
    """Search statistics collected during DPLL."""

    propagations: int = 0
    decisions: int = 0
    backtracks: int = 0


@dataclass
class SolveResult:
    """Result of solving a formula.

    satisfiable is True/False; model is a complete assignment
    {var: bool} for every variable 1..num_vars when satisfiable,
    otherwise None. stats holds the search statistics.
    """

    satisfiable: bool
    model: dict = None
    stats: Stats = field(default_factory=Stats)


def _normalize_clause(literals):
    """Collapse duplicates; tautologies become None (dropped by caller)."""
    seen = set()
    for lit in literals:
        if -lit in seen:
            return None  # tautology: always satisfied
        seen.add(lit)
    return frozenset(seen)


def parse_dimacs(text):
    """Parse DIMACS CNF text into a CnfFormula, validating strictly.

    Raises DimacsError on any malformed input.
    """
    num_vars = None
    expected_clauses = None
    clauses = []
    current = []
    header_seen = False
    ended = False

    lines = text.splitlines()
    for lineno, raw in enumerate(lines, start=1):
        line = raw.strip()
        if ended:
            if line:
                raise DimacsError(
                    "line %d: content after end-of-file marker '%%'" % lineno
                )
            continue
        if not line:
            continue
        if line.startswith("c"):
            continue
        if line.startswith("%"):
            ended = True
            continue
        if line.startswith("p"):
            if header_seen:
                raise DimacsError("line %d: duplicate problem line" % lineno)
            tokens = line.split()
            if len(tokens) != 4 or tokens[1] != "cnf":
                raise DimacsError(
                    "line %d: problem line must be 'p cnf <vars> <clauses>'" % lineno
                )
            try:
                num_vars = int(tokens[2])
                expected_clauses = int(tokens[3])
            except ValueError:
                raise DimacsError(
                    "line %d: variable/clause counts must be integers" % lineno
                )
            if num_vars < 0 or expected_clauses < 0:
                raise DimacsError(
                    "line %d: variable/clause counts must be non-negative" % lineno
                )
            header_seen = True
            continue
        if not header_seen:
            raise DimacsError(
                "line %d: clause data before the 'p cnf' problem line" % lineno
            )
        for token in line.split():
            try:
                lit = int(token)
            except ValueError:
                raise DimacsError(
                    "line %d: invalid literal %r" % (lineno, token)
                )
            if lit == 0:
                clauses.append(_normalize_clause(current))
                current = []
            else:
                if abs(lit) > num_vars:
                    raise DimacsError(
                        "line %d: literal %d exceeds declared %d variables"
                        % (lineno, lit, num_vars)
                    )
                current.append(lit)

    if not header_seen:
        raise DimacsError("missing 'p cnf <vars> <clauses>' problem line")
    if current:
        raise DimacsError("last clause is not terminated by 0")
    if len(clauses) != expected_clauses:
        raise DimacsError(
            "header declares %d clauses but %d were found"
            % (expected_clauses, len(clauses))
        )
    return CnfFormula(num_vars=num_vars, clauses=clauses)


def parse_dimacs_file(path):
    with open(path, "r") as handle:
        return parse_dimacs(handle.read())


def verify_model(formula, model):
    """Return True iff the complete assignment satisfies every clause."""
    for clause in formula.clauses:
        if clause is None:
            continue  # tautology dropped at parse time
        if not any(model[abs(lit)] == (lit > 0) for lit in clause):
            return False
    return True


def _simplify(clauses, lit):
    """Assign literal lit=True. Return simplified clauses, or None on conflict."""
    new_clauses = []
    neg = -lit
    for clause in clauses:
        if lit in clause:
            continue  # clause satisfied
        if neg in clause:
            reduced = clause - {neg}
            if not reduced:
                return None  # empty clause: conflict
            new_clauses.append(reduced)
        else:
            new_clauses.append(clause)
    return new_clauses


def _find_unit(clauses):
    for clause in clauses:
        if len(clause) == 1:
            return next(iter(clause))
    return None


def _find_pure(clauses):
    polarities = {}
    for clause in clauses:
        for lit in clause:
            polarities.setdefault(abs(lit), set()).add(lit > 0)
    for var, signs in polarities.items():
        if len(signs) == 1:
            return var if signs.pop() else -var
    return None


def _choose_variable(clauses):
    """DLIS-style heuristic: unassigned variable with the most occurrences."""
    counts = {}
    for clause in clauses:
        for lit in clause:
            var = abs(lit)
            counts[var] = counts.get(var, 0) + 1
    if not counts:
        return None
    # deterministic tie-break on the variable index
    return max(sorted(counts), key=lambda var: counts[var])


def _preferred_polarity(clauses, var):
    """Branch first on the polarity in which var occurs more often."""
    pos = neg = 0
    for clause in clauses:
        if var in clause:
            pos += 1
        if -var in clause:
            neg += 1
    return pos >= neg


def _dpll(clauses, stats):
    """Core DPLL. Return a partial assignment dict, or None if UNSAT."""
    assignment = {}
    while True:
        unit = _find_unit(clauses)
        if unit is not None:
            stats.propagations += 1
            clauses = _simplify(clauses, unit)
            if clauses is None:
                return None
            assignment[abs(unit)] = unit > 0
            continue
        pure = _find_pure(clauses)
        if pure is not None:
            stats.propagations += 1
            clauses = _simplify(clauses, pure)
            if clauses is None:
                return None
            assignment[abs(pure)] = pure > 0
            continue
        break

    if not clauses:
        return assignment

    var = _choose_variable(clauses)
    stats.decisions += 1
    first = _preferred_polarity(clauses, var)
    for value in (first, not first):
        lit = var if value else -var
        reduced = _simplify(clauses, lit)
        if reduced is None:
            stats.backtracks += 1
            continue
        sub = _dpll(reduced, stats)
        if sub is not None:
            assignment[var] = value
            assignment.update(sub)
            return assignment
        stats.backtracks += 1
    return None


def solve(formula):
    """Solve a CnfFormula with DPLL. Returns a SolveResult."""
    stats = Stats()
    clauses = [c for c in formula.clauses if c is not None]
    if any(len(c) == 0 for c in clauses):
        # empty clause: formula is UNSAT without any search
        return SolveResult(satisfiable=False, model=None, stats=stats)
    partial = _dpll(clauses, stats)
    if partial is None:
        return SolveResult(satisfiable=False, model=None, stats=stats)
    # Complete the model: variables never constrained get False.
    model = {var: partial.get(var, False) for var in range(1, formula.num_vars + 1)}
    assert verify_model(formula, model)
    return SolveResult(satisfiable=True, model=model, stats=stats)


def solve_dimacs(text):
    return solve(parse_dimacs(text))


def main(argv=None):
    import sys

    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 1:
        print("usage: python3 -m sat_solver <file.cnf>", file=sys.stderr)
        return 2
    try:
        formula = parse_dimacs_file(argv[0])
    except DimacsError as exc:
        print("parse error: %s" % exc, file=sys.stderr)
        return 2
    result = solve(formula)
    stats = result.stats
    print(
        "c stats: decisions=%d propagations=%d backtracks=%d"
        % (stats.decisions, stats.propagations, stats.backtracks)
    )
    if result.satisfiable:
        print("s SATISFIABLE")
        lits = " ".join(
            str(var if value else -var) for var, value in sorted(result.model.items())
        )
        print("v %s 0" % lits if lits else "v 0")
        return 0
    print("s UNSATISFIABLE")
    return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
