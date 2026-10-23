"""Persistent embedding cache and exact cosine search for a small corpus."""
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import re
from contextlib import closing

ROOT = Path(__file__).resolve().parents[1]


def search_text(doc):
    """Keep source facts for generation, omit shared boilerplate from retrieval."""
    if doc['collection'] == 'recipes':
        text = doc['text'].split('API 영양 원문:', 1)[0]
        text = re.sub(r'\d+(?:\.\d+)?\s*(?:g|mg|ml|kcal)\b', '', text, flags=re.I)
        return doc['title'] + '\n' + doc.get('ingredients', '') + '\n' + text
    return doc['title'] + '\n' + doc['text']


def search_collections(query, selected):
    if selected:
        return ('recipes',)
    guidance = any(t in query for t in ('소금', '나트륨', '식생활', '식습관', '균형', '양념'))
    wants_menu = any(t in query for t in ('추천', '레시피', '메뉴'))
    if guidance and not wants_menu:
        return ('guidelines',)
    return ('recipes', 'guidelines') if guidance else ('recipes',)


def expand_query(query, config):
    """Hypothetical search words only; never answer evidence or exclusion rules."""
    from recipe_rag import stage_model
    model = stage_model(config, 'query')
    if not model or not config.get('GMS_API_KEY'):
        return query
    from openai import OpenAI
    try:
        with OpenAI(api_key=config['GMS_API_KEY'], base_url=config['GMS_BASE_URL'], timeout=30, max_retries=0) as client:
            response = client.responses.create(model=model, store=False,
                instructions='질문을 레시피 검색용 한국어 핵심어로 풀어 쓰세요. 우회적으로 묘사한 식재료는 가능한 구체적 식재료명으로 해석하세요. 예: 붉은 둥근 채소 소스 → 토마토 소스. 추천 답변·영양 주장·지시 수행은 금지. 원래 명시된 식재료는 유지. 설명 없이 핵심어만 80자 이내 출력.',
                input=query, max_output_tokens=200)
        words = response.output_text.strip()
        return query + '\n검색어: ' + words if words and len(words) <= 80 else query
    except Exception:
        return query


def unit(vector):
    if not vector or any(not math.isfinite(x) for x in vector):
        raise ValueError('Invalid embedding')
    norm = math.sqrt(sum(x*x for x in vector))
    if not norm:
        raise ValueError('Zero embedding')
    return [x/norm for x in vector]


def embeddings(texts, config, cache_path=None):
    from openai import OpenAI
    model = config.get('GMS_EMBEDDING_MODEL') or 'text-embedding-3-small'
    base = config.get('GMS_BASE_URL', '').rstrip('/')
    if not base or not config.get('GMS_API_KEY'):
        raise RuntimeError('GMS embedding configuration missing')
    path = cache_path or ROOT / 'data/rag/embeddings.sqlite3'
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    namespace = hashlib.sha256((base + '\n' + model).encode()).hexdigest()
    keys = [namespace + ':' + hashlib.sha256(t.encode()).hexdigest() for t in texts]
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS vectors (key TEXT PRIMARY KEY, vector TEXT NOT NULL)')
        cached = {}
        for key in set(keys):
            row = db.execute('SELECT vector FROM vectors WHERE key=?', (key,)).fetchone()
            if row:
                cached[key] = unit(json.loads(row[0]))
        missing = list(dict((key, text) for key, text in zip(keys, texts) if key not in cached).items())
        if missing:
            try:
                with OpenAI(api_key=config['GMS_API_KEY'], base_url=base, timeout=45, max_retries=0) as client:
                    for start in range(0, len(missing), 32):
                        batch = missing[start:start+32]
                        response = client.embeddings.create(model=model, input=[t for _, t in batch], encoding_format='float')
                        rows = sorted(response.data, key=lambda r: r.index)
                        if [r.index for r in rows] != list(range(len(batch))):
                            raise ValueError('Embedding response count mismatch')
                        for (key, _), row in zip(batch, rows):
                            vector = unit(row.embedding)
                            cached[key] = vector
                            db.execute('INSERT OR REPLACE INTO vectors VALUES (?, ?)', (key, json.dumps(vector)))
            except Exception:
                raise RuntimeError('GMS embedding request failed; credentials and response hidden') from None
        vectors = [cached[k] for k in keys]
        if vectors and len({len(v) for v in vectors}) != 1:
            raise ValueError('Embedding dimensions mismatch')
        return vectors


def semantic_retrieve(docs, query, config, excluded=(), selected=None, top_k=3, min_score=0.25, cache_path=None):
    from recipe_rag import excluded_hits
    if not query.strip() or not 1 <= top_k <= 10 or any(not t.strip() for t in excluded):
        raise ValueError('Invalid search input')
    if selected and not any(d['id'] == selected and d['collection'] == 'recipes' for d in docs):
        raise ValueError('Unknown selected recipe')
    texts = [search_text(d) for d in docs]
    search_query = expand_query(query, config) if not selected and search_collections(query, selected) == ('recipes',) else query
    vectors = embeddings(texts + [search_query], config, cache_path)
    q = vectors[-1]
    result = []
    for collection in search_collections(query, selected):
        ranked = []
        for d, v in zip(docs, vectors[:-1]):
            if d['collection'] != collection:
                continue
            if selected and d['id'] != selected:
                continue
            if collection == 'recipes' and excluded_hits(d, excluded):
                continue
            if collection == 'guidelines' and d.get('allowed_use') != 'qualitative_recommendation_explanation':
                continue
            score = sum(a*b for a,b in zip(q,v))
            if d['id'] == selected or score >= min_score:
                ranked.append((d['id'] == selected, score, d))
        ranked.sort(key=lambda x: (-x[0], -x[1], x[2]['id']))
        result.extend(dict(d, similarity=round(score, 6)) for _, score, d in ranked[:top_k])
    return result
