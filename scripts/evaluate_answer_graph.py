"""Evaluate one fixed public recipe question; never log arbitrary user input."""
import json
from pathlib import Path
from unittest.mock import patch

from rag_graph import build_graph, answer_options
from recipe_rag import documents, settings


def main():
    graph = build_graph()
    from openai import OpenAI
    raw = []

    def client_factory(*args, **kwargs):
        client = OpenAI(*args, **kwargs)
        create = client.responses.create

        def record(*args, **kwargs):
            response = create(*args, **kwargs)
            raw.append(response.output_text)
            return response
        client.responses.create = record
        return client

    with patch('openai.OpenAI', side_effect=client_factory):
        state = graph.invoke(dict(question='이 요리의 재료와 조리법 알려줘',
            docs=documents(), selected='recipe:28', excluded=[], config=settings(),
            options=answer_options(), retriever='chroma', do_generate=True))
    report = dict(case_id='A1', selected='recipe:28',
        question=state['question'], warnings=state['warnings'],
        options=answer_options(),
        evidence=[dict(id=d['id'], number=d['evidence_number'], evidence_type=d['evidence_type'])
                  for d in state['evidence']], generation=state['generation'])
    if state['generation']['status'] == 'invalid_citations':
        report['rejected_public_answer'] = raw[-1] if raw else None
    used = {int(n) for n in __import__('re').findall(r'\[근거 (\d+)\]', state['generation'].get('answer') or '')}
    report['checks'] = dict(
        generated=state['generation']['status'] == 'generated_unreviewed',
        selected_metadata_present=any(d['id'] == 'recipe:28' for d in state['evidence']),
        only_cited_sources=used == {c['number'] for c in state['generation']['citations']})
    path = Path(__file__).resolve().parents[1] / 'data/rag/answer_graph_evaluation.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True, indent=2))
    if not all(report['checks'].values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
