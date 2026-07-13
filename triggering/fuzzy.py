import os
import yaml
from typing import Dict, Any

class FuzzySystem:
    def __init__(self, config_path: str):
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f)
            
        self.antecedents = self._parse_memberships(data.get('inputs', []))
        self.consequents = self._parse_memberships(data.get('outputs', []))
        self.rules = data.get('rules', [])

    def _parse_memberships(self, data_list: list) -> Dict[str, Any]:
        parsed = {}
        for var in data_list:
            name = var['name']
            terms = {}
            for term in var['terms']:
                terms[term['name']] = {
                    'fn': term['fn'],
                    'params': term.get('abcd') or term.get('abc')
                }
            parsed[name] = terms
        return parsed

    def _evaluate_membership(self, x: float, term: Dict[str, Any]) -> float:
        fn = term['fn']
        p = term['params']
        if fn == 'trapmf':
            a, b, c, d = p
            if x < a or x > d:
                return 0.0
            elif b <= x <= c:
                return 1.0
            elif a <= x < b:
                return (x - a) / (b - a) if b != a else 1.0
            elif c < x <= d:
                return (d - x) / (d - c) if d != c else 1.0
        elif fn == 'trimf':
            a, b, c = p
            if x <= a or x >= c:
                return 0.0
            elif x == b:
                return 1.0
            elif a < x < b:
                return (x - a) / (b - a) if b != a else 1.0
            elif b < x < c:
                return (c - x) / (c - b) if c != b else 1.0
        return 0.0

    def compute(self, inputs: Dict[str, float]) -> Dict[str, float]:
        # Evaluate all antecedent memberships for the given state
        fuzzified_inputs = {}
        for var_name, terms in self.antecedents.items():
            val = inputs.get(var_name, 0.0) # default to 0 if missing
            fuzzified_inputs[var_name] = {}
            for term_name, term_data in terms.items():
                fuzzified_inputs[var_name][term_name] = self._evaluate_membership(val, term_data)

        # Output aggregation (max of all fired rule strengths for each consequent)
        consequent_scores = {c: 0.0 for c in self.consequents}

        for rule in self.rules:
            # Replicating the exact logic from the original parser:
            l1_scores = []
            l2_scores = []
            other_scores = []
            negation_scores = []

            for name, values in rule['antecedents'].items():
                if name not in fuzzified_inputs:
                    continue
                
                var_or_scores = []
                for v in values:
                    is_not = v.startswith('not ')
                    term_name = v[4:] if is_not else v
                    score = fuzzified_inputs[name].get(term_name, 0.0)
                    
                    if is_not:
                        negation_scores.append(1.0 - score)
                    else:
                        if 'L1' in name:
                            l1_scores.append(score)
                        elif 'L2' in name:
                            l2_scores.append(score)
                        else:
                            var_or_scores.append(score)
                
                if var_or_scores:
                    other_scores.append(max(var_or_scores))

            # Combine subrules using AND (min)
            final_score_components = []
            if l1_scores:
                final_score_components.append(max(l1_scores))
            if l2_scores:
                final_score_components.append(max(l2_scores))
            if other_scores:
                final_score_components.append(min(other_scores)) # AND across different other vars
            if negation_scores:
                final_score_components.append(min(negation_scores))

            if final_score_components:
                rule_strength = min(final_score_components)
            else:
                rule_strength = 0.0

            # Apply to consequent
            for cons_name, cons_val in rule['consequent'].items():
                if cons_val == 'active':
                    consequent_scores[cons_name] = max(consequent_scores[cons_name], rule_strength)

        return consequent_scores

if __name__ == "__main__":
    import argparse
    import json
    parser = argparse.ArgumentParser(description="Fuzzy Inference Engine CLI")
    parser.add_argument("command", choices=["compute"])
    parser.add_argument("--config", type=str, required=True, help="Path to the unified YAML configuration file.")
    parser.add_argument("--inputs", type=str, required=True, help="JSON dictionary of crisp input values.")
    args = parser.parse_args()

    if args.command == "compute":
        system = FuzzySystem(config_path=args.config)
        state = eval(args.inputs)
        result = system.compute(state)
        print(json.dumps(result, indent=4))
