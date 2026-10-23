"""Fixed synthetic A/B experiment; never accept or persist real user questions.

Compare collection + lexical evidence retrieval + production generation helpers.
This is not the Streamlit/Chroma end-to-end path or an automatic semantic grade.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import tempfile
from time import perf_counter

from collect_source_docs import collect, load_bundle, ask_json, PROMPT1, digest, save, string_array
from recipe_rag import documents, generate, retrieve, settings, stage_model

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    dict(id='M1', recipe_id='28', question='새우 두부 계란찜의 재료와 만드는 순서, 찌는 시간을 알려줘.',
         rubric='연두부·새우·달걀 등 원문 재료, 원문 조리 순서, 약한 불 10분을 확인한다. 다른 요리의 방법을 섞지 않는다.'),
    dict(id='M2', recipe_id='36', question='저염 된장으로 맛을 낸 황태해장국은 어떻게 만들고, 짠맛을 줄이는 일반적인 식생활 방법은 뭐야?',
         rubric='황태·무를 끓인 뒤 된장, 콩나물 등 원문 순서를 지킨다. 일반 식생활 설명은 확보된 지침에서만 제시하고 나트륨 감소량은 추정하지 않는다.'),
    dict(id='M3', recipe_id='31', question='방울토마토 소박이에 쓰는 방울토마토 150g의 비타민 C는 몇 mg이야? 모르면 자료 부족이라고 알려줘.',
         rubric='현재 문서 묶음에 원재료 비타민 C 수치가 없으므로 mg 값을 만들지 않고 자료 부족을 안내한다. 레시피 영양값을 원재료 값으로 대체하지 않는다.'),
]


def run_one(case, variant, repeat, item, bundle, options, config, query_raw):
    calls = []
    def ask(prompt, payload, stage_config):
        if prompt == PROMPT1:
            return query_raw
        started = perf_counter()
        try:
            return ask_json(prompt, payload, stage_config)
        finally:
            calls.append(dict(stage='selection', model=stage_config['GMS_MODEL'],
                              seconds=round(perf_counter() - started, 3), payload_hash=digest(payload)))
    result = dict(case_id=case['id'], variant=variant, repeat=repeat,
                  selection_model=stage_model(config, 'selection'), answer_model=stage_model(config, 'answer'))
    try:
        with tempfile.TemporaryDirectory() as temp:
            chunks, report = collect(item, bundle, options, config, Path(temp), ask)
        recipe_docs = [d for d in documents() if d['id'] == item['id']]
        evidence = retrieve(recipe_docs + chunks, case['question'], selected=item['id'], top_k=3)
        started = perf_counter()
        generation = generate(case['question'], evidence, config)
        result.update(status=generation['status'], generation=generation,
                      answer_seconds=round(perf_counter() - started, 3),
                      selection_calls=calls, collection=report, evidence=evidence,
                      mandatory_source_present=any(d.get('document_id') == 'cookrcp01-' + case['recipe_id'] for d in chunks))
    except Exception:
        # API exception text may include credentials or request URLs.
        result.update(status='experiment_error', selection_calls=calls,
                      error='Collection or evaluation failed; exception details hidden.')
    return result


def write_html(report, path):
    sections = ['<!doctype html><html lang="ko"><meta charset="utf-8"><title>모델 비교 평가</title>',
                '<style>body{font:16px/1.6 sans-serif;max-width:1500px;margin:30px auto;padding:16px} '
                '.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px} article{border:1px solid #aaa;padding:18px;min-width:0} '
                'pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit} @media(max-width:800px){.pair{grid-template-columns:1fr}}</style>',
                '<h1>단일 모델 / 단계별 모델 실제 비교</h1>',
                '<p>고정 합성 질문. 검색어·후보·프롬프트·답변 모델을 고정하고 선별 모델만 변경합니다. '
                '자료 수집 → 어휘 검색 → 답변 생성의 통제 실험이며 실제 UI 전체 경로의 성능 평가는 아닙니다. '
                '인용 ID 유효성은 의미 정확성 점수가 아닙니다. 두 번 반복은 일반화 근거로 부족합니다.</p>',
                '<p>실행 시각(UTC): ' + escape(report['started_at']) + '</p>']
    if report.get('query_error'):
        sections.append('<p><strong>검색어 추출 API 호출 실패: 실제 답변 비교가 수행되지 않았습니다. 성능 개선은 미검증입니다.</strong></p>')
    for case in report['cases']:
        sections += ['<h2>' + escape(case['id'] + ': ' + case['question']) + '</h2>',
                     '<p>사전 검토 기준: ' + escape(case['rubric']) + '</p>']
        for repeat in range(1, report['repeats'] + 1):
            sections.append('<h3>반복 ' + str(repeat) + '</h3><div class="pair">')
            for variant in ('single', 'split'):
                row = next((r for r in report['results'] if r['case_id'] == case['id'] and r['repeat'] == repeat and r['variant'] == variant), None)
                sections.append('<article><h3>' + ('기존: 단일 모델' if variant == 'single' else '변경: 단계별 모델') + '</h3>')
                if row:
                    sections.append('<p>' + escape(str(row['selection_model'])) + ' 선별 / ' + escape(str(row['answer_model'])) + ' 답변</p>')
                    sections.append('<p>상태: ' + escape(row['status']) + ' / 선별 ' + str(sum(c['seconds'] for c in row.get('selection_calls', []))) + '초 / 답변 ' + str(row.get('answer_seconds', '-')) + '초</p>')
                    sections.append('<pre>' + escape(row.get('generation', {}).get('answer') or row.get('error', '표시 가능한 답변 없음')) + '</pre>')
                    sections.append('<details><summary>선별 문서·실제 답변 근거</summary><pre>' + escape(json.dumps(dict(collection=row.get('collection'), evidence=row.get('evidence')), ensure_ascii=False, indent=2)) + '</pre></details>')
                else:
                    sections.append('<p>실행되지 않음</p>')
                sections.append('</article>')
            sections.append('</div>')
    sections.append('</html>')
    path.write_text('\n'.join(sections), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeats', type=int, choices=range(1, 4), default=2)
    args = parser.parse_args()
    config = settings()
    if not all(config.get(k) for k in ('GMS_API_KEY', 'GMS_BASE_URL')):
        raise SystemExit('GMS credentials/server configuration missing; values hidden.')
    baseline = stage_model(config, 'query')
    if not baseline or not stage_model(config, 'selection'):
        raise SystemExit('Model configuration missing.')
    # Deliberately use the same answer model in both arms to isolate selection.
    configs = dict(single=dict(config, GMS_QUERY_MODEL=baseline, GMS_SELECTION_MODEL=baseline, GMS_ANSWER_MODEL=baseline),
                   split=dict(config, GMS_QUERY_MODEL=baseline, GMS_ANSWER_MODEL=baseline))
    bundle = load_bundle()
    options = json.loads((ROOT / 'config/rag_sources.json').read_text(encoding='utf-8'))
    recipes = json.loads((ROOT / 'data/recipes.json').read_text(encoding='utf-8'))
    output = ROOT / 'data/rag/model_comparison.json'
    report = dict(started_at=datetime.now(timezone.utc).isoformat(), cases=CASES, repeats=args.repeats,
                  bundle_hash=digest(bundle), options=options, results=[],
                  scope='Controlled collection/lexical retrieval/generation; not UI or Chroma end-to-end.',
                  scoring='Manual rubric review required; no automatic semantic quality score.',
                  cost='Token usage/cost not measured; timing includes network latency.')
    output.parent.mkdir(parents=True, exist_ok=True)
    save(output, report)
    for case in CASES:
        recipe = next(r for r in recipes if r['recipe_id'] == case['recipe_id'])
        item = dict(id='recipe:' + case['recipe_id'], name=recipe['name'], ingredients=recipe['ingredients_text'])
        try:
            query_raw = ask_json(PROMPT1, item, dict(config, GMS_MODEL=baseline))
            string_array(query_raw, limit=5)
        except Exception:
            report['query_error'] = dict(case_id=case['id'], status='query_api_failed', details='hidden')
            save(output, report)
            write_html(report, output.with_suffix('.html'))
            print(case['id'], 'query_api_failed', flush=True)
            return
        for repeat in range(1, args.repeats + 1):
            variants = ('single', 'split') if repeat % 2 else ('split', 'single')
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(run_one, case, v, repeat, item, bundle, options, configs[v], query_raw) for v in variants]
                for future in futures:
                    result = future.result()
                    report['results'].append(result)
                    save(output, report)
                    print(case['id'], result['variant'], repeat, result['status'], flush=True)
            write_html(report, output.with_suffix('.html'))
        if all(r['status'] == 'experiment_error' for r in report['results'] if r['case_id'] == case['id']):
            print('Stopped after repeated collection failures; see report.', flush=True)
            return
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    save(output, report)
    write_html(report, output.with_suffix('.html'))


if __name__ == '__main__':
    main()
