"""Rebuild two persistent Chroma collections from repository source data."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / 'data/rag/chroma'
COLLECTIONS = {'recipes': 'recipe_meta', 'guidelines': 'source_docs'}


def client_for(path=DB_PATH):
    # Optional project-local installation, also supports a normal pip environment.
    local = ROOT / '.tools/vector'
    if local.exists() and str(local) not in sys.path:
        sys.path.insert(0, str(local))
    import chromadb
    from chromadb.config import Settings
    return chromadb.PersistentClient(path=str(path), settings=Settings(anonymized_telemetry=False))


def namespace(config):
    model = config.get('GMS_EMBEDDING_MODEL') or 'text-embedding-3-small'
    base = config.get('GMS_BASE_URL', '').rstrip('/')
    if not base:
        raise ValueError('GMS embedding server is not configured')
    return hashlib.sha256((base + '\n' + model).encode()).hexdigest()


def counts(client):
    existing = {c.name for c in client.list_collections()}
    return {name: client.get_collection(name, embedding_function=None).count()
            if name in existing else 0 for name in COLLECTIONS.values()}


def index_documents(docs, config, client, embed=None):
    from semantic_search import embeddings, search_text, unit
    embed = embed or embeddings
    ids = [d['id'] for d in docs]
    if len(ids) != len(set(ids)) or any(not i for i in ids):
        raise ValueError('Document IDs must be nonempty and unique')
    if any(d['collection'] not in COLLECTIONS for d in docs):
        raise ValueError('Unknown document collection')
    signature = namespace(config)
    existing = {c.name for c in client.list_collections()}
    # Fail before changing either collection when the embedding space changes.
    for name in COLLECTIONS.values():
        if name in existing:
            c = client.get_collection(name, embedding_function=None)
            if (c.metadata or {}).get('embedding_namespace') != signature:
                raise ValueError('Embedding model/server changed; choose a new --db-dir and rebuild')
    texts = [search_text(d) for d in docs]
    if any(not t.strip() for t in texts):
        raise ValueError('Empty search text')
    vectors = embed(texts, config) if texts else []
    if len(vectors) != len(docs):
        raise ValueError('Embedding response count mismatch')
    vectors = [unit(v) for v in vectors]
    if vectors and len({len(v) for v in vectors}) != 1:
        raise ValueError('Embedding dimensions mismatch')
    for kind, name in COLLECTIONS.items():
        c = client.get_or_create_collection(name, embedding_function=None,
            metadata={'hnsw:space': 'cosine', 'embedding_namespace': signature})
        positions = [i for i, d in enumerate(docs) if d['collection'] == kind]
        for start in range(0, len(positions), 64):
            batch = positions[start:start+64]
            metadata = []
            for i in batch:
                d = docs[i]
                metadata.append(dict(id=d['id'], title=d['title'],
                    source_url=d['source_url'], collection=kind,
                    evidence_json=json.dumps(d, ensure_ascii=False)))
                for field in ('related_item_id', 'document_id', 'source_file', 'source_record',
                              'source_type', 'chunk_index', 'chunk_size', 'chunk_overlap',
                              'char_start', 'char_end', 'is_item_document'):
                    if field in d:
                        metadata[-1][field] = d[field]
            c.upsert(ids=[ids[i] for i in batch], documents=[texts[i] for i in batch],
                     embeddings=[vectors[i] for i in batch], metadatas=metadata)
        wanted = {ids[i] for i in positions}
        stale = [i for i in c.get(include=[])['ids'] if i not in wanted]
        if stale:
            c.delete(ids=stale)
        if c.count() != len(wanted):
            raise RuntimeError('Stored collection count does not match source')
    return counts(client)


def retrieve(docs, query, config, excluded=(), selected=None, top_k=3,
             min_score=0.25, db_path=DB_PATH):
    from semantic_search import embeddings, expand_query, search_collections, search_text
    from recipe_rag import excluded_hits
    if not query.strip() or not 1 <= top_k <= 10 or any(not t.strip() for t in excluded):
        raise ValueError('Invalid search input')
    current = {d['id']: d for d in docs}
    if selected and (selected not in current or current[selected]['collection'] != 'recipes'):
        raise ValueError('Unknown selected recipe')
    client = client_for(db_path)
    signature = namespace(config)
    collections = ('recipes', 'guidelines') if selected else search_collections(query, selected)
    search_query = expand_query(query, config) if not selected and collections == ('recipes',) else query
    q = embeddings([search_query], config)[0]
    result = []
    for kind in collections:
        try:
            c = client.get_collection(COLLECTIONS[kind], embedding_function=None)
        except Exception:
            raise RuntimeError('Vector index missing; run scripts/index_vectors.py') from None
        if (c.metadata or {}).get('embedding_namespace') != signature:
            raise RuntimeError('Vector index model/server mismatch; rebuild the index')
        # Validate freshness; do not silently serve stale or deleted source documents.
        stored = c.get(include=['documents'])
        expected = {d['id']: search_text(d) for d in docs if d['collection'] == kind}
        if dict(zip(stored['ids'], stored['documents'])) != expected:
            raise RuntimeError('Vector index is stale; run scripts/index_vectors.py')
        if not c.count():
            continue
        hits = c.query(query_embeddings=[q], n_results=c.count(), include=['distances'])
        ranked = []
        for doc_id, distance in zip(hits['ids'][0], hits['distances'][0]):
            d = current[doc_id]
            if selected and kind == 'recipes' and doc_id != selected:
                continue
            if selected and kind == 'guidelines' and d.get('related_item_id') != selected:
                continue
            if kind == 'guidelines' and d.get('related_item_id'):
                parent = current.get(d['related_item_id'])
                if parent and excluded_hits(parent, excluded):
                    continue
            if kind == 'recipes' and excluded_hits(d, excluded):
                continue
            if kind == 'guidelines' and d.get('allowed_use') not in ('qualitative_recommendation_explanation', 'recipe_explanation'):
                continue
            score = 1 - distance
            mandatory = selected is not None and (selected == doc_id or
                (d.get('related_item_id') == selected and d.get('is_item_document', False)))
            if mandatory or score >= min_score:
                ranked.append((mandatory, score, d))
        ranked.sort(key=lambda x: (-x[0], -x[1], x[2]['id']))
        result.extend(dict(d, similarity=round(score, 6)) for _, score, d in ranked[:top_k])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db-dir', type=Path, default=DB_PATH)
    parser.add_argument('--count', action='store_true', help='Show persisted counts without API calls')
    args = parser.parse_args()
    client = client_for(args.db_dir)
    if args.count:
        result = counts(client)
    else:
        from recipe_rag import documents, settings
        result = index_documents(documents(), settings(), client)
    print(json.dumps({'collections': result, 'total': sum(result.values())}, indent=2))


if __name__ == '__main__':
    main()
