"""Retrieve local research metadata without inferring health effects from titles."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def items(value):
    return value if isinstance(value, list) else [value] if isinstance(value, dict) else []


def available_research_foods():
    """List foods with saved papers, rather than all catalog entries."""
    path = ROOT / 'data/agrifood_collection_report.json'
    if not path.exists():
        return []
    report = json.loads(path.read_text(encoding='utf-8'))
    return sorted({row['food'] for row in report.get('records', [])
                   if row.get('status') in ('success', 'cached') and row.get('unique_bibliography_count', 0) > 0})


def answer_research(question):
    """Return None for other intents; never call external services or an LLM."""
    if not any(word in question for word in ('몸에', '효능', '건강', '좋아', '좋은', '좋나요', '좋을', '이점', '도움', '항산화', '혈압', '연구', '논문')):
        return None
    if any(word in question for word in ('추천', '만드는', '조리법', '레시피')):
        return None
    sources = json.loads((ROOT / 'config/agrifood_sources.json').read_text(encoding='utf-8'))
    def mentioned(name):
        return re.search(r'(?<![가-힣A-Za-z])' + re.escape(name) + r'(?=$|\s|[?？.,!]|가|는|를|에|의|와|도|은|이)', question)
    searchable = {name: name for name in sources['foods']}
    searchable.update(sources.get('aliases', {}))
    matched = [name for name in searchable if mentioned(name)]
    # A specific cultivar/variant takes precedence over a shorter base name.
    matched = [name for name in matched if not any(name != other and name in other for other in matched)]
    names = list(dict.fromkeys(searchable[name] for name in matched))
    if '가지' in names and re.search(r'(여러|몇|한|두|세)\s*가지', question):
        names.remove('가지')
    if len(names) != 1:
        ambiguous = [name for name in sources.get('ambiguous_names', {}) if mentioned(name)]
        if not names and ambiguous:
            name = max(ambiguous, key=len)
            return dict(status='research_ambiguous', answer=f'{name}은 자료에서 종류가 나뉩니다. 다음 중 식품 이름을 구체적으로 입력해 주세요: ' + ', '.join(sources['ambiguous_names'][name]), citations=[])
        unavailable = [name for name in sources.get('unavailable_foods', []) if mentioned(name)]
        if not names and unavailable:
            name = max(unavailable, key=len)
            return dict(status='research_unavailable', answer=f'{name}의 효능 연구는 현재 연결된 농산물 논문 자료에서 확인할 수 없습니다. 원료나 비슷한 식품의 연구를 {name}의 효과로 대신 설명하지 않습니다. 영양성분이 궁금하면 “{name} 영양성분”으로 질문해 주세요.', citations=[])
        return None
    name = names[0]
    sample = sources['foods'][name]
    citations = []
    rows = []
    groups_by_type = {}
    for path in sorted((ROOT / 'data/raw/agrifood').glob(sample + '-*-food-functions-*.json')):
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
            body = payload.get('body', {})
            if payload.get('header', {}).get('result_Code') != '200' or body.get('sample_Id') != sample:
                continue
            code, label = body['research_Type_Cd'], body['research_Type_Nm']
            groups = items(body.get('items', {}).get('fnclty_List', {}).get('item'))
            papers = {}
            for group in groups:
                for paper in items(group.get('thesis_List', {}).get('item')):
                    if not paper.get('title'):
                        continue
                    identity = (paper['title'], paper.get('details', ''), paper.get('pblicte_Year', ''))
                    papers.setdefault(identity, set()).add(group.get('fnclty_Nm', '분류 미제공'))
            if not papers:
                continue
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
        number = len(citations) + 1
        citations.append(dict(number=number, id=path.stem, title=name + ' · ' + label + ' 논문정보',
                              source_url=sources['source_url'], source_label='농촌진흥청 논문 메타데이터',
                              source_file=path.relative_to(ROOT).as_posix()))
        groups_by_type.setdefault((code, label), set()).update(g.get('fnclty_Nm', '') for g in groups)
        for (title, journal, year), categories in papers.items():
            rows.append({'연구유형': label, 'API 기능성 분류': ', '.join(sorted(categories)),
                         '논문명(원문)': title, '저널': journal, '연도': year, '근거': number})
    if not rows:
        return dict(status='research_missing', answer=f'{name}의 기능성 연구 자료를 현재 저장된 데이터에서 확인하지 못했습니다. 확인되지 않은 효능을 추정하지 않습니다.', citations=[])
    # Deduplicate repeated cached snapshots, preserving the originating citation.
    rows = list({(r['연구유형'], r['논문명(원문)'], r['저널'], r['연도']): r for r in rows}.values())
    rows.sort(key=lambda r: (r['연구유형'] != '인체적용시험', r['연구유형'], r['논문명(원문)']))
    paragraphs = [f'**{name}가 몸에 어떤 도움이 되는지 궁금하시군요. 확보한 자료에서는 다음 주제의 연구를 확인할 수 있습니다.**']
    for (code, label), categories in sorted(groups_by_type.items(), key=lambda pair: pair[0][0] != 'G003'):
        numbers = sorted({r['근거'] for r in rows if r['연구유형'] == label})
        refs = ' '.join(f'[근거 {n}]' for n in numbers)
        paragraphs.append(f'**{label}** 자료의 API 분류: {", ".join(sorted(c for c in categories if c))}. {refs}')
    paragraphs.append('위 내용은 **관련 연구가 등록되어 있다는 뜻**입니다. 논문 제목·저널·연구유형만 확보했으므로 효과의 크기나 확실성, 적정 섭취량은 판단할 수 없습니다. 동물시험 결과를 사람의 효과로 해석하거나, 추출물·분말 연구를 일반적인 가지 요리의 효과로 그대로 적용할 수 없습니다.')
    paragraphs.append('아래에서 연구유형과 논문 원문 제목을 확인할 수 있습니다. 비타민·단백질 함량은 별도의 원재료 영양 데이터가 필요합니다.')
    return dict(status='research_lookup', answer='\n\n'.join(paragraphs), citations=citations, research_rows=rows)
