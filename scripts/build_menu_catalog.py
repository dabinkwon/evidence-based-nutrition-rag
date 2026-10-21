"""Build reviewable recipe/food links; no name match is nutrition verification."""
import argparse
import csv
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import time

from collect_nutrition import ROOT, key_from_env, request_page, items_from, normalize, write_json


def name_key(value):
    return re.sub(r'[\W_]+', '', value)


def candidates(recipe, foods):
    name = name_key(recipe['name'])
    matches = []
    for food in foods:
        other = name_key(food['name'])
        exact = name == other
        contains = min(len(name), len(other)) >= 3 and (other in name or name in other)
        if not (exact or contains):
            continue
        matches.append(dict(food_id=food['food_id'], food_name=food['name'],
                            relation='exact_name' if exact else 'name_contains',
                            name_similarity=round(SequenceMatcher(None, name, other).ratio(), 3),
                            status='needs_review',
                            reason='이름 기반 후보. 재료·조리 상태·영양 기준량의 일치 여부는 미확인.'))
    matches.sort(key=lambda x: (x['relation'] == 'exact_name', x['name_similarity']), reverse=True)
    # Similarity is a string metric, not probability or nutrition accuracy.
    return matches[:3]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--enrich', action='store_true', help='Fetch up to 2000 source rows separately')
    args = parser.parse_args()
    foods = json.loads((ROOT / 'data/foods.json').read_text(encoding='utf-8'))
    extra = ROOT / 'data/foods_extended.json'
    if args.enrich:
        key = key_from_env()
        pool = {f['food_id']: f for f in foods}
        raw = ROOT / 'data/raw/matching'
        raw.mkdir(parents=True, exist_ok=True)
        for page in range(1, 21):
            payload, body = request_page(key, page, 100)
            # Prevent any echoed credential from entering saved artifacts.
            if key in json.dumps(payload):
                raise RuntimeError('Credential in response; refused to save.')
            write_json(raw / f'nutrition_{page:03}.json', payload)
            for item in items_from(body):
                row = normalize(item)
                if (row['data_group'] == '음식' and row['food_id'] and row['name']
                    and row['basis_amount'] and all(row[k] is not None for k in
                        ('energy_kcal', 'protein_g', 'fat_g', 'carbohydrate_g'))):
                    pool[row['food_id']] = row
            print(f'Nutrition page {page}: {len(pool)} valid food records')
            time.sleep(0.5)
        write_json(extra, list(pool.values()))
    if extra.exists():
        foods = list({f['food_id']: f for f in foods + json.loads(extra.read_text(encoding='utf-8'))}.values())
    recipes = json.loads((ROOT / 'data/recipes.json').read_text(encoding='utf-8'))
    menus, links = [], []
    for recipe in recipes:
        found = candidates(recipe, foods)
        links.extend(dict(recipe_id=recipe['recipe_id'], recipe_name=recipe['name'], **x) for x in found)
        menus.append(dict(menu_id='recipe:' + recipe['recipe_id'], recipe_id=recipe['recipe_id'],
                          name=recipe['name'], category=recipe['category'],
                          ingredients_text=recipe['ingredients_text'], steps=recipe['steps'],
                          source_url=recipe['source_url'], candidate_food_ids=[x['food_id'] for x in found],
                          nutrition_food_id=None, matching_status='needs_review' if found else 'unmatched',
                          ingredients_review_status='unreviewed', nutrition_ready=False))
    write_json(ROOT / 'data/menu_catalog.json', menus)
    write_json(ROOT / 'data/recipe_food_candidates.json', links)
    with (ROOT / 'data/recipe_food_candidates.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['recipe_id','recipe_name','food_id','food_name',
                                              'relation','name_similarity','status','reason'])
        writer.writeheader()
        writer.writerows(links)
    report = dict(date='2026-10-21', food_count=len(foods), menu_count=len(menus),
                  menus_with_candidates=sum(bool(m['candidate_food_ids']) for m in menus),
                  exact_name_candidates=sum(x['relation']=='exact_name' for x in links),
                  candidate_pairs=len(links), verified_links=0, nutrition_ready=0,
                  policy='Name similarity is not nutritional equivalence. All links require review.',
                  original_files_preserved=['data/foods.json','data/recipes.json'])
    write_json(ROOT / 'data/matching_report.json', report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except RuntimeError as exc:
        print(str(exc))
        raise SystemExit(1)
    except Exception as exc:
        # Network exceptions may contain credential URLs; never emit details.
        print(f'Catalog build failed ({type(exc).__name__}); details hidden.')
        raise SystemExit(1)
