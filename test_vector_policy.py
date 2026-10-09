import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from model import run
class VectorPolicy(unittest.TestCase):
 def test_single_construct_and_planned_lot(self):
  for c in ('low','base','high'):
   r=run(c);self.assertEqual(r['capacity']['vector_constructs'],1);self.assertEqual(r['capacity']['vector_attempts'],1)
 def test_shortfall_is_flagged_not_autopurchased(self):
  r=run('high');self.assertTrue(r['vector_capacity_warning']);self.assertIsNone(r['approved_total_sek'])
