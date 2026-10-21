"""Collect COOKRCP01 recipes using stdlib; never print credential URLs."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'https://www.foodsafetykorea.go.kr/api/newDatasetDetail.do?svc_no=COOKRCP01'


def load_key():
    key = os.environ.get('FOOD_RECIPE_API_KEY', '')
    if not key:
        for line in (ROOT / '.env').read_text(encoding='utf-8-sig').splitlines():
            name, sep, value = line.partition('=')
            if sep and name.strip() == 'FOOD_RECIPE_API_KEY':
                key = value.strip().strip('\"\'')
    if not re.fullmatch(r'[A-Za-z0-9]+', key):
        raise RuntimeError('FOOD_RECIPE_API_KEY missing or invalid; value hidden.')
    return key


def fetch(key, start, end):
    url = f'https://openapi.foodsafetykorea.go.kr/api/{key}/COOKRCP01/json/{start}/{end}'
    for attempt in range(3):
        try:
            with urlopen(url, timeout=30) as response:
                text = response.read().decode('utf-8-sig')
            if key in text:
                raise RuntimeError('Response contains credential; refused to save.')
            try:
                payload = json.loads(text)
            except ValueError:
                raise RuntimeError('API returned non-JSON; response hidden.') from None
            body = payload.get('COOKRCP01', payload)
            code = str(body.get('RESULT', {}).get('CODE', 'unknown'))
            if code != 'INFO-000':
                safe_code = code if re.fullmatch(r'[A-Za-z0-9_-]{1,40}', code) else 'unknown'
                raise RuntimeError('Recipe API result: ' + safe_code)
            return payload, body
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise RuntimeError(f'HTTP status {exc.code}; URL hidden.') from None
        except (URLError, TimeoutError):
            if attempt == 2:
                raise RuntimeError('Network connection failed; URL hidden.') from None
        time.sleep(2 ** attempt)


def normalize(item):
    steps = [dict(number=i, text=item.get(f'MANUAL{i:02}', '').strip(),
                  image_url=item.get(f'MANUAL_IMG{i:02}', '').strip())
             for i in range(1, 21) if item.get(f'MANUAL{i:02}', '').strip()]
    return dict(recipe_id=item.get('RCP_SEQ', '').strip(), name=item.get('RCP_NM', '').strip(),
                category=item.get('RCP_PAT2', '').strip(), cooking_method=item.get('RCP_WAY2', '').strip(),
                ingredients_text=item.get('RCP_PARTS_DTLS', '').strip(), steps=steps,
                image_url=item.get('ATT_FILE_NO_MAIN', ''), tip=item.get('RCP_NA_TIP', ''),
                nutrition_raw={k: v for k, v in item.items() if k.startswith('INFO_')},
                nutrition_basis_status='unverified', nutrition_food_id=None,
                matching_status='unreviewed', source_name='식품의약품안전처 조리식품의 레시피 DB',
                source_url=SOURCE)


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000:
        raise RuntimeError('limit must be 1..1000')
    key = load_key()
    raw = ROOT / 'data' / 'raw' / 'recipes'
    raw.mkdir(parents=True, exist_ok=True)
    rows, seen, rejected = [], set(), 0
    for start in range(1, 2001, 100):
        payload, body = fetch(key, start, start + 99)
        write_json(raw / f'recipes_{start:04}_{start+99:04}.json', payload)
        items = body.get('row', [])
        for item in items:
            row = normalize(item)
            if not all([row['recipe_id'], row['name'], row['ingredients_text'], row['steps']]):
                rejected += 1
                continue
            if row['recipe_id'] in seen:
                continue
            rows.append(row)
            seen.add(row['recipe_id'])
            if len(rows) == args.limit:
                break
        print(f'Fetched range {start}-{start+99}; selected {len(rows)}; rejected {rejected}')
        if len(rows) >= args.limit or not items or start + 99 >= int(body['total_count']):
            break
        time.sleep(0.5)
    if len(rows) < args.limit:
        raise RuntimeError(f'Insufficient complete recipes: {len(rows)}; raw responses saved.')
    write_json(ROOT / 'data' / 'recipes.json', rows)
    flat = [{k: v for k, v in row.items() if k not in ('steps', 'nutrition_raw')} |
            {'instructions_text': '\n'.join(s['text'] for s in row['steps'])} for row in rows]
    with (ROOT / 'data' / 'recipes.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(flat[0]))
        writer.writeheader()
        writer.writerows(flat)
    report = dict(collected_at=datetime.now(timezone.utc).isoformat(), source_url=SOURCE,
                  service='COOKRCP01', total_available=int(body['total_count']), count=len(rows),
                  rejected=rejected, categories=dict(Counter(r['category'] for r in rows)),
                  selection='API order, unique recipe ID, nonempty name/ingredients/instructions',
                  license_status='Needs review before redistribution; official service page recorded.',
                  limitations='Nutrition basis and food mappings unverified; do not use recipe nutrition in calculations.')
    write_json(ROOT / 'data' / 'recipe_collection_report.json', report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except RuntimeError as exc:
        print(str(exc))
        raise SystemExit(1)
    except Exception as exc:
        print(f'Collection failed ({type(exc).__name__}); details hidden to protect credentials.')
        raise SystemExit(1)
