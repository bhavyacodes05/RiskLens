import copy
import json
import math
from pathlib import Path
import sqlite3
import tempfile
import unittest
from risklens.engine import analyze, backtest, load_inputs, position_pnl, tail_risk, validate_history, validate_positions
from risklens.reporting import save_run
ROOT = Path(__file__).resolve().parents[1]

class RiskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.positions, cls.history = load_inputs(ROOT/'data')

    def test_var_and_exact_tail_mass(self):
        r = tail_risk([0, 10, 20, 30], .625)
        self.assertEqual(r['var'], 20)
        self.assertAlmostEqual(r['es'], 40/1.5)

    def test_ties_do_not_overweight_boundary(self):
        self.assertEqual(tail_risk([0, 1, 1, 1, 10], .6)['es'], 5.5)

    def test_es_at_least_var(self):
        for confidence in (.95, .975, .99):
            r = analyze(self.positions, self.history, confidence)['risk']
            self.assertGreaterEqual(r['es'], r['var'])

    def test_bond_hand_calculation(self):
        p = {'asset': 'bond', 'market_value': 1000000, 'duration': 5, 'convexity': 30}
        self.assertAlmostEqual(position_pnl(p, {'yield_bp': 100}), -48500)

    def test_zero_shock(self):
        for p in self.positions:
            self.assertEqual(position_pnl(p, {'equity_return': 0, 'yield_bp': 0, 'fx_return': 0}), 0)

    def test_short_hedge_gains_on_equity_fall(self):
        self.assertEqual(position_pnl({'asset':'equity','market_value':-1000}, {'equity_return':-.2}), 200)

    def test_scaling_and_reconciliation(self):
        a = analyze(self.positions, self.history)
        b = analyze(self.positions, self.history, scale=2)
        for key in ('var', 'es'):
            self.assertAlmostEqual(b['risk'][key], 2*a['risk'][key])
        for s in b['scenarios']:
            self.assertAlmostEqual(s['pnl'], sum(x['pnl'] for x in s['contributions']))

    def test_forecast_excludes_current_and_future_losses(self):
        losses = [1., 2., 3., 4., 5., 6., 7.]
        dates = [str(i) for i in range(len(losses))]
        before = backtest(losses, dates, .75, 4)
        losses[4] = 1000000.
        after = backtest(losses, dates, .75, 4)
        self.assertEqual(before['rows'][0]['var'], after['rows'][0]['var'])
        self.assertEqual(after['rows'][0]['var'], 3)

    def test_kupiec_extremes_are_finite(self):
        for losses in ([1.]*10, list(range(10))):
            r = backtest(losses, list(range(10)), .95, 4)
            self.assertTrue(math.isfinite(r['kupiec_lr']))
            self.assertTrue(0 <= r['kupiec_p_value'] <= 1)

    def test_invalid_position_data_is_rejected(self):
        for field, value in [('id', self.positions[0]['id']), ('market_value',float('nan')), ('asset','unknown')]:
            rows = copy.deepcopy(self.positions); rows[1][field] = value
            with self.assertRaises(ValueError): validate_positions(rows)

    def test_invalid_history_is_rejected(self):
        for field, value in [('date', self.history[0]['date']), ('fx_return', -1), ('yield_2y_bp', float('inf'))]:
            rows = copy.deepcopy(self.history); rows[1][field] = value
            with self.assertRaises(ValueError): validate_history(rows)

    def test_invalid_controls_rejected(self):
        for kwargs in ({'scale':float('nan')}, {'scale':0}, {'confidence':1}, {'custom':{'equity_return':-.9,'yield_bp':0,'fx_return':0}}):
            with self.assertRaises(ValueError): analyze(self.positions,self.history,**kwargs)

    def test_audit_persists_identical_results(self):
        result = analyze(self.positions, self.history)
        with tempfile.TemporaryDirectory() as d:
            run, path = save_run(result, d)
            saved = json.loads(path.read_text())
            with sqlite3.connect(Path(d)/'audit.sqlite') as con:
                stored = json.loads(con.execute('SELECT result_json FROM runs WHERE id=?',(run,)).fetchone()[0])
            self.assertEqual(saved, stored)
            self.assertEqual(saved['input_sha256'], result['input_sha256'])

if __name__ == '__main__': unittest.main()
