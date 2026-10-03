"""Seeded synthetic daily factor history, with correlated market shocks."""
import csv
import random
from datetime import date, timedelta
from pathlib import Path


def generate(folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    positions = [
        ('EQ1', 'Global equity basket', 'equity', 5000000, 0, 0),
        ('EQ2', 'Equity index hedge', 'equity', -1500000, 0, 0),
        ('BD1', 'Treasury portfolio', 'bond', 4000000, 6.2, 46),
        ('BD2', 'Short-duration bonds', 'bond', 2000000, 2.1, 6),
        ('FX1', 'EUR cash exposure', 'fx', 1500000, 0, 0),
    ]
    with (folder/'positions.csv').open('w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['id', 'name', 'asset', 'market_value', 'duration', 'convexity', 'krd_2y', 'krd_5y', 'krd_10y'])
        for p in positions:
            krd = {'BD1':(.4,1.8,4.),'BD2':(1.6,.4,.1)}.get(p[0],(0,0,0))
            w.writerow((*p[:5], 0, *krd))
    rng = random.Random(42)
    curve_rng = random.Random(173)
    day = date(2023, 1, 2)
    with (folder/'factors.csv').open('w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['date', 'equity_return', 'yield_2y_bp', 'yield_5y_bp', 'yield_10y_bp', 'fx_return'])
        for i in range(750):
            while day.weekday() >= 5:
                day += timedelta(days=1)
            a, b, c = (rng.gauss(0, 1) for _ in range(3))
            regime = 1.8 if 450 <= i < 530 else 1.
            equity = .00015 + .011*a*regime
            rate = (2*a + 4.5*b)*regime
            fx = (.0025*a + .005*c)*regime
            if i in (270, 470, 505, 650, 705):
                equity -= .06
                rate -= 18
                fx -= .018
            rate = round(rate,6)
            slope, bend = curve_rng.gauss(0,1.7), curve_rng.gauss(0,.8)
            w.writerow([day.isoformat(), f'{equity:.8f}', f'{rate-slope:.6f}', f'{rate+bend:.6f}', f'{rate+slope:.6f}', f'{fx:.8f}'])
            day += timedelta(days=1)

if __name__ == '__main__':
    generate(Path(__file__).resolve().parents[1]/'data')
