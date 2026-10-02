import itertools
import random
import unittest

from sat_solver import (
    DimacsError,
    parse_dimacs,
    solve,
    solve_dimacs,
    verify_model,
)


def brute_force_satisfiable(formula):
    """Exhaustive oracle for small formulas."""
    clauses = [c for c in formula.clauses if c is not None]
    for values in itertools.product([False, True], repeat=formula.num_vars):
        model = {var: values[var - 1] for var in range(1, formula.num_vars + 1)}
        if all(
            any(model[abs(lit)] == (lit > 0) for lit in clause) for clause in clauses
        ):
            return True
    return False


def dimacs(num_vars, clauses):
    lines = ["p cnf %d %d" % (num_vars, len(clauses))]
    for clause in clauses:
        lines.append(" ".join(str(lit) for lit in clause) + " 0")
    return "\n".join(lines) + "\n"


class TestDimacsParsing(unittest.TestCase):
    def test_valid_file_with_comments_and_end_marker(self):
        text = "c a comment\np cnf 2 2\n1 2 0\nc mid comment\n-1 0\n%\n"
        formula = parse_dimacs(text)
        self.assertEqual(formula.num_vars, 2)
        self.assertEqual(len(formula.clauses), 2)

    def test_clause_spanning_multiple_lines(self):
        formula = parse_dimacs("p cnf 3 1\n1\n2\n3 0\n")
        self.assertEqual(formula.clauses, [frozenset({1, 2, 3})])

    def test_missing_header(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("1 0\n")

    def test_bad_header_format(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p sat 2 1\n1 0\n")

    def test_duplicate_header(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 1 1\np cnf 1 1\n1 0\n")

    def test_clause_before_header(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("1 0\np cnf 1 1\n")

    def test_literal_out_of_range(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 2 1\n3 0\n")

    def test_non_integer_literal(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 2 1\nx 0\n")

    def test_unterminated_clause(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 2 1\n1 2\n")

    def test_clause_count_mismatch(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 2 2\n1 0\n")

    def test_content_after_end_marker(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 1 1\n1 0\n%\n1 0\n")

    def test_negative_counts_rejected(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf -1 0\n")


class TestDeterministicSemantics(unittest.TestCase):
    def test_empty_formula_is_sat(self):
        result = solve_dimacs("p cnf 3 0\n")
        self.assertTrue(result.satisfiable)
        self.assertEqual(set(result.model), {1, 2, 3})

    def test_empty_clause_is_unsat(self):
        result = solve_dimacs("p cnf 2 2\n1 0\n0\n")
        self.assertFalse(result.satisfiable)
        self.assertIsNone(result.model)

    def test_duplicate_literals_collapse(self):
        formula = parse_dimacs("p cnf 2 1\n1 1 -2 -2 0\n")
        self.assertEqual(formula.clauses, [frozenset({1, -2})])

    def test_tautology_clause_dropped(self):
        result = solve_dimacs("p cnf 2 2\n1 -1 0\n2 0\n")
        self.assertTrue(result.satisfiable)
        self.assertTrue(result.model[2])


class TestDpll(unittest.TestCase):
    def test_simple_sat(self):
        result = solve_dimacs(dimacs(2, [[1, 2], [-1]]))
        self.assertTrue(result.satisfiable)
        self.assertFalse(result.model[1])
        self.assertTrue(result.model[2])

    def test_simple_unsat(self):
        result = solve_dimacs(dimacs(1, [[1], [-1]]))
        self.assertFalse(result.satisfiable)

    def test_unit_propagation_chain(self):
        # (x1) & (~x1 | x2) & (~x2 | x3) forces x1=x2=x3=True
        result = solve_dimacs(dimacs(3, [[1], [-1, 2], [-2, 3]]))
        self.assertTrue(result.satisfiable)
        self.assertEqual(result.model, {1: True, 2: True, 3: True})
        self.assertGreaterEqual(result.stats.propagations, 3)
        self.assertEqual(result.stats.decisions, 0)

    def test_pure_literal_elimination(self):
        # x1 and x3 occur only positively: pure literal elimination
        # solves the formula without any decisions.
        result = solve_dimacs(dimacs(3, [[1, 3], [2, 3], [-2, 3]]))
        self.assertTrue(result.satisfiable)
        self.assertTrue(result.model[1])
        self.assertTrue(result.model[3])
        self.assertEqual(result.stats.decisions, 0)
        self.assertGreaterEqual(result.stats.propagations, 2)

    def test_deep_backtracking_pigeonhole(self):
        # 3 pigeons, 2 holes: classic UNSAT requiring real search.
        # var p*2+h (1-based): pigeon p in hole h
        clauses = []
        for p in range(3):
            clauses.append([p * 2 + 1, p * 2 + 2])  # every pigeon in some hole
        for h in range(2):
            for p1 in range(3):
                for p2 in range(p1 + 1, 3):
                    clauses.append([-(p1 * 2 + h + 1), -(p2 * 2 + h + 1)])
        result = solve_dimacs(dimacs(6, clauses))
        self.assertFalse(result.satisfiable)
        self.assertGreater(result.stats.decisions, 0)
        self.assertGreater(result.stats.backtracks, 0)

    def test_backtracking_finds_sat_after_wrong_branch(self):
        # x1 is the most frequent variable; trying x1=True forces both
        # x2 and ~x2, so the solver must backtrack to x1=False.
        clauses = [[-1, 2], [-1, -2], [1, 2], [1, 3], [-3, 2]]
        result = solve_dimacs(dimacs(3, clauses))
        self.assertTrue(result.satisfiable)
        self.assertFalse(result.model[1])
        self.assertTrue(result.model[2])
        self.assertGreaterEqual(result.stats.backtracks, 1)

    def test_model_is_complete_and_verified(self):
        result = solve_dimacs(dimacs(5, [[1, -3], [2, 4]]))
        self.assertTrue(result.satisfiable)
        self.assertEqual(set(result.model), {1, 2, 3, 4, 5})
        formula = parse_dimacs(dimacs(5, [[1, -3], [2, 4]]))
        self.assertTrue(verify_model(formula, result.model))

    def test_verify_model_rejects_bad_assignment(self):
        formula = parse_dimacs(dimacs(2, [[1], [2]]))
        self.assertFalse(verify_model(formula, {1: True, 2: False}))

    def test_stats_reported(self):
        result = solve_dimacs(dimacs(3, [[1, 2], [-1, 3], [-2, -3], [1, 3]]))
        self.assertGreaterEqual(result.stats.decisions, 1)
        self.assertGreaterEqual(result.stats.propagations, 0)
        self.assertGreaterEqual(result.stats.backtracks, 0)


class TestRandomAgainstOracle(unittest.TestCase):
    def test_random_small_formulas_match_brute_force(self):
        rng = random.Random(20261002)
        for trial in range(300):
            num_vars = rng.randint(1, 4)
            num_clauses = rng.randint(0, 8)
            clauses = []
            for _ in range(num_clauses):
                size = rng.randint(1, 3)
                clause = [
                    rng.choice([-1, 1]) * rng.randint(1, num_vars)
                    for _ in range(size)
                ]
                clauses.append(clause)
            text = dimacs(num_vars, clauses)
            formula = parse_dimacs(text)
            result = solve(formula)
            expected = brute_force_satisfiable(formula)
            self.assertEqual(
                result.satisfiable, expected, "mismatch on trial %d: %s" % (trial, text)
            )
            if result.satisfiable:
                self.assertTrue(verify_model(formula, result.model))


class TestCli(unittest.TestCase):
    def test_cli_sat_and_unsat(self):
        import os
        import subprocess
        import sys
        import tempfile

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with tempfile.TemporaryDirectory() as tmp:
            sat_path = os.path.join(tmp, "sat.cnf")
            with open(sat_path, "w") as handle:
                handle.write("p cnf 2 2\n1 2 0\n-1 0\n")
            proc = subprocess.run(
                [sys.executable, "-m", "sat_solver", sat_path],
                cwd=root,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0)
            self.assertIn("s SATISFIABLE", proc.stdout)
            self.assertIn("decisions=", proc.stdout)
            self.assertIn("propagations=", proc.stdout)
            self.assertIn("backtracks=", proc.stdout)

            unsat_path = os.path.join(tmp, "unsat.cnf")
            with open(unsat_path, "w") as handle:
                handle.write("p cnf 1 2\n1 0\n-1 0\n")
            proc = subprocess.run(
                [sys.executable, "-m", "sat_solver", unsat_path],
                cwd=root,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 1)
            self.assertIn("s UNSATISFIABLE", proc.stdout)

            bad_path = os.path.join(tmp, "bad.cnf")
            with open(bad_path, "w") as handle:
                handle.write("p cnf 1 1\n2 0\n")
            proc = subprocess.run(
                [sys.executable, "-m", "sat_solver", bad_path],
                cwd=root,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 2)
            self.assertIn("parse error", proc.stderr)


if __name__ == "__main__":
    unittest.main()
