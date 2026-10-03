import copy
import csv
import math
from pathlib import Path
import tempfile
import unittest
from app import compute
from risklens.engine import validate_positions, position_pnl, load_inputs
from risklens.history import levels_to_factors, load_dataset
from risklens.diagnostics import wilson_interval, exception_diagnostics, risk_intervals
from risklens.engine import tail_risk

ROOT=Path(__file__).resolve().parents[1]
class CurveTests(unittest.TestCase):
    def test_parallel_krd_equals_total_duration(self):
        p={'asset':'bond','market_value':1000000,'krd_2y':1,'krd_5y':2,'krd_10y':3}
        self.assertAlmostEqual(position_pnl(p,{f'yield_{t}_bp':100 for t in ('2y','5y','10y')}),-60000)
    def test_steepener_hand_calculation(self):
        p={'asset':'bond','market_value':1000000,'krd_2y':1,'krd_5y':2,'krd_10y':3}
        self.assertAlmostEqual(position_pnl(p,{'yield_2y_bp':-50,'yield_5y_bp':25,'yield_10y_bp':100}),-30000)
    def test_bad_krd_sum_rejected(self):
        ps,_=load_inputs(ROOT/'data');ps[2]['krd_2y']+=1
        with self.assertRaises(ValueError):validate_positions(ps)
    def test_treasury_mode_is_bond_only(self):
        r=compute({'dataset':['treasury']})
        self.assertEqual(r['history_count'],498)
        self.assertTrue(all(p['asset']=='bond' for p in r['positions']))
        self.assertEqual(r['data_type'],'historical_rates')
        json_safe=__import__('json').dumps(r,allow_nan=False)
        self.assertIn('Curve steepening',json_safe)
    def test_treasury_hash_tamper_fails(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            for name in ('positions.csv','treasury_levels.csv','treasury_calendar.csv','treasury_provenance.json'):
                shutil.copy(ROOT/'data'/name,Path(tmp)/name)
            p=Path(tmp)/'treasury_levels.csv';p.write_text(p.read_text().replace('4.33','4.34',1))
            with self.assertRaises(ValueError):load_dataset(tmp,'treasury')

class DataTests(unittest.TestCase):
    def setUp(self):
        self.dates=['2024-01-02','2024-01-03','2024-01-04']
        self.rows=[dict(date=d,yield_2y_pct=4+i*.1,yield_5y_pct=4+i*.2,yield_10y_pct=4+i*.3,equity_level=100+i*10,eurusd=1+i*.1) for i,d in enumerate(self.dates)]
    def test_return_and_yield_units(self):
        r=levels_to_factors(self.rows,self.dates,True)[0]
        self.assertAlmostEqual(r['yield_2y_bp'],10)
        self.assertAlmostEqual(r['yield_10y_bp'],30)
        self.assertAlmostEqual(r['equity_return'],.1)
        self.assertAlmostEqual(r['fx_return'],.1)
    def test_missing_date_is_not_bridged(self):
        with self.assertRaises(ValueError):levels_to_factors(self.rows[::2],self.dates,True)
    def test_missing_value_is_not_filled(self):
        for value in ('','N/A',float('nan')):
            rows=copy.deepcopy(self.rows);rows[1]['eurusd']=value
            with self.assertRaises(ValueError):levels_to_factors(rows,self.dates,True)
    def test_missing_date_field_rejected(self):
        del self.rows[1]['date']
        with self.assertRaises(ValueError):levels_to_factors(self.rows,self.dates,True)
    def test_duplicate_date_rejected(self):
        with self.assertRaises(ValueError):levels_to_factors(self.rows+[self.rows[-1]],self.dates,True)
    def test_reversed_dates_rejected(self):
        with self.assertRaises(ValueError):levels_to_factors(list(reversed(self.rows)),self.dates,True)

class DiagnosticTests(unittest.TestCase):
    def test_wilson_known_value(self):
        low,high=wilson_interval(0,100)
        self.assertAlmostEqual(low,0,places=12)
        self.assertAlmostEqual(high,.0369934982,places=8)
    def test_clustering_changes_independence_at_same_count(self):
        clustered=[False]*40+[True]*10+[False]*40+[True]*10
        dispersed=([False]*4+[True])*20
        a,b=exception_diagnostics(clustered),exception_diagnostics(dispersed)
        self.assertEqual(a['longest_exception_run'],10)
        self.assertGreater(a['independence_lr'],b['independence_lr'])
        self.assertEqual(sum(a['transitions'].values()),len(clustered)-1)
    def test_all_clear_is_not_claimed_independent(self):
        r=exception_diagnostics([False]*100)
        self.assertIsNone(r['independence_p_value'])
        self.assertGreater(r['wilson_95'][1],0)
    def test_bootstrap_reproducible_and_scales(self):
        losses=list(range(50))
        a=risk_intervals(losses,.95,tail_risk)
        self.assertEqual(a,risk_intervals(losses,.95,tail_risk))
        b=risk_intervals([2*x for x in losses],.95,tail_risk)
        for key in ('var_95','es_95'):
            for x,y in zip(a[key],b[key]):self.assertAlmostEqual(2*x,y)
