"""A self-contained local SAT solver (DPLL) with DIMACS CNF parsing.

No external solvers, services, or dependencies are used. The core DPLL
algorithm (unit propagation, pure literal elimination, branching heuristic,
backtracking) is implemented from scratch using only the Python standard
library.

Deterministic semantics for edge cases:
  * Empty formula (zero clauses)          -> SAT with an empty model.
  * Empty clause                          -> the formula is UNSAT.
  * Duplicate literals inside a clause    -> deduplicated at load time.
  * Tautology clause (contains x and ~x)  -> always true, dropped at load time.
"""

from dataclasses import dataclass, field

__all__ = [
    "DimacsError",
    "parse_dimacs",
    "normalize_clause",
    "DPLLSolver",
    "Stats",
    "solve",
    "verify",
]


class DimacsError(ValueError):
    """Raised when a DIMACS CNF input is malformed."""


def normalize_clause(literals):
    """Normalize one clause.

    Returns a tuple of deduplicated literals, or None if the clause is a
    tautology (contains both x and -x) and therefore always satisfied.
    """
    seen = set()
    for lit in literals:
        if -lit in seen:
            return None
        seen.add(lit)
    return tuple(sorted(seen, key=lambda l: (abs(l), l < 0)))


def parse_dimacs(text):
    """Parse DIMACS CNF text into (num_vars, clauses).

    Strictly validates the header, literal ranges, clause terminators, the
    declared clause count, and the end of file. Clauses are normalized
    (duplicates removed, tautologies dropped); empty clauses are preserved.

    Raises DimacsError on any malformed input.
    """
    num_vars = None
    expected_clauses = None
    clauses = []
    raw_clause_count = 0
    current = []
    header_seen = False
    lines = text.splitlines()
    lineno = 0

    while lineno < len(lines):
        raw_line = lines[lineno]
        lineno += 1
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("c"):
            if len(line) > 1 and not line[1].isspace():
                raise DimacsError(f"line {lineno}: malformed comment line")
            continue
        if line.startswith("p"):
            if header_seen:
                raise DimacsError(f"line {lineno}: duplicate problem line")
            parts = line.split()
            if len(parts) != 4 or parts[1] != "cnf":
                raise DimacsError(
                    f"line {lineno}: problem line must be 'p cnf <vars> <clauses>'"
                )
            try:
                num_vars = int(parts[2])
                expected_clauses = int(parts[3])
            except ValueError:
                raise DimacsError(
                    f"line {lineno}: variable/clause counts must be integers"
                ) from None
            if num_vars < 0 or expected_clauses < 0:
                raise DimacsError(
                    f"line {lineno}: variable/clause counts must be non-negative"
                )
            header_seen = True
            continue
        if line.startswith("%"):
            for extra in lines[lineno:]:
                extra = extra.strip()
                if extra and not extra.startswith("c"):
                    raise DimacsError(
                        "content found after the '%' end-of-file marker"
                    )
            break
        if not header_seen:
            raise DimacsError(f"line {lineno}: clause data before problem line")

        for token in line.split():
            try:
                lit = int(token)
            except ValueError:
                raise DimacsError(
                    f"line {lineno}: invalid literal {token!r}"
                ) from None
            if lit == 0:
                raw_clause_count += 1
                normalized = normalize_clause(current)
                if normalized is not None:
                    clauses.append(normalized)
                current = []
            else:
                if abs(lit) > num_vars:
                    raise DimacsError(
                        f"line {lineno}: literal {lit} exceeds declared "
                        f"variable count {num_vars}"
                    )
                current.append(lit)

    if not header_seen:
        raise DimacsError("missing problem line 'p cnf <vars> <clauses>'")
    if current:
        raise DimacsError("file ended in the middle of a clause (missing '0')")
    if raw_clause_count != expected_clauses:
        raise DimacsError(
            f"declared {expected_clauses} clauses but found {raw_clause_count}"
        )
    return num_vars, clauses


@dataclass
class Stats:
    """Search statistics collected during DPLL."""

    propagations: int = 0
    pure_literals: int = 0
    decisions: int = 0
    backtracks: int = 0


def _clause_status(clause, assignment):
    """Return ('sat'|'conflict'|'unit'|'open', unit_literal_or_None)."""
    unassigned = []
    for lit in clause:
        value = assignment.get(abs(lit))
        if value is None:
            unassigned.append(lit)
        elif value == (lit > 0):
            return "sat", None
    if not unassigned:
        return "conflict", None
    if len(unassigned) == 1:
        return "unit", unassigned[0]
    return "open", None


class DPLLSolver:
    """Recursive DPLL solver with unit propagation and pure literals."""

    def __init__(self, num_vars, clauses):
        self.num_vars = num_vars
        self.clauses = [tuple(c) for c in clauses]
        self.stats = Stats()

    def solve(self):
        """Return a complete model dict {var: bool} if SAT, else None."""
        assignment = {}
        result = self._dpll(assignment)
        if result is None:
            return None
        # Any variable left unassigned is a don't-care: the formula is
        # satisfied regardless of its value, so extend the model with False
        # to make it complete.
        model = dict(result)
        for var in range(1, self.num_vars + 1):
            model.setdefault(var, False)
        return model

    def _propagate(self, assignment):
        """Unit propagation. Returns False on conflict."""
        while True:
            unit_lit = None
            for clause in self.clauses:
                status, lit = _clause_status(clause, assignment)
                if status == "conflict":
                    return False
                if status == "unit" and unit_lit is None:
                    unit_lit = lit
            if unit_lit is None:
                return True
            assignment[abs(unit_lit)] = unit_lit > 0
            self.stats.propagations += 1

    def _eliminate_pure_literals(self, assignment):
        """Assign every literal that occurs with only one polarity."""
        polarity = {}
        for clause in self.clauses:
            status, _ = _clause_status(clause, assignment)
            if status == "sat":
                continue
            for lit in clause:
                var = abs(lit)
                if var in assignment:
                    continue
                sign = lit > 0
                if var in polarity and polarity[var] != sign:
                    polarity[var] = None  # both polarities seen: not pure
                elif var not in polarity:
                    polarity[var] = sign
        for var, sign in polarity.items():
            if sign is not None:
                assignment[var] = sign
                self.stats.pure_literals += 1

    def _choose_variable(self, assignment):
        """Pick the unassigned variable occurring most often in open clauses."""
        scores = {}
        for clause in self.clauses:
            status, _ = _clause_status(clause, assignment)
            if status == "sat":
                continue
            for lit in clause:
                var = abs(lit)
                if var not in assignment:
                    scores[var] = scores.get(var, 0) + 1
        if not scores:
            return None
        return max(sorted(scores), key=lambda v: scores[v])

    def _all_satisfied(self, assignment):
        return all(
            _clause_status(clause, assignment)[0] == "sat" for clause in self.clauses
        )

    def _dpll(self, assignment):
        if not self._propagate(assignment):
            return None
        self._eliminate_pure_literals(assignment)
        if not self._propagate(assignment):
            return None
        if self._all_satisfied(assignment):
            return assignment

        var = self._choose_variable(assignment)
        if var is None:
            return assignment

        self.stats.decisions += 1
        snapshot = dict(assignment)
        for value in (True, False):
            assignment[var] = value
            if self._dpll(assignment) is not None:
                return assignment
            self.stats.backtracks += 1
            assignment.clear()
            assignment.update(snapshot)
        return None


def solve(num_vars, clauses):
    """Solve a CNF instance. Returns (is_sat, model_or_None, stats)."""
    solver = DPLLSolver(num_vars, clauses)
    model = solver.solve()
    return model is not None, model, solver.stats


def verify(clauses, model):
    """Check that every clause is satisfied by the given model."""
    for clause in clauses:
        if not any(model.get(abs(lit)) == (lit > 0) for lit in clause):
            return False
    return True
