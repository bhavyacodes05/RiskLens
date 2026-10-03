import unittest
from app import compute

class ControlTests(unittest.TestCase):
    def test_default_equals_original(self):
        r=compute({})
        self.assertAlmostEqual(r['comparison']['var_change'],0)
    def test_zero_hedge_matches_unhedged(self):
        r=compute({'hedge':['0']})
        self.assertAlmostEqual(r['risk']['var'],r['unhedged_var'])
        self.assertFalse(any(p['asset']=='equity' and p['market_value']<0 for p in r['positions']))
    def test_edit_precedes_both_multipliers(self):
        r=compute({'value_EQ2':['-2000000'],'hedge':['.5'],'scale':['2']})
        p=next(p for p in r['positions'] if p['id']=='EQ2')
        self.assertEqual(p['market_value'],-2000000)
    def test_zero_removes_position(self):
        r=compute({'value_BD1':['0']})
        self.assertFalse(any(p['id']=='BD1' for p in r['positions']))
    def test_invalid_controls_fail(self):
        for p in ({'hedge':['nan']},{'hedge':['4']},{'value_EQ1':['inf']},{'value_EQ1':['50000001']}):
            with self.assertRaises(ValueError):compute(p)
    def test_empty_book_rejected(self):
        with self.assertRaises(ValueError):compute({f'value_{i}':['0'] for i in ['EQ1','EQ2','BD1','BD2','FX1']})
