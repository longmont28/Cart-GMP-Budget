import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from model import run,minimum_enrollment,binomial_tail
class TestModelV3(unittest.TestCase):
 def test_assurance(self):
  for c in ('low','base','high'):
   r=run(c);self.assertGreaterEqual(r['probability_at_least_target'],.9)
 def test_minimality(self):
  n=minimum_enrollment(12,.8,.9)
  self.assertLess(binomial_tail(n-1,12,.8),.9)
 def test_missing_prices_not_zero(self):
  r=run('base');self.assertIsNone(r['approved_total_sek']);self.assertTrue(r['missing'])
 def test_lymphodepletion_not_infusion(self):
  r=run('base');self.assertGreater(r['expected']['lymphodepleted'],r['expected']['infused'])
 def test_cost_ownership(self):
  rows=run('base')['lines'];self.assertEqual(len(set(r['wbs'] for r in rows)),len(rows))
if __name__=='__main__':unittest.main()
