"""Run fixed public/synthetic search cases and write reviewable evidence."""
import json
from pathlib import Path
from recipe_rag import documents, settings, retrieve, generate
from semantic_search import semantic_retrieve


def main():
    docs, config = documents(), settings()
    root = Path(__file__).resolve().parents[1]
    for name in ('data/rag/semantic_evaluation.json',):
        path = root / name
        previous = path.with_name(path.stem + '_W026' + path.suffix)
        if path.exists() and not previous.exists():
            previous.write_bytes(path.read_bytes())
    cases = [
        ('S1', '콩으로 만든 부드러운 식재료를 쓰는 요리 추천해줘', [], None),
        ('S2', '소금을 적게 먹으려면 어떻게 요리하면 좋을까?', [], None),
        ('S3', '두부 요리 추천해줘', ['새우', '계란', '우유'], None),
        ('S4', '이 요리의 재료와 조리법 알려줘', [], 'recipe:28'),
        ('S5', '새우 두부 계란찜 1인분의 열량은 얼마야?', [], 'recipe:28')]
    results = []
    for case_id, question, excluded, selected in cases:
        evidence = semantic_retrieve(docs, question, config, excluded, selected)
        result = dict(case_id=case_id, question=question, excluded=excluded,
                      lexical_ids=[d['id'] for d in retrieve(docs, question, excluded, selected)],
                      semantic_results=[dict(id=d['id'], title=d['title'], similarity=d['similarity']) for d in evidence],
                      generation=generate(question, evidence, config))
        results.append(result)
        print(case_id, result['generation']['status'], flush=True)
    root = Path(__file__).resolve().parents[1]
    (root / 'data/rag/semantic_evaluation.json').write_text(json.dumps(results, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    lines = ['# 임베딩 검색 실행 결과', '', '2026-10-21. 고정 공개 질문 5개. 검색 모델: '+config['GMS_EMBEDDING_MODEL']+'.',
             '', '자동 인용 ID 검사와 의미 일치 평가는 별개다. 아래는 실제 실행 결과이며 내용 품질 최종 통과를 뜻하지 않는다.', '']
    for r in results:
        lines += ['## '+r['case_id'], '', r['question'], '', '키워드 검색 ID: '+', '.join(r['lexical_ids']), '',
                  '의미 검색: '+', '.join(d['title']+' ('+d['id']+')' for d in r['semantic_results']), '',
                  '생성 상태: '+r['generation']['status'], '', r['generation'].get('answer') or '답변 없음', '']
    (root / 'docs/SEMANTIC_RESULTS.md').write_text('\n'.join(lines), encoding='utf-8')


if __name__ == '__main__':
    main()
