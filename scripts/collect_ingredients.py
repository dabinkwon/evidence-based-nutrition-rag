"""Collect ingredient-name nutrition candidates separately from prepared dishes."""
import json
import time
import math
import argparse
from datetime import datetime, timezone
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from collect_nutrition import ROOT, key_from_env, request_page, items_from, normalize, write_json

TERMS=['두부','연두부','달걀','새우','시금치','생크림','버터','설탕','우유','당근','양파','마늘']


def collect_term(index,term,key):
    raw_dir=ROOT/'data/raw/ingredients'
    raw_dir.mkdir(parents=True,exist_ok=True)
    try:
        first_path=raw_dir/f'query_{index:02}.json'
        if first_path.exists():
            payload=json.loads(first_path.read_text(encoding='utf-8'))
            root=payload.get('response',payload)
            body=root.get('body',{})
        else:
            if key is None:
                return [],dict(term=term,status='not_collected')
            payload,body=request_page(key,1,100,filters={'FOOD_NM_KR':term})
        if key and key in json.dumps(payload,ensure_ascii=False):
            raise RuntimeError('Credential echo detected; refused to save')
        write_json(raw_dir/f'query_{index:02}.json',payload)
        rows=items_from(body)
        last=max(1,math.ceil(int(body.get('totalCount',0))/100))
        missing_pages=[]
        for page in sorted({max(1,last-1),last}-{1}):
            page_path=raw_dir/f'query_{index:02}_page_{page}.json'
            if page_path.exists():
                extra=json.loads(page_path.read_text(encoding='utf-8'))
                extra_body=extra.get('response',extra).get('body',{})
            else:
                if key is None:
                    missing_pages.append(page)
                    continue
                extra,extra_body=request_page(key,page,100,filters={'FOOD_NM_KR':term})
                if key in json.dumps(extra,ensure_ascii=False):
                    raise RuntimeError('Credential echo detected')
                write_json(page_path,extra)
                time.sleep(1)
            rows+=items_from(extra_body)
        report=dict(term=term,total=body.get('totalCount'),returned=len(rows),status='partial' if missing_pages else 'complete',missing_pages=missing_pages,
                    groups=dict(Counter(str(r.get('DB_GRP_NM')) for r in rows)))
        records={}
        for item in rows:
            row=normalize(item)
            # Raw-food classification only. Other groups are not ingredient proof.
            if '원재료' in str(row['data_group']) and row['food_id'] and row['basis_amount']:
                row['lookup_term']=term
                records[row['food_id']]=row
        print(term,len(records),'ingredient candidates',flush=True)
        time.sleep(1)
        return list(records.values()),report
    except Exception:
        return [],dict(term=term,status='failed',reason='Request failed; details hidden')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--offline',action='store_true',help='Normalize cached responses only')
    args=parser.parse_args()
    key=None if args.offline else key_from_env()
    records={}
    queries=[]
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures=[executor.submit(collect_term,i,t,key) for i,t in enumerate(TERMS)]
        for future in futures:
            rows,report=future.result()
            records.update({r['food_id']:r for r in rows})
            queries.append(report)
    if not records:
        raise RuntimeError('No ingredient records; existing data preserved')
    write_json(ROOT/'data/ingredients.json',list(records.values()))
    write_json(ROOT/'data/ingredient_collection_report.json',dict(collected_at=datetime.now(timezone.utc).isoformat(),queries=queries,count=len(records),
        limitation='Ingredient-name candidates, not automatically verified recipe ingredient equivalence. First and final two pages only; coverage incomplete.'))


if __name__=='__main__':
    try:
        main()
    except Exception:
        print('Ingredient collection failed; credential and request details hidden.')
        raise SystemExit(1)
