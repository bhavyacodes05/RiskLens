"""Risk calculations, deliberately implemented without third-party dependencies.

Units: USD, decimal simple returns, yield shocks in basis points.
Historical simulation applies each observed factor vector to a fixed current book.
"""
import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import NormalDist, mean, stdev

TENORS = ('2y', '5y', '10y')
FACTORS = ('equity_return', 'yield_2y_bp', 'yield_5y_bp', 'yield_10y_bp', 'fx_return')

def parallel(equity, rate, fx):
    return {'equity_return': equity, 'fx_return': fx, **{f'yield_{t}_bp': rate for t in TENORS}}

SCENARIOS = {
    'Equity sell-off': parallel(-.20, -75, -.05),
    'Inflation shock': parallel(-.12, 200, -.08),
    'Flight to quality': parallel(-.30, -150, -.10),
    'Curve steepening': {'equity_return': 0, 'yield_2y_bp': -50, 'yield_5y_bp': 25, 'yield_10y_bp': 100, 'fx_return': 0},
    'Curve flattening': {'equity_return': 0, 'yield_2y_bp': 100, 'yield_5y_bp': 25, 'yield_10y_bp': -50, 'fx_return': 0},
}


def finite(value, name):
    try:
        number = float(value)
    except (ValueError, TypeError):
        raise ValueError(f'{name} must be numeric') from None
    if not math.isfinite(number):
        raise ValueError(f'{name} must be finite')
    return number


def validate_positions(rows):
    if not rows:
        raise ValueError('Portfolio is empty')
    seen, result = set(), []
    for source in rows:
        p = dict(source)
        for key in ('id', 'name', 'asset', 'market_value', 'duration', 'convexity'):
            if key not in p or str(p[key]).strip() == '':
                raise ValueError(f'Missing position field: {key}')
        if p['id'] in seen:
            raise ValueError(f'Duplicate position ID: {p["id"]}')
        seen.add(p['id'])
        if p['asset'] not in ('equity', 'bond', 'fx'):
            raise ValueError(f'Unsupported asset: {p["asset"]}')
        for field in ('market_value', 'duration', 'convexity'):
            p[field] = finite(p[field], field)
        if p['market_value'] == 0:
            raise ValueError('Position market value cannot be zero')
        if p['duration'] < 0 or p['convexity'] < 0:
            raise ValueError('Duration and convexity must be nonnegative')
        if p['asset'] != 'bond' and (p['duration'] or p['convexity']):
            raise ValueError('Only bonds may have duration and convexity')
        for tenor in TENORS:
            key = f'krd_{tenor}'
            p[key] = finite(p.get(key, 0), key)
            if p[key] < 0 or (p['asset'] != 'bond' and p[key] != 0):
                raise ValueError('Key-rate durations must be nonnegative and apply only to bonds')
        if p['asset'] == 'bond' and not math.isclose(sum(p[f'krd_{t}'] for t in TENORS), p['duration'], abs_tol=1e-8):
            raise ValueError('Bond key-rate durations must sum to modified duration')
        result.append(p)
    return result


def validate_history(rows):
    from datetime import date
    if len(rows) < 260:
        raise ValueError('At least 260 factor observations are required')
    previous, result = None, []
    for row in rows:
        try:
            day = date.fromisoformat(row['date'])
        except (KeyError, TypeError, ValueError):
            raise ValueError('Invalid or missing ISO date') from None
        if previous is not None and day <= previous:
            raise ValueError('Factor dates must be unique and strictly increasing')
        previous = day
        out = {'date': day.isoformat()}
        for key in FACTORS:
            if key not in row:
                raise ValueError(f'Missing factor: {key}')
            out[key] = finite(row[key], key)
        if out['equity_return'] <= -1 or out['fx_return'] <= -1:
            raise ValueError('Simple returns must exceed -100%')
        result.append(out)
    return result


def load_inputs(folder):
    folder = Path(folder)
    def read(name):
        with (folder / name).open(newline='', encoding='utf-8') as f:
            return list(csv.DictReader(f))
    return validate_positions(read('positions.csv')), validate_history(read('factors.csv'))


def position_pnl(position, shock):
    value = position['market_value']
    if position['asset'] == 'equity':
        return value * shock['equity_return']
    if position['asset'] == 'fx':
        return value * shock['fx_return']
    if all(f'krd_{t}' in position for t in TENORS):
        return -value * sum(position[f'krd_{t}'] * shock.get(f'yield_{t}_bp', shock.get('yield_bp', 0)) / 10000 for t in TENORS)
    # Legacy direct-function example; loaded v3 bonds always use key-rate durations.
    dy = shock['yield_bp'] / 10000
    return value * (-position['duration'] * dy + .5 * position['convexity'] * dy * dy)


def portfolio_pnl(positions, shock):
    return sum(position_pnl(p, shock) for p in positions)


def tail_risk(losses, confidence=.99):
    """Empirical inverse-CDF VaR; ES uses exactly (1-alpha) probability mass.

    A fractional boundary observation avoids over-counting tied quantiles.
    Losses are signed; negative risk estimates are not floored to zero.
    """
    if not .5 < confidence < 1:
        raise ValueError('Confidence must be between 0.5 and 1, exclusively')
    if not losses or not all(math.isfinite(x) for x in losses):
        raise ValueError('Loss samples must be nonempty and finite')
    ordered = sorted(losses)
    n = len(ordered)
    var = ordered[math.ceil(confidence * n) - 1]
    mass = (1 - confidence) * n
    # Remove floating-point noise at exact integer probability masses.
    if math.isclose(mass, round(mass), abs_tol=1e-10):
        mass = float(round(mass))
    whole = int(mass)
    tail = sorted(losses, reverse=True)
    total = sum(tail[:whole])
    if mass > whole:
        total += (mass - whole) * tail[whole]
    return {'var': var, 'es': total / mass, 'tail_observations': mass}


def backtest(losses, dates, confidence=.99, window=250):
    """Fixed-book hypothetical P&L backtest. Day t excluded from its forecast."""
    if window < 2 or len(losses) <= window or len(losses) != len(dates):
        raise ValueError('Backtest needs matching dates and more observations than its window')
    rows = []
    for t in range(window, len(losses)):
        forecast = tail_risk(losses[t-window:t], confidence)['var']
        rows.append({'date': dates[t], 'loss': losses[t], 'var': forecast,
                     'breach': losses[t] > forecast})
    n, x = len(rows), sum(r['breach'] for r in rows)
    p, observed = 1-confidence, x/len(rows)
    null_ll = x*math.log(p) + (n-x)*math.log1p(-p)
    fitted_ll = (x*math.log(observed) if x else 0) + ((n-x)*math.log1p(-observed) if x < n else 0)
    lr = max(0., 2*(fitted_ll-null_ll))
    from .diagnostics import exception_diagnostics
    diagnostic = exception_diagnostics([r['breach'] for r in rows], lr)
    # Survival probability of chi-square(1); asymptotic diagnostic only.
    return {'rows': rows, 'exceptions': x, 'observations': n,
            'expected_exceptions': n*p, 'exception_rate': observed,
            'kupiec_lr': lr, 'kupiec_p_value': math.erfc(math.sqrt(lr/2)), 'window': window, **diagnostic}


def analyze(positions, history, confidence=.99, scale=1., custom=None):
    scale = finite(scale, 'Exposure scale')
    if not .1 <= scale <= 3:
        raise ValueError('Exposure scale must be between 0.1 and 3')
    book = [{**p, 'market_value': p['market_value']*scale} for p in positions]
    losses = [-portfolio_pnl(book, s) for s in history]
    risk = tail_risk(losses[-250:], confidence)
    from .diagnostics import risk_intervals
    risk['intervals'] = risk_intervals(losses[-250:], confidence, tail_risk)
    normal_var = mean(losses[-250:]) + NormalDist().inv_cdf(confidence)*stdev(losses[-250:])
    scenarios = dict(SCENARIOS)
    if custom is not None:
        if 'yield_bp' in custom and not any(f'yield_{t}_bp' in custom for t in TENORS):
            custom = parallel(custom['equity_return'], custom['yield_bp'], custom['fx_return'])
        validated = {key: finite(custom[key], key) for key in FACTORS}
        if not -.6 <= validated['equity_return'] <= .6 or not -.4 <= validated['fx_return'] <= .4 or any(not -300 <= validated[f'yield_{t}_bp'] <= 300 for t in TENORS):
            raise ValueError('Custom shock is outside supported demo range')
        scenarios['Custom scenario'] = validated
    stress = []
    for name, shock in scenarios.items():
        contributions = [{'name': p['name'], 'asset': p['asset'], 'pnl': position_pnl(p, shock)} for p in book]
        stress.append({'name': name, 'shock': shock, 'pnl': sum(p['pnl'] for p in contributions), 'contributions': contributions})
    worst = min(stress, key=lambda s:s['pnl'])
    limits = [
        {'name': '1-day historical VaR', 'value': risk['var'], 'limit': 200000},
        {'name': 'Worst scenario loss', 'value': max(0, -worst['pnl']), 'limit': 1500000},
        {'name': 'Gross exposure', 'value': sum(abs(p['market_value']) for p in book), 'limit': 15000000},
    ]
    for row in limits:
        row['utilization'] = row['value']/row['limit']
        row['status'] = 'BREACH' if row['value'] > row['limit'] else 'WITHIN'
    controls = [
        {'check': 'Position IDs unique; schema and asset types valid', 'status': 'PASS'},
        {'check': 'Numeric values finite; bond sensitivities nonnegative', 'status': 'PASS'},
        {'check': 'Factor dates unique and strictly increasing', 'status': 'PASS'},
        {'check': 'Minimum history for rolling backtest available', 'status': 'PASS'},
        {'check': 'Dataset provenance is shown below; no live freshness guarantee', 'status': 'INFO'},
    ]
    input_hash = hashlib.sha256(json.dumps({'positions': positions, 'history': history}, sort_keys=True).encode()).hexdigest()
    return {'confidence': confidence, 'scale': scale, 'positions': book, 'risk': risk,
            'normal_var': normal_var, 'losses': losses[-250:], 'scenarios': stress,
            'worst_scenario': worst['name'], 'limits': limits, 'controls': controls,
            'backtest': backtest(losses, [r['date'] for r in history], confidence),
            'as_of': history[-1]['date'], 'history_count': len(history), 'input_sha256': input_hash,
            'gross_exposure': sum(abs(p['market_value']) for p in book),
            'net_exposure': sum(p['market_value'] for p in book)}
