"""Compare recipe API values with explicitly per-serving official PDF pages.

Requires pypdf (local install: python -m pip install --target .tools/pdf pypdf).
PDF must be downloaded separately; no credentials are used.
"""
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]

URL = 'https://www.foodsafetykorea.go.kr/upload/20170417/20170417053825_1492418305214.pdf'
FIELDS = {'INFO_ENG': ('열량', 'kcal'), 'INFO_CAR': ('탄수화물', 'g'),
          'INFO_PRO': ('단백질', 'g'), 'INFO_FAT': ('지방', 'g'), 'INFO_NA': ('나트륨', 'mg')}


def compact(value):
    return re.sub(r'\s+', '', value)


def main():
    path = ROOT / 'data/sources/samsam_01.pdf'
    if not path.exists():
        raise SystemExit('PDF removed by user request. Historical audit is preserved; no re-audit performed.')
    sys.path.insert(0, str(ROOT / '.tools/pdf'))
    from pypdf import PdfReader
    pages = [p.extract_text() or '' for p in PdfReader(path).pages]
    recipes = json.loads((ROOT / 'data/recipes.json').read_text(encoding='utf-8'))
    rows = []
    for recipe in recipes:
        row = dict(recipe_id=recipe['recipe_id'], name=recipe['name'], basis_status='unverified',
                   serving_weight_raw=recipe['nutrition_raw'].get('INFO_WGT', ''),
                   gram_conversion_ready=False, evidence=None)
        for index, text in enumerate(pages):
            flat = compact(text)
            if compact(recipe['name']) not in flat or '영양성분(1인분)' not in flat:
                continue
            values = {}
            for field, (label, unit) in FIELDS.items():
                found = re.search(label + r'([0-9]+(?:\.[0-9]+)?)' + unit, flat)
                values[field] = float(found[1]) if found else None
            match = all(values[k] is not None and str(recipe['nutrition_raw'].get(k,''))
                        and values[k] == float(recipe['nutrition_raw'][k]) for k in FIELDS)
            ingredient_lines = [compact(line) for line in recipe['ingredients_text'].splitlines()
                                if re.search(r'\d', line)]
            ingredient_match = bool(ingredient_lines) and all(line in flat for line in ingredient_lines)
            if match and ingredient_match:
                row.update(basis_status='verified_per_serving', basis_amount=1, basis_unit='serving',
                           nutrients={'energy_kcal':values['INFO_ENG'], 'carbohydrate_g':values['INFO_CAR'],
                                      'protein_g':values['INFO_PRO'], 'fat_g':values['INFO_FAT'],
                                      'sodium_mg':values['INFO_NA']},
                           evidence=dict(source_url=URL, pdf_page=index+1,
                                         method='Exact five nutrient values and all numeric ingredient lines match; explicit per-serving heading.',
                                         source_title='우리 몸이 원하는 삼삼한 밥상', checked_date='2026-10-21'))
                break
        rows.append(row)
    recipe_by_id = {r['recipe_id']:r for r in recipes}
    serving_menus = []
    for row in rows:
        if row['basis_status'] != 'verified_per_serving':
            continue
        recipe = recipe_by_id[row['recipe_id']]
        serving_menus.append(dict(menu_id='recipe:'+row['recipe_id'], recipe_id=row['recipe_id'],
                                  name=row['name'], category=recipe['category'],
                                  ingredients_text=recipe['ingredients_text'], steps=recipe['steps'],
                                  nutrition_source='recipe_pdf_verified', nutrition_source_id=row['recipe_id'],
                                  nutrition=row['nutrients'], basis_amount=1, basis_unit='serving',
                                  nutrition_basis_status=row['basis_status'], gram_conversion_ready=False,
                                  evidence=row['evidence'], ingredients_review_status='unreviewed',
                                  personalized_recommendation_ready=False))
    (ROOT / 'data/recipe_serving_menus.json').write_text(json.dumps(serving_menus, ensure_ascii=False, indent=2),encoding='utf-8')
    output = dict(checked_date='2026-10-21', source_url=URL,
                  source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  local_source='data/sources/samsam_01.pdf', source_page_count=len(pages),
                  recipe_count=len(rows), weight_present_count=sum(bool(x['serving_weight_raw']) for x in rows),
                  verified_per_serving_count=sum(x['basis_status']=='verified_per_serving' for x in rows),
                  gram_conversion_ready_count=0,
                  limitation='Per-serving document values only; not laboratory validation or verification of every recipe in COOKRCP01.',
                  recipes=rows)
    (ROOT / 'data/recipe_basis_audit.json').write_text(json.dumps(output, ensure_ascii=False, indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in output.items() if k!='recipes'},ensure_ascii=False))
    print('Verified:', [(x['recipe_id'],x['name'],x['evidence']['pdf_page']) for x in rows if x['evidence']])


if __name__ == '__main__':
    main()
