"""Persist an audit trail and export a reproducible analysis."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def save_run(result, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    summary = {'timestamp_utc': timestamp, 'model_version': '3.0.0',
               'data_type': 'synthetic', **result}
    with sqlite3.connect(folder/'audit.sqlite') as connection:
        connection.execute('CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY, timestamp_utc TEXT, input_sha256 TEXT, confidence REAL, scale REAL, result_json TEXT)')
        cursor = connection.execute('INSERT INTO runs (timestamp_utc,input_sha256,confidence,scale,result_json) VALUES (?,?,?,?,?)',
            (timestamp, result['input_sha256'], result['confidence'], result['scale'], json.dumps(summary)))
        run_id = cursor.lastrowid
    path = folder/f'run_{run_id}.json'
    path.write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return run_id, path
