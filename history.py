"""Explicit level-to-factor conversion; no fill, interpolation or implicit joins."""
import argparse
import csv
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from .engine import finite, validate_history, validate_positions, load_inputs

RATE_COLUMNS = ('yield_2y_pct','yield_5y_pct','yield_10y_pct')


def read_csv(path):
    with Path(path).open(newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f))


def levels_to_factors(rows, expected_dates, multi_asset=False):
    """Rates: percent-point levels -> basis-point changes.
    Equity: P(t)/P(t-1)-1; EURUSD: USD per EUR -> same simple-return formula.
    Expected dates must list the explicitly chosen common observation calendar.
    Every expected date must exist exactly once; input order must already be ascending.
    """
    required=['date',*RATE_COLUMNS]+(['equity_level','eurusd'] if multi_asset else [])
    if len(rows)<2:raise ValueError('At least two level observations are required')
    expected=list(expected_dates)
    if not expected or expected!=sorted(set(expected)):
        raise ValueError('Expected calendar must be nonempty, unique and increasing')
    for day in expected:
        try:
            if date.fromisoformat(day).isoformat()!=day:raise ValueError('Noncanonical date')
        except (TypeError,ValueError):raise ValueError('Calendar dates must be ISO YYYY-MM-DD') from None
    if any(not isinstance(r.get('date'),str) or not r['date'].strip() for r in rows):
        raise ValueError('Every level row needs a nonempty ISO date')
    actual=[r.get('date') for r in rows]
    if len(set(actual))!=len(actual):raise ValueError('Duplicate level dates')
    if actual!=expected:
        missing=sorted(set(expected)-set(actual));extra=sorted(set(actual)-set(expected))
        raise ValueError(f'Level dates must exactly match the ordered common calendar; missing={missing[:5]}, extra={extra[:5]}')
    clean=[]
    for row in rows:
        day=date.fromisoformat(row['date'])
        if day.weekday()>=5:raise ValueError('Weekend observations are not supported by this daily session calendar')
        out={'date':day.isoformat()}
        for key in required[1:]:
            if key not in row or str(row[key]).strip() in ('','N/A','NA','.'):
                raise ValueError(f'Missing {key} on {day}; no forward filling is permitted')
            out[key]=finite(row[key],key)
        if multi_asset and (out['equity_level']<=0 or out['eurusd']<=0):
            raise ValueError('Equity and FX levels must be positive')
        clean.append(out)
    factors=[]
    for previous,current in zip(clean,clean[1:]):
        if (date.fromisoformat(current['date'])-date.fromisoformat(previous['date'])).days>7:
            raise ValueError('Observation gap exceeds seven calendar days; check source/calendar')
        f={'date':current['date'],'equity_return':0.,'fx_return':0.}
        for tenor in ('2y','5y','10y'):
            key=f'yield_{tenor}_pct'
            f[f'yield_{tenor}_bp']=round((current[key]-previous[key])*100,10)
        if multi_asset:
            f['equity_return']=current['equity_level']/previous['equity_level']-1
            f['fx_return']=current['eurusd']/previous['eurusd']-1
        factors.append(f)
    return factors


def load_dataset(folder, mode):
    folder=Path(folder)
    if mode=='synthetic':
        positions,history=load_inputs(folder)
        return positions,history,{'label':'Synthetic multi-asset','kind':'synthetic','source':'Seeded sample generator (42 / 173)',
                                 'scope':'Equity, bonds and EUR cash. All factor observations are synthetic.',
                                 'calendar':'Weekdays only; not an exchange calendar.'}
    if mode=='treasury':
        positions=validate_positions([p for p in read_csv(folder/'positions.csv') if p['asset']=='bond'])
        rows=read_csv(folder/'treasury_levels.csv')
        calendar=[r['date'] for r in read_csv(folder/'treasury_calendar.csv')]
        history=validate_history(levels_to_factors(rows,calendar))
        metadata=json.loads((folder/'treasury_provenance.json').read_text())
        digest=hashlib.sha256((folder/'treasury_levels.csv').read_bytes()).hexdigest()
        if digest!=metadata['levels_sha256']:raise ValueError('Bundled Treasury data hash mismatch; restore the source snapshot')
        return positions,history,metadata
    if mode=='imported':
        manifest=folder/'imported'/'manifest.json'
        if not manifest.exists():raise ValueError('No imported dataset. See docs/HISTORICAL_DATA.md for the CSV import command.')
        meta=json.loads(manifest.read_text())
        for filename,key in [('levels.csv','levels_sha256'),('calendar.csv','calendar_sha256')]:
            if hashlib.sha256((manifest.parent/filename).read_bytes()).hexdigest()!=meta[key]:
                raise ValueError(f'Imported {filename} changed after validation; import it again')
        rows=read_csv(manifest.parent/'levels.csv');calendar=[r['date'] for r in read_csv(manifest.parent/'calendar.csv')]
        history=validate_history(levels_to_factors(rows,calendar,True))
        positions=validate_positions(read_csv(folder/'positions.csv'))
        return positions,history,meta
    raise ValueError('Unknown dataset')


def main():
    parser=argparse.ArgumentParser(description='Validate and import permissioned daily equity, EURUSD and Treasury levels')
    parser.add_argument('--levels',required=True,type=Path)
    parser.add_argument('--calendar',required=True,type=Path,help='CSV date column defining common observation dates')
    parser.add_argument('--source-note',required=True,help='Provider, series identifiers, download date and attribution for every series')
    parser.add_argument('--usage-basis',required=True,help='Public-domain basis, licence, or permission that allows your intended use')
    parser.add_argument('--equity-convention',required=True,choices=['price-return','total-return'])
    args=parser.parse_args()
    rows=read_csv(args.levels);calendar=[r['date'] for r in read_csv(args.calendar)]
    history=validate_history(levels_to_factors(rows,calendar,True))
    if not args.source_note.strip() or not args.usage_basis.strip():parser.error('Source and usage basis must be nonempty')
    out=Path(__file__).resolve().parents[1]/'data'/'imported';out.mkdir(exist_ok=True)
    # Validate fully before overwriting the imported dataset. Write manifest last.
    levels_bytes=args.levels.read_bytes();calendar_bytes=args.calendar.read_bytes()
    metadata={'label':'Imported multi-asset','kind':'historical_import','source':args.source_note,
              'usage_basis':args.usage_basis,'equity_convention':args.equity_convention,
              'scope':'User-supplied observations; provenance and permission declared by importer, not independently verified.',
              'calendar':'Explicit common observation calendar; no missing-value fill.',
              'imported_utc':datetime.now(timezone.utc).isoformat(),'observations':len(history),
              'levels_sha256':hashlib.sha256(levels_bytes).hexdigest(),'calendar_sha256':hashlib.sha256(calendar_bytes).hexdigest()}
    (out/'levels.csv').write_bytes(levels_bytes);(out/'calendar.csv').write_bytes(calendar_bytes)
    (out/'manifest.json').write_text(json.dumps(metadata,indent=2))
    print(f'Validated {len(history)} common-session factor observations. Select Imported multi-asset in the dashboard.')

if __name__=='__main__':main()
