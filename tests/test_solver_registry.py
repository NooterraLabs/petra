"""Every registered rule has a solver module of the same name, and nothing else does. Owner: I."""
import pkgutil
import unittest

import lola.solvers as solvers
from lola.kernel import GOAL_RULE, MODULE_OF


class SolverRegistry(unittest.TestCase):
    def test_one_solver_module_per_rule(self):
        on_disk = {info.name for info in pkgutil.iter_modules(solvers.__path__)}
        self.assertEqual(on_disk - solvers._HELPERS, set(MODULE_OF.values()))

    def test_every_goal_has_a_solver(self):
        self.assertEqual(set(solvers.SOLVERS), set(GOAL_RULE))
        for solve in solvers.SOLVERS.values():
            self.assertTrue(callable(solve))


if __name__ == "__main__":
    unittest.main()
