"""Exercise real persistent Chroma storage without network or API credentials."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class VectorIndexChecks(unittest.TestCase):
    def test_persistence_upsert_pruning_and_embedding_space_guard(self):
        # Separate processes release Windows file handles before directory cleanup.
        script = '''
import sys
from pathlib import Path
sys.path.insert(0, str(Path('scripts').resolve()))
from index_vectors import client_for, index_documents, counts
client = client_for(Path(sys.argv[1]))
config = dict(GMS_BASE_URL='https://test.invalid/v1', GMS_EMBEDDING_MODEL='test')
def embed(texts, config):
    return [[1., 0.] if 'changed' not in t else [0., 1.] for t in texts]
docs = [dict(id='recipe:1', collection='recipes', title='one', ingredients='one',
             text='one', source_url='https://example.invalid/one'),
        dict(id='guidance:1', collection='guidelines', title='guide', text='guide',
             source_url='https://example.invalid/guide', related_item_id='recipe:1',
             is_item_document=True, allowed_use='recipe_explanation')]
expected = dict(recipe_meta=1, source_docs=1)
assert index_documents(docs, config, client, embed) == expected
assert index_documents(docs, config, client, embed) == expected
docs[0]['text'] = 'changed'
assert index_documents(docs, config, client, embed) == expected
c = client.get_collection('recipe_meta', embedding_function=None)
record = c.get(ids=['recipe:1'], include=['documents','embeddings','metadatas'])
assert 'changed' in record['documents'][0]
assert list(record['embeddings'][0]) == [0., 1.]
from unittest.mock import patch
from index_vectors import retrieve
with patch('semantic_search.embeddings', return_value=[[0., 1.]]):
    hits = retrieve(docs, 'question', config, selected='recipe:1', db_path=Path(sys.argv[1]))
    assert [d['id'] for d in hits] == ['recipe:1', 'guidance:1']
    meta = client.get_collection('source_docs', embedding_function=None).get(include=['metadatas'])
    assert meta['metadatas'][0]['related_item_id'] == 'recipe:1'
    assert retrieve(docs, 'question', config, excluded=['one'], selected='recipe:1', db_path=Path(sys.argv[1])) == []
    changed = [docs[0] | {'title': 'new title'}, docs[1]]
    try:
        retrieve(changed, 'question', config, selected='recipe:1', db_path=Path(sys.argv[1]))
    except RuntimeError:
        pass
    else:
        raise AssertionError('Stale search documents must require reindexing')
try:
    index_documents(docs, config | {'GMS_EMBEDDING_MODEL': 'other'}, client, embed)
except ValueError:
    pass
else:
    raise AssertionError('Model mismatch must not mix embedding spaces')
assert counts(client) == expected
try:
    index_documents(docs + [docs[0]], config, client, embed)
except ValueError:
    pass
else:
    raise AssertionError('Duplicate input IDs must fail')
assert index_documents(docs[:1], config, client, embed) == dict(recipe_meta=1, source_docs=0)
'''
        with tempfile.TemporaryDirectory() as temp:
            run = subprocess.run([sys.executable, '-c', script, temp], cwd=ROOT,
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            check = subprocess.run([sys.executable, 'scripts/index_vectors.py',
                                    '--db-dir', temp, '--count'], cwd=ROOT,
                                   capture_output=True, text=True)
            self.assertEqual(check.returncode, 0, check.stderr)
            import json
            self.assertEqual(json.loads(check.stdout)['collections'],
                             dict(recipe_meta=1, source_docs=0))
