"""Prioritize local recipes for official web review; never approve nutrition."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = ROOT / 'data/recipes.json'
    recipes = json.loads(source.read_text(encoding='utf-8'))
    historical = {r['recipe_id'] for r in json.loads(
        (ROOT / 'data/recipe_serving_menus.json').read_text(encoding='utf-8'))}
    rows = []
    for recipe in recipes:
        marker = re.search(r'\[\s*1\s*인분\s*\]', recipe['ingredients_text'])
        weight = recipe['nutrition_raw'].get('INFO_WGT', '').strip()
        priority = 1 if marker else 2 if weight else 3
        rows.append(dict(recipe_id=recipe['recipe_id'], name=recipe['name'],
                         review_priority=priority,
                         ingredient_serving_marker=marker.group() if marker else None,
                         weight_raw=weight or None,
                         historical_pdf_match=recipe['recipe_id'] in historical,
                         web_basis_status='unverified', calculation_allowed=False,
                         grams_conversion_allowed=False))
    rows.sort(key=lambda r: (r['review_priority'], int(r['recipe_id'])))
    report = dict(input_path='data/recipes.json',
                  input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  recipe_count=len(rows),
                  ingredient_serving_marker_count=sum(r['ingredient_serving_marker'] is not None for r in rows),
                  weight_present_count=sum(r['weight_raw'] is not None for r in rows),
                  newly_verified_count=0,
                  limitation='Review priority only. Ingredient servings and INFO_WGT do not establish nutrient denominator or weight unit.',
                  recipes=rows)
    (ROOT / 'data/recipe_web_review.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Reviewed {len(rows)} recipes; newly verified: 0')


if __name__ == '__main__':
    main()
