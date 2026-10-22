"""Ingredient-only recipe discovery using the recipe ingredient field."""
import re

NOTICE='현재는 재료 이름으로만 요리를 검색할 수 있습니다. 단백질 등 영양 조건 검색은 중단했습니다. 예: 두부, 두부와 달걀.'


def nutrition_blocked(question):
    return any(word in question for word in ('단백질','고단백','영양','성분','탄수','지방','칼로리','열량','나트륨','저염','저당','당류','식이섬유','비타민','미네랄'))


def ingredient_terms(question):
    text=question.strip()
    text=re.sub(r'(들어간|들어있는|들어 있는|포함된|만들 수 있는|만들수있는|추천해줘|추천해주세요|알려줘|찾아줘|레시피|요리|추천|음식|메뉴|저녁|점심|아침)', ' ',text)
    parts=re.split(r'[,，/+\s]+',text)
    result=[]
    for part in parts:
        stripped=re.sub(r'(으로|이랑|랑|와|과|가|이|로|를|을)$','',part)
        # Keep short ingredient names such as 오이/사과 intact.
        if len(stripped)>=2:
            part=stripped
        if part and part not in ('재료','있는','만드는'):
            result.append(part)
    return list(dict.fromkeys(result))


def matches(ingredients, term):
    # Inclusion aliases describe the ingredient, not allergen families.
    aliases={'계란':('계란','달걀'), '달걀':('계란','달걀'), '소고기':('소고기','쇠고기'), '쇠고기':('소고기','쇠고기')}
    text=re.sub(r'\s+','',ingredients).casefold()
    return any(a.casefold() in text for a in aliases.get(term,(term,)))


def search(docs, question, excluded=(), limit=6):
    from recipe_rag import excluded_hits
    def response(status,answer,hits=()):
        citations=[dict(number=i,id=d['id'],title=d['title'],source_url=d['source_url'],source_label='레시피 재료 원문') for i,d in enumerate(hits,1)]
        return dict(evidence=list(hits),warnings=[],generation=dict(status=status,answer=answer,citations=citations))
    if nutrition_blocked(question):
        return response('ingredient_blocked',NOTICE)
    terms=ingredient_terms(question)
    if not terms:
        return response('ingredient_empty','찾을 재료 이름을 입력해 주세요. 예: 두부, 달걀.')
    hits=[dict(d,ingredient_reason='재료 원문에 '+', '.join(terms)+' 포함') for d in docs
          if d['collection']=='recipes' and d.get('source_url') and not excluded_hits(d,excluded)
          and all(matches(d.get('ingredients',''),t) for t in terms)]
    hits.sort(key=lambda d:(d['title'],d['id']))
    total=len(hits);hits=hits[:limit]
    if not hits:
        return response('ingredient_no_match','입력한 재료가 모두 포함된 요리를 찾지 못했습니다. 재료 이름과 제외 조건을 확인해 주세요.')
    answer=f'재료 원문에서 {", ".join(terms)} 포함을 확인한 요리 {total}개 중 {len(hits)}개입니다.\n\n'
    answer+='\n\n'.join(f"**{d['title']}** — {d['ingredients']} [근거 {i}]" for i,d in enumerate(hits,1))
    return response('ingredient_matched',answer,hits)


def is_ingredient_query(docs, question):
    terms=ingredient_terms(question)
    return bool(terms) and all(any(matches(d.get('ingredients',''),term) for d in docs if d['collection']=='recipes') for term in terms)
