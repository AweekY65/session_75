import itertools
import random
import unittest

from sat_solver import (
    DimacsError,
    DPLLSolver,
    normalize_clause,
    parse_dimacs,
    solve,
    verify,
)


def brute_force(num_vars, clauses):
    """Exhaustive oracle: returns a satisfying model or None."""
    for values in itertools.product([False, True], repeat=num_vars):
        model = {var: values[var - 1] for var in range(1, num_vars + 1)}
        if verify(clauses, model):
            return model
    return None


class TestParseDimacs(unittest.TestCase):
    def test_basic(self):
        text = "c comment\np cnf 3 2\n1 -2 0\n2 3 0\n"
        num_vars, clauses = parse_dimacs(text)
        self.assertEqual(num_vars, 3)
        self.assertEqual(clauses, [(1, -2), (2, 3)])

    def test_clause_spanning_lines(self):
        num_vars, clauses = parse_dimacs("p cnf 2 1\n1\n2 0\n")
        self.assertEqual(clauses, [(1, 2)])

    def test_duplicate_literals_deduplicated(self):
        _, clauses = parse_dimacs("p cnf 2 1\n1 1 -2 -2 0\n")
        self.assertEqual(clauses, [(1, -2)])

    def test_tautology_clause_dropped(self):
        _, clauses = parse_dimacs("p cnf 2 2\n1 -1 0\n2 0\n")
        self.assertEqual(clauses, [(2,)])

    def test_empty_clause_preserved(self):
        _, clauses = parse_dimacs("p cnf 1 1\n0\n")
        self.assertEqual(clauses, [()])

    def test_empty_formula(self):
        num_vars, clauses = parse_dimacs("p cnf 4 0\n")
        self.assertEqual(num_vars, 4)
        self.assertEqual(clauses, [])

    def test_percent_end_marker(self):
        num_vars, clauses = parse_dimacs("p cnf 1 1\n1 0\n%\nc trailing\n")
        self.assertEqual(clauses, [(1,)])

    def test_missing_header(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("1 0\n")

    def test_bad_header_format(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 2\n1 0\n")
        with self.assertRaises(DimacsError):
            parse_dimacs("p sat 2 1\n1 0\n")

    def test_duplicate_header(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 1 1\np cnf 1 1\n1 0\n")

    def test_literal_out_of_range(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 2 1\n3 0\n")

    def test_non_integer_token(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 2 1\n1 x 0\n")

    def test_missing_clause_terminator(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 2 1\n1 2\n")

    def test_clause_count_mismatch(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 2 2\n1 0\n")
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 2 1\n1 0\n2 0\n")

    def test_content_after_end_marker(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 1 1\n1 0\n%\n2 0\n")


class TestNormalizeClause(unittest.TestCase):
    def test_tautology(self):
        self.assertIsNone(normalize_clause([1, -1, 2]))

    def test_dedup(self):
        self.assertEqual(normalize_clause([2, 2, -1]), (-1, 2))


class TestDPLL(unittest.TestCase):
    def test_simple_sat(self):
        is_sat, model, _ = solve(2, [(1, 2), (-1,)])
        self.assertTrue(is_sat)
        self.assertTrue(verify([(1, 2), (-1,)], model))

    def test_simple_unsat(self):
        is_sat, model, _ = solve(1, [(1,), (-1,)])
        self.assertFalse(is_sat)
        self.assertIsNone(model)

    def test_empty_formula_is_sat(self):
        is_sat, model, _ = solve(3, [])
        self.assertTrue(is_sat)
        self.assertEqual(set(model), {1, 2, 3})

    def test_empty_clause_is_unsat(self):
        is_sat, _, _ = solve(2, [()])
        self.assertFalse(is_sat)

    def test_unit_propagation_chain(self):
        # 1 -> 2 -> 3 forced by unit propagation alone.
        clauses = [(1,), (-1, 2), (-2, 3)]
        is_sat, model, stats = solve(3, clauses)
        self.assertTrue(is_sat)
        self.assertEqual(model, {1: True, 2: True, 3: True})
        self.assertGreaterEqual(stats.propagations, 3)
        self.assertEqual(stats.decisions, 0)

    def test_pure_literal_elimination(self):
        # Variable 2 occurs only positively: pure literal, no decision needed.
        clauses = [(1, 2), (-1, 2)]
        is_sat, model, stats = solve(2, clauses)
        self.assertTrue(is_sat)
        self.assertTrue(model[2])
        self.assertGreaterEqual(stats.pure_literals, 1)

    def test_deep_backtracking(self):
        # Pigeonhole: 3 pigeons, 2 holes -> UNSAT, requires backtracking.
        # Variable p_h means pigeon p in hole h.
        clauses = []
        for p in range(3):
            clauses.append(tuple(p * 2 + h + 1 for h in range(2)))
        for p in range(3):
            for q in range(p + 1, 3):
                for h in range(2):
                    clauses.append((-(p * 2 + h + 1), -(q * 2 + h + 1)))
        is_sat, _, stats = solve(6, clauses)
        self.assertFalse(is_sat)
        self.assertGreater(stats.decisions, 0)
        self.assertGreater(stats.backtracks, 0)

    def test_backtracking_finds_late_model(self):
        # Only all-true assignment satisfies; wrong early guesses must be
        # undone by backtracking.
        num_vars = 6
        clauses = []
        for i in range(1, num_vars):
            clauses.append(tuple(range(i, num_vars + 1)))
            clauses.append((-i, i + 1))
        is_sat, model, stats = solve(num_vars, clauses)
        self.assertTrue(is_sat)
        self.assertTrue(verify(clauses, model))

    def test_stats_fields(self):
        _, _, stats = solve(2, [(1, 2), (-1, 2), (1, -2), (-1, -2)])
        for name in ("propagations", "pure_literals", "decisions", "backtracks"):
            self.assertGreaterEqual(getattr(stats, name), 0)

    def test_model_is_complete(self):
        # Variable 3 does not occur in any clause; model must still cover it.
        is_sat, model, _ = solve(3, [(1,)])
        self.assertTrue(is_sat)
        self.assertEqual(set(model), {1, 2, 3})

    def test_verify_rejects_bad_model(self):
        self.assertFalse(verify([(1,)], {1: False}))
        self.assertFalse(verify([()], {1: True}))


class TestRandomOracle(unittest.TestCase):
    def test_random_small_formulas_against_brute_force(self):
        rng = random.Random(20261002)
        for _ in range(300):
            num_vars = rng.randint(1, 5)
            num_clauses = rng.randint(0, 8)
            clauses = []
            for _ in range(num_clauses):
                size = rng.randint(1, 3)
                clause = tuple(
                    rng.choice([-1, 1]) * rng.randint(1, num_vars)
                    for _ in range(size)
                )
                normalized = normalize_clause(clause)
                if normalized is not None:
                    clauses.append(normalized)
            is_sat, model, _ = solve(num_vars, clauses)
            oracle = brute_force(num_vars, clauses)
            self.assertEqual(
                is_sat, oracle is not None, f"clauses={clauses}"
            )
            if is_sat:
                self.assertTrue(verify(clauses, model), f"clauses={clauses}")


if __name__ == "__main__":
    unittest.main()
