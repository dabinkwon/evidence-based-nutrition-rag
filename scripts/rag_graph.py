"""Two-node grounded answer graph; no persistent conversation checkpointer."""
import json
from pathlib import Path
import sys
from typing import TypedDict

ROOT = Path(__file__).resolve().parents[1]


def answer_options(path=None):
    values = json.loads(Path(path or ROOT / 'config/rag_answer.json').read_text(encoding='utf-8'))
    if type(values.get('top_k')) is not int or not 1 <= values['top_k'] <= 10:
        raise ValueError('top_k must be an integer from 1 to 10')
    if type(values.get('min_score')) not in (int, float) or not 0 <= values['min_score'] <= 1:
        raise ValueError('min_score must be between 0 and 1')
    return values


def evidence_context(docs, hits, selected=None, excluded=()):
    from recipe_rag import excluded_hits
    merged = []
    if selected:
        matches = [d for d in docs if d['id'] == selected and d['collection'] == 'recipes']
        if not matches:
            raise ValueError('Unknown selected recipe')
        d = matches[0]
        merged.append(dict(d, recommendation_blocked=bool(excluded_hits(d, excluded))))
    merged.extend(hits)
    seen = set()
    evidence = []
    for d in merged:
        if d['id'] in seen:
            continue
        seen.add(d['id'])
        kind = 'item_metadata' if d['collection'] == 'recipes' else 'external_document'
        evidence.append(dict(d, evidence_number=len(evidence) + 1, evidence_type=kind,
            source_label='항목 메타데이터' if kind == 'item_metadata' else '외부 문서'))
    return evidence


class State(TypedDict, total=False):
    question: str
    docs: list
    selected: str
    excluded: list
    config: dict
    options: dict
    retriever: str
    do_generate: bool
    evidence: list
    generation: dict
    warnings: list


def retrieve_node(state):
    from recipe_rag import retrieve as lexical
    from semantic_search import semantic_retrieve
    from index_vectors import retrieve as chroma
    # Validate/preserve selected metadata before any database/network operation.
    base = evidence_context(state['docs'], [], state.get('selected'), state.get('excluded', []))
    backend = {'chroma': chroma, 'semantic': semantic_retrieve, 'lexical': lexical}[state['retriever']]
    args = (state['docs'], state['question'])
    kwargs = dict(excluded=state.get('excluded', []), selected=state.get('selected'),
                  top_k=state['options']['top_k'])
    if state['retriever'] != 'lexical':
        args += (state['config'],)
        kwargs['min_score'] = state['options']['min_score']
    warnings = []
    try:
        hits = backend(*args, **kwargs)
    except (RuntimeError, ValueError):
        if not base:
            return dict(evidence=[], warnings=['검색에 실패했습니다. 색인과 설정을 확인해 주세요.'])
        hits = []
        warnings = ['추가 근거 검색에 실패해 선택 항목 메타데이터만 사용합니다.']
    return dict(evidence=evidence_context(state['docs'], hits, state.get('selected'),
                                         state.get('excluded', [])), warnings=warnings)


def generate_node(state):
    from recipe_rag import generate
    if not state.get('do_generate'):
        return dict(generation=dict(status='not_requested', answer=None, citations=[]))
    return dict(generation=generate(state['question'], state['evidence'], state['config']))


def build_graph():
    local = ROOT / '.tools/vector'
    if local.exists() and str(local) not in sys.path:
        sys.path.insert(0, str(local))
    from langgraph.graph import StateGraph, START, END
    graph = StateGraph(State)
    graph.add_node('retrieve', retrieve_node)
    graph.add_node('generate', generate_node)
    graph.add_edge(START, 'retrieve')
    graph.add_edge('retrieve', 'generate')
    graph.add_edge('generate', END)
    return graph.compile()
