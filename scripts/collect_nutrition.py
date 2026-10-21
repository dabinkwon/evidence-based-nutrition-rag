"""Collect public nutrition data without logging credentials (Python stdlib only)."""
import argparse
import csv
import json
import math
import os
from pathlib import Path
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlencode, unquote
from urllib.request import urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = 'https://apis.data.go.kr/1471000/FoodNtrCpntDbInfo03/getFoodNtrCpntDbInq03'
SOURCE = 'https://www.data.go.kr/data/15127578/openapi.do'
FIELDS = {'energy_kcal': 'AMT_NUM1', 'protein_g': 'AMT_NUM3',
          'fat_g': 'AMT_NUM4', 'carbohydrate_g': 'AMT_NUM6',
          'sugars_g': 'AMT_NUM7', 'fiber_g': 'AMT_NUM8', 'sodium_mg': 'AMT_NUM13'}


def key_from_env():
    key = os.environ.get('FOOD_NUTRITION_API_KEY', '')
    if not key and (ROOT / '.env').exists():
        for line in (ROOT / '.env').read_text(encoding='utf-8-sig').splitlines():
            name, sep, value = line.strip().partition('=')
            if sep and name.strip() == 'FOOD_NUTRITION_API_KEY':
                key = value.strip().strip('\"\'')
    if not key:
        raise RuntimeError('FOOD_NUTRITION_API_KEY is missing.')
    return unquote(key)


def request_page(key, page, size, category=None):
    params = dict(serviceKey=key, pageNo=page, numOfRows=size, type='json')
    if category:
        params['FOOD_CAT1_NM'] = category
    for attempt in range(3):
        try:
            with urlopen(ENDPOINT + '?' + urlencode(params), timeout=40) as response:
                payload = response.read().decode('utf-8-sig')
            try:
                data = json.loads(payload)
            except ValueError:
                # Never emit a server response that might echo the request URL/key.
                raise RuntimeError('API returned non-JSON; check approval and credentials.') from None
            root = data.get('response', data)
            header = root.get('header', {})
            if str(header.get('resultCode')) not in ('00', '0'):
                code = str(header.get('resultCode', 'unknown'))
                if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', code):
                    code = 'unknown'
                raise RuntimeError('API result code: ' + code)
            return data, root.get('body', {})
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise RuntimeError(f'HTTP status {exc.code}; request URL hidden.') from None
        except (URLError, TimeoutError):
            if attempt == 2:
                raise RuntimeError('Network connection failed; request URL hidden.') from None
        time.sleep(2 ** attempt)


def items_from(body):
    items = body.get('items', [])
    if isinstance(items, dict):
        items = items.get('item', [])
    if isinstance(items, dict):
        items = [items]
    return items or []


def number(value):
    try:
        result = float(str(value).replace(',', '').strip())
        return result if math.isfinite(result) and result >= 0 else None
    except (ValueError, TypeError):
        return None


def normalize(item):
    basis = str(item.get('SERVING_SIZE', '')).strip()
    match = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(g|ml|mL)', basis)
    row = dict(food_id=item.get('FOOD_CD'), name=item.get('FOOD_NM_KR'),
               category=item.get('FOOD_CAT1_NM'), data_group=item.get('DB_GRP_NM'),
               reference_food=item.get('FOOD_REF_NM'), basis_label=basis,
               basis_amount=float(match[1]) if match else None,
               basis_unit=match[2].lower() if match else None,
               serving_reference=item.get('DISH_ONE_SERVING'),
               source_name=item.get('SUB_REF_NAME'), source_url=SOURCE,
               research_date=item.get('RESEARCH_YMD'), update_date=item.get('UPDATE_DATE'))
    row.update({name: number(item.get(field)) for name, field in FIELDS.items()})
    return row


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--probe', action='store_true')
    parser.add_argument('--category')
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000:
        raise RuntimeError('limit must be between 1 and 1000.')
    key = key_from_env()
    raw_dir = ROOT / 'data' / 'raw'
    raw_dir.mkdir(parents=True, exist_ok=True)
    collected, seen, rejected = [], set(), 0
    size = 100
    for page in range(1, 21):
        data, body = request_page(key, page, 3 if args.probe else size, args.category)
        items = items_from(body)
        if args.probe:
            print(json.dumps({'totalCount': body.get('totalCount'), 'samples': [
                {k: v for k, v in i.items() if k in ['FOOD_CD', 'FOOD_NM_KR', 'DB_GRP_NM',
                 'FOOD_CAT1_NM', 'FOOD_OR_NM', 'SERVING_SIZE', *FIELDS.values()]}
                for i in items]}, ensure_ascii=False, indent=2))
            return
        write_json(raw_dir / f'nutrition_page_{page:03}.json', data)
        for item in items:
            row = normalize(item)
            valid = (row['food_id'] and row['name'] and row['basis_amount']
                     and all(row[k] is not None for k in
                             ('energy_kcal', 'protein_g', 'fat_g', 'carbohydrate_g')))
            if not valid:
                rejected += 1
                continue
            if row['food_id'] not in seen:
                seen.add(row['food_id'])
                collected.append(row)
            if len(collected) == args.limit:
                break
        print(f'Page {page}: selected {len(collected)}, rejected {rejected}')
        if len(collected) >= args.limit or not items or page * size >= int(body.get('totalCount', 0)):
            break
        time.sleep(0.5)
    if len(collected) < args.limit:
        raise RuntimeError(f'Only {len(collected)} valid records found; inspect raw data.')
    write_json(ROOT / 'data' / 'foods.json', collected)
    with (ROOT / 'data' / 'foods.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(collected[0]))
        writer.writeheader()
        writer.writerows(collected)
    write_json(ROOT / 'data' / 'collection_report.json', dict(
        collected_at=datetime.now(timezone.utc).isoformat(), endpoint=ENDPOINT,
        source_url=SOURCE, count=len(collected), rejected=rejected, category=args.category,
        selection='API order; unique food ID; positive g/ml basis; nonnegative energy and macros',
        missing_values='null means missing/unparseable, never assumed zero',
        license='Portal states no restrictions; checked 2026-10-21',
        limitations='Initial dataset, not a representative menu selection. Recipe/ingredient mapping unverified.'))
    print(f'Saved {len(collected)} foods to data/foods.json and data/foods.csv')


if __name__ == '__main__':
    try:
        main()
    except RuntimeError as exc:
        print(str(exc))
        raise SystemExit(1)
