"""Structured recipe nutrition retrieval; no inferred serving sizes or LLM math."""
import math
import re


def protein_request(question):
    nutrient = '단백질' in question or '고단백' in question
    discovery = any(w in question for w in ('요리', '음식', '메뉴', '추천', '찾아'))
    if not nutrient or not discovery:
        return None
    if re.search(r'(이|선택한|선택된)\s*요리', question) and not any(w in question for w in ('추천', '찾아', '다른')):
        return None
    from ingredient_lookup import TERMS
    excluded = [name for name in TERMS if re.search(re.escape(name)+r'\s*(?:은|는|을|를)?\s*(?:빼|제외|없이)', question)]
    ingredients = [name for name in TERMS if name in question and name not in excluded
                   and not any(name in other and name != other and other in question for other in TERMS)]
    request = dict(nutrient='protein_g', mode='presence', minimum=None, maximum=None,
                   basis=None, ingredients=ingredients, excluded=excluded)
    if re.search(r'단백질.{0,8}(?:안\s*들어|없|불포함)', question):
        return request | dict(mode='clarify', reason='단백질이 없는 요리는 현재 판정하지 않습니다. 기준량과 최대 단백질 함량을 알려주세요.')
    # Never silently drop a second nutrition/health/time condition.
    if any(w in question for w in ('나트륨', '칼로리', '열량', '지방', '당류', '저염', '저당', '탄수', '알레르기', '당뇨', '채식', '비건', '분 안', '분 이내')):
        return request | dict(mode='clarify', reason='지금은 단백질 조건만 검사할 수 있습니다. 다른 영양·건강·시간 조건을 함께 만족하는지는 확인할 수 없습니다.')
    amounts = re.findall(r'(\d+(?:\.\d+)?)\s*(?:g|그램)\s*(이상|이하|초과|미만)', question, re.I)
    if amounts:
        request['mode']='quantity'
        if re.search(r'-\s*\d', question):
            return request | dict(mode='clarify', reason='단백질 함량은 음수로 입력할 수 없습니다.')
        for number, operator in amounts:
            if operator not in ('이상', '이하'):
                return request | dict(mode='clarify', reason='단백질 조건을 “25g 이상” 또는 “25g 이하”처럼 입력해 주세요.')
            field='minimum' if operator=='이상' else 'maximum'
            if request[field] is not None:
                return request | dict(mode='clarify', reason='최소·최대 단백질 함량을 각각 하나씩 입력해 주세요.')
            request[field]=float(number)
            if not math.isfinite(request[field]):
                return request | dict(mode='clarify', reason='유효한 단백질 함량을 입력해 주세요.')
        request['basis']='100g' if re.search(r'100\s*(?:g|그램)\s*(?:당|기준)', question, re.I) else 'serving' if any(w in question for w in ('1인분', '한 끼', '한끼', '일인분')) else None
        if request['basis'] is None:
            return request | dict(mode='clarify', reason='단백질 함량을 비교할 기준을 함께 알려주세요. 예: “1인분 단백질 25g 이상인 요리”, “100g당 단백질 10g 이상인 요리”.')
        if request['minimum'] is not None and request['maximum'] is not None and request['minimum'] > request['maximum']:
            return request | dict(mode='clarify', reason='최소 단백질 함량이 최대 함량보다 큽니다. 조건을 확인해 주세요.')
    elif any(w in question for w in ('고단백', '많', '높', '풍부', '적은', '적게', '낮')):
        if '재료' in question and not any(w in question for w in ('적은', '적게', '낮')):
            return request | dict(mode='ingredient_rank')
        return request | dict(mode='clarify', reason='재료 기준으로 찾으려면 “단백질 함량이 높은 재료가 들어간 요리”로 검색해 주세요. 요리 전체의 고단백 여부·1인분 함량은 현재 확인할 수 없습니다.')
    elif re.search(r'\d|이상|이하|초과|미만|없는', question):
        return request | dict(mode='clarify', reason='요청한 단백질 조건을 확인하기 어렵습니다. 기준량과 g 단위의 최소·최대 함량을 알려주세요.')
    return request


def number(value):
    if isinstance(value, bool):
        return None
    try:
        result=float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (TypeError, ValueError):
        return None


def search(docs, request, excluded=(), limit=6):
    from recipe_rag import excluded_hits
    if request['mode']=='ingredient_rank':
        return rank_by_ingredient(docs, request, excluded, limit)
    if request['mode']=='clarify':
        return dict(evidence=[], generation=dict(status='nutrition_clarify', answer=request['reason'], citations=[]))
    matches=[]
    eligible=0
    for doc in docs:
        if doc['collection'] != 'recipes' or not doc.get('source_url'):
            continue
        terms=list(excluded)+request['excluded']
        if excluded_hits(doc, terms):
            continue
        if any(not excluded_hits(doc, [ingredient]) for ingredient in request['ingredients']):
            continue
        value=number(doc.get('nutrition_raw', {}).get('INFO_PRO'))
        if request['mode']=='presence':
            if value is None or value <= 0:
                continue
            reason=f'레시피 API에 단백질 {value:g}g이 제공되어 있습니다. 기준량 미확인으로 고단백·1인분 함량을 뜻하지 않습니다.'
        else:
            # A reviewed, recipe-specific record is required; generic food matches
            # and API weight fields never establish a serving size.
            verified=doc.get('verified_nutrition', {})
            if verified.get('verified') is not True or not verified.get('source_url') or verified.get('basis') != request['basis']:
                continue
            if request['basis']=='serving' and (number(verified.get('serving_grams')) or 0) <= 0:
                continue
            value=number(verified.get('protein_g'))
            if value is None:
                continue
            eligible+=1
            if request['minimum'] is not None and value < request['minimum']:
                continue
            if request['maximum'] is not None and value > request['maximum']:
                continue
            basis='100g당' if request['basis']=='100g' else '1인분당'
            reason=f'{basis} 단백질 {value:g}g으로 입력한 함량 조건을 충족합니다.'
            doc=dict(doc, source_url=verified['source_url'])
        matches.append(dict(doc, nutrition_reason=reason, protein_value=value))
    # Unknown-basis API values must not be used to rank protein content.
    matches.sort(key=lambda d:(d['title'], d['id']))
    total=len(matches)
    matches=matches[:limit]
    if not matches:
        answer=('해당 기준량의 단백질 값이 검증된 레시피가 없어 함량 조건을 검사할 수 없습니다. 대신 “단백질 함량이 높은 재료가 들어간 요리”로 검색할 수 있습니다. 이 검색은 1인분 조건과 다릅니다.'
                if request['mode']=='quantity' and not eligible else '확인 가능한 자료에서 조건에 맞는 레시피를 찾지 못했습니다.')
        return dict(evidence=[], generation=dict(status='nutrition_no_match', answer=answer, citations=[]))
    intro=(f'레시피 API에 단백질이 제공된 메뉴 {total}개 중 {len(matches)}개입니다. '
           '단백질 포함은 고단백을 뜻하지 않으며 호박·곡물 요리도 포함될 수 있습니다. 함량순이 아닌 이름순입니다.'
           if request['mode']=='presence' else f'단백질 함량 조건을 통과한 메뉴 {total}개 중 {len(matches)}개입니다.')
    answer=intro+'\n\n'+'\n\n'.join(f"**{d['title']}** — {d['nutrition_reason']} [근거 {i}]" for i,d in enumerate(matches,1))
    citations=[dict(number=i,id=d['id'],title=d['title'],source_url=d['source_url'],source_label='레시피 영양 근거') for i,d in enumerate(matches,1)]
    return dict(evidence=matches, generation=dict(status='nutrition_matched', answer=answer, citations=citations))


def rank_by_ingredient(docs, request, excluded=(), limit=6, records=None):
    """Rank by a matching ingredient record, never by inferred dish protein.

    Only an exact ingredient name with plain/raw descriptors is accepted. Dried,
    fried, species-specific, yolk/white records cannot stand in for generic names.
    The displayed food name and candidate status retain product uncertainty.
    """
    import json
    from pathlib import Path
    from ingredient_lookup import recipe_ingredients, ALIASES
    from recipe_rag import excluded_hits
    if records is None:
        path=Path(__file__).resolve().parents[1]/'data/ingredients.json'
        records=json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    matches=[]
    for doc in docs:
        if doc['collection']!='recipes' or not doc.get('source_url') or excluded_hits(doc,list(excluded)+request['excluded']):
            continue
        if any(not excluded_hits(doc,[term]) for term in request['ingredients']):
            continue
        candidates=[]
        for ingredient in recipe_ingredients(doc.get('ingredients','')):
            canonical=ALIASES.get(ingredient,ingredient)
            # Do not erase an explicit product/preparation constraint.
            if ingredient not in (canonical, '계란'):
                continue
            for food in records:
                parts=[part.strip() for part in food.get('name','').split(',')]
                if not parts or parts[0]!=canonical or any(p not in ('생것','전란') for p in parts[1:]):
                    continue
                protein=number(food.get('protein_g'))
                basis=number(food.get('basis_amount'))
                if ('원재료' not in str(food.get('data_group')) or food.get('basis_unit')!='g'
                    or not basis or protein is None or protein<=0 or protein>basis or not food.get('source_url')):
                    continue
                per100=protein/basis*100
                candidates.append((per100,food['name'],food.get('food_id',''),ingredient,food))
        if not candidates:
            continue
        per100,_,_,ingredient,food=sorted(candidates,key=lambda c:(-c[0],c[1],c[2]))[0]
        reason=(f"재료 {ingredient} · 영양 데이터 후보 ‘{food['name']}’ 기준 단백질 {per100:.2f}g/100g "
                f"(중량 비율 {per100:.2f}%). 재료 종류·상태 확인이 필요하며 요리 전체·1인분 단백질 값이 아닙니다.")
        matches.append(dict(doc,nutrition_reason=reason,ingredient_protein_per100=per100,
                            ingredient_source_url=food['source_url'],ingredient_food_name=food['name']))
    matches.sort(key=lambda d:(-d['ingredient_protein_per100'],d['title'],d['id']))
    total=len(matches)
    matches=matches[:limit]
    if not matches:
        return dict(evidence=[],generation=dict(status='nutrition_no_match',answer='이름·상태·중량 기준을 대조할 수 있는 재료 영양 후보가 없어 요리를 정렬하지 못했습니다.',citations=[]))
    intro=(f'연결 가능한 재료의 100g당 단백질 함량이 높은 순으로 {total}개 중 {len(matches)}개를 표시합니다. '
           '각 요리에서 확인된 재료 후보 중 가장 높은 값으로 정렬합니다. 요리 전체의 고단백 판정이나 1인분 함량 순위는 아닙니다.')
    citations=[]
    lines=[]
    for i,doc in enumerate(matches):
        n=i*2+1
        lines.append(f"**{doc['title']}** — {doc['nutrition_reason']} [근거 {n}] [근거 {n+1}]")
        citations.extend([dict(number=n,id=doc['id'],title=doc['title'],source_url=doc['source_url'],source_label='레시피 재료'),
            dict(number=n+1,id=doc['id']+':ingredient',title=doc['ingredient_food_name'],source_url=doc['ingredient_source_url'],source_label='재료 영양 데이터 후보')])
    return dict(evidence=matches,generation=dict(status='nutrition_matched',answer=intro+'\n\n'+'\n\n'.join(lines),citations=citations))
