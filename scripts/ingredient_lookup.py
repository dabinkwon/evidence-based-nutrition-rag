"""Conservative ingredient candidate lookup; never substitute dish nutrients."""
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
ALIASES={'칵테일새우':'새우','달걀':'달걀','계란':'달걀','무염버터':'버터','다진 마늘':'마늘'}
TERMS=('연두부','순두부','두부','달걀','계란','새우','시금치','생크림','버터','설탕','우유','당근','양파','마늘')


def nutrition_lookup_names(question, recipe):
    """Separate named ingredient facts from nutrient-qualified recommendations."""
    if not any(t in question for t in ('영양','성분','단백질','탄수화물','나트륨','칼로리','열량','지방')):
        return []
    if any(t in question for t in ('추천','찾아','들어간','들어있는','고단백','많은','높은','이상','이하','미만','초과','저염','저지방')):
        return []
    names=query_ingredients(question,recipe)
    if names:
        return names
    # Preserve an unfamiliar ingredient name, rather than searching dish values
    # or silently replacing cherry tomato with another tomato variety.
    name=re.split(r'영양|성분|단백질|탄수화물|나트륨|칼로리|열량|지방',question,maxsplit=1)[0].strip()
    name=re.sub(r'(의|에는|은|는|을|를)$','',name).strip()
    if name and not any(t in name for t in ('요리','음식','메뉴')):
        return [name]
    return []


def recipe_ingredients(text):
    names=[]
    for part in re.split(r'[,\n]',text):
        match=re.search(r'([가-힣][가-힣 ]*?)\s*[(（]?\s*\d+(?:\.\d+)?\s*(?:g|ml|mL)\b',part)
        if match:
            name=match[1].strip().split()[-1]
            names.append(name)
    return list(dict.fromkeys(names))


def query_ingredients(question,recipe):
    if any(term in question for term in ('그 재료','재료들','재료의','재료 영양','재료별')):
        return recipe_ingredients(recipe['ingredients_text'])
    # Longest terms first: 연두부 must not silently become generic 두부.
    found=[term for term in TERMS if term in question]
    return [t for t in found if not any(t!=other and t in other for other in found)]


def lookup(names, records=None):
    if records is None:
        path=ROOT/'data/ingredients.json'
        records=json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    rows=[];missing=[]
    for name in names:
        term=ALIASES.get(name,name)
        hits=[f for f in records if '원재료' in str(f.get('data_group')) and term in f['name']]
        if not hits:
            missing.append(name)
        for f in hits[:5]:
            row={'레시피 재료':name,'영양 데이터 후보':f['name'],'연결 상태':'종류·조리 상태 확인 필요',
                 '기준량':f['basis_label'],'출처':f['source_url']}
            for label,key,unit in [('열량','energy_kcal','kcal'),('단백질','protein_g','g'),('탄수화물','carbohydrate_g','g'),('지방','fat_g','g'),('나트륨','sodium_mg','mg')]:
                row[f'{label} ({unit})']=str(f[key]) if f.get(key) is not None else '미제공'
            rows.append(row)
    answer='재료별 영양 데이터 후보입니다. 표의 식품 종류·조리 상태와 기준량을 확인해 주세요. 이름이 비슷해도 해당 레시피의 정확한 재료값으로 확정한 것은 아닙니다.' if rows else '현재 확보한 원재료 영양 데이터에서 찾지 못했습니다. 조리된 음식의 영양값으로 대신하지 않습니다.'
    if missing:
        answer+='\n\n아직 데이터가 없는 재료: '+', '.join(missing)
    if rows:
        answer+='\n\n표의 수치는 표시된 기준량에 대한 값이며 레시피 사용량으로 환산하거나 합산하지 않았습니다.'
    return dict(answer=answer,citations=[],nutrition_rows=rows)
