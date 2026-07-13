import unittest
from triggering.fuzzy import FuzzySystem

class TestFuzzySystem(unittest.TestCase):
    def setUp(self):
        # Using the consolidated clair apt-base example config for testing
        self.system = FuzzySystem("examples/clair_apt_base.yml")
        
    def test_fuzzy_compute(self):
        state = {
            'L1_DOM': 1.0,
            'L1_COO': 0.0,
            'L1_OFF': 0.0,
            'L2C_IN': 0.0,
            'L2C_AR': 1.0,
            'L2C_AI': 0.0,
            'L2C_AM': 0.0,
            'L2C_NOS': 0.0,
            'TSIM': 0.3,
            'TACC': 0.3,
            'PACE': 5.0,
            'TIME': 1200.0
        }
        
        fuzzy_output = self.system.compute(state)
        
        # It should trigger expand_reasoning and not others
        self.assertGreater(fuzzy_output.get("expand_reasoning", 0), 0)
        self.assertEqual(fuzzy_output.get("agree_disagree", 0), 0)

if __name__ == '__main__':
    unittest.main()
