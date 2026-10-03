"""Run `python app.py`, then open http://127.0.0.1:8000."""
import argparse
import csv
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from risklens.engine import analyze, load_inputs, finite, validate_positions
from risklens.reporting import save_run

ROOT = Path(__file__).resolve().parent


def compute(params):
    confidence = float(params.get('confidence', ['.99'])[0])
    if confidence not in (.95, .975, .99):
        raise ValueError('Choose confidence 0.95, 0.975 or 0.99')
    scale = float(params.get('scale', ['1'])[0])
    custom = {'equity_return': float(params.get('equity', ['-20'])[0])/100,
              'yield_bp': float(params.get('rates', ['150'])[0]),
              'fx_return': float(params.get('fx', ['-8'])[0])/100}
    positions, history = load_inputs(ROOT/'data')
    baseline = analyze(positions, history, confidence, 1, custom)
    hedge = finite(params.get('hedge', ['1'])[0], 'Hedge multiplier')
    if not 0 <= hedge <= 3:
        raise ValueError('Hedge multiplier must be between 0 and 3')
    edited = []
    for position in positions:
        p = dict(position)
        value = finite(params.get('value_'+p['id'], [p['market_value']])[0], p['name'])
        if abs(value) > 50000000:
            raise ValueError('Individual exposures must be within +/- $50m')
        p['market_value'] = value
        if p['asset'] == 'equity' and value < 0:
            p['market_value'] *= hedge
        if p['market_value'] != 0:
            edited.append(p)
    edited = validate_positions(edited)
    result = analyze(edited, history, confidence, scale, custom)
    unhedged = [p for p in edited if not (p['asset'] == 'equity' and p['market_value'] < 0)]
    result['comparison'] = {'baseline_var': baseline['risk']['var'],
                            'baseline_es': baseline['risk']['es'],
                            'baseline_gross': baseline['gross_exposure'],
                            'var_change': result['risk']['var'] - baseline['risk']['var']}
    result['hedge_multiplier'] = hedge
    result['editable_positions'] = positions
    result['unhedged_var'] = analyze(unhedged, history, confidence, scale, custom)['risk']['var'] if unhedged else None
    return result


class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, content_type='application/json', filename=None):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ('/', '/index.html'):
            self.send(200, (ROOT/'web/index.html').read_bytes(), 'text/html; charset=utf-8')
            return
        if parsed.path not in ('/api/risk', '/api/export'):
            self.send(404, b'{"error":"Not found"}')
            return
        try:
            result = compute(parse_qs(parsed.query))
            if parsed.path == '/api/export':
                out = io.StringIO()
                writer = csv.writer(out)
                writer.writerow(['scenario', 'position', 'asset', 'pnl_usd', 'confidence', 'scale', 'input_sha256'])
                for scenario in result['scenarios']:
                    for p in scenario['contributions']:
                        writer.writerow([scenario['name'], p['name'], p['asset'], round(p['pnl'], 2), result['confidence'], result['scale'], result['input_sha256']])
                self.send(200, out.getvalue().encode(), 'text/csv; charset=utf-8', 'risklens_scenarios.csv')
            else:
                self.send(200, json.dumps(result, allow_nan=False).encode())
        except (ValueError, KeyError, OSError) as error:
            self.send(400, json.dumps({'error': str(error)}).encode())

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != '/api/save':
            self.send(404, b'{"error":"Not found"}')
            return
        # Local application: reject cross-origin browser writes.
        if self.headers.get('Origin') not in (None, f'http://{self.headers.get("Host")}'):
            self.send(403, b'{"error":"Cross-origin write rejected"}')
            return
        try:
            result = compute(parse_qs(parsed.query))
            run_id, path = save_run(result, ROOT/'reports')
            self.send(200, json.dumps({'run_id': run_id, 'file': path.name}).encode())
        except (ValueError, KeyError, OSError) as error:
            self.send(400, json.dumps({'error': str(error)}).encode())


def main():
    parser = argparse.ArgumentParser(description='RiskLens educational risk dashboard')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--report', action='store_true', help='Save a report and exit without serving')
    args = parser.parse_args()
    if args.report:
        result = compute({})
        run_id, path = save_run(result, ROOT/'reports')
        print(f'Saved run {run_id}: {path}')
        print(f'99% 1-day VaR: ${result["risk"]["var"]:,.0f}; ES: ${result["risk"]["es"]:,.0f}')
        return
    compute({})  # Validate inputs before opening the server.
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'RiskLens is ready: http://127.0.0.1:{args.port}', flush=True)
    print('Synthetic data | Ctrl+C to stop', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == '__main__':
    main()
