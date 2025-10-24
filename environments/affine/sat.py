"""SAT task generator and evaluator"""

import random
import re


class SATTask:
    """SAT problem generator and evaluator"""
    
    @staticmethod
    def generate(n=15, k=10):
        """Generate a satisfiable k-SAT problem"""
        m = int(4.26 * n)
        sol = {i: random.choice([True, False]) for i in range(1, n + 1)}
        
        cls = []
        for _ in range(m):
            vs = random.sample(list(sol), k)
            sv = random.choice(vs)
            cls.append([
                (v if sol[v] else -v) if v == sv 
                else (v if random.choice([True, False]) else -v)
                for v in vs
            ])
        
        formula = " ∧ ".join(
            "(" + " ∨ ".join(f"{'¬' if l < 0 else ''}x{abs(l)}" for l in c) + ")"
            for c in cls
        )
        
        prompt = (
            f"Find a satisfying assignment for the following {k}-SAT formula over variables x1..x{n}:\n"
            f"{formula}\n"
            "Provide your answer as comma-separated assignments like `x1=True, x2=False, ...`, "
            "or respond `UNSAT` if it has no solution."
        )
        
        return prompt, sol, cls
    
    @staticmethod
    def evaluate(response, cls):
        """Evaluate SAT response"""
        got = {
            int(v): val.lower() in ("true", "1")
            for v, val in re.findall(r"x(\d+)=(True|False|1|0)", response or "")
        }
        
        ok = all(any((lit > 0) == got.get(abs(lit), None) for lit in c) for c in cls)
        return float(ok)