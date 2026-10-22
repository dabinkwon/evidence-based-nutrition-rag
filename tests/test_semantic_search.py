import sys
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from semantic_search import embeddings, semantic_retrieve, unit, search_text, search_collections


class SemanticChecks(unittest.TestCase):
    def test_search_text_keeps_facts_without_shared_nutrition_notice(self):
        doc = dict(title='두부찜', collection='recipes', ingredients='두부',
                   text='두부를 찐다. API 영양 원문: 100 기준량 미확인')
        text = search_text(doc)
        self.assertIn('두부를 찐다', text)
        self.assertNotIn('기준량 미확인', text)
        self.assertIn('기준량 미확인', doc['text'])

    def test_question_routing(self):
        self.assertEqual(search_collections('소금을 적게 먹으려면?', None), ('guidelines',))
        self.assertEqual(search_collections('두부 요리 추천', None), ('recipes',))
        self.assertEqual(search_collections('저염 레시피 추천 소금', None), ('recipes','guidelines'))
        self.assertEqual(search_collections('이 요리 조리법', 'recipe:28'), ('recipes',))

    def test_cache_reuse_and_model_invalidation(self):
        config = dict(GMS_API_KEY='fake', GMS_BASE_URL='https://gateway.example/v1', GMS_EMBEDDING_MODEL='model-a')
        with tempfile.TemporaryDirectory() as temp, patch('openai.OpenAI') as factory:
            client = factory.return_value.__enter__.return_value
            client.embeddings.create.return_value.data = [SimpleNamespace(index=0, embedding=[3., 4.])]
            path = Path(temp) / 'cache.sqlite3'
            self.assertEqual(embeddings(['text'], config, path), [[0.6, 0.8]])
            embeddings(['text'], config, path)
            self.assertEqual(client.embeddings.create.call_count, 1)
            embeddings(['text'], config | {'GMS_EMBEDDING_MODEL': 'model-b'}, path)
            self.assertEqual(client.embeddings.create.call_count, 2)

    def test_exclusion_and_selection_with_vectors(self):
        docs = [dict(id='recipe:a', collection='recipes', title='새우찜', text='새우', ingredients='새우'),
                dict(id='recipe:b', collection='recipes', title='두부', text='두부', ingredients='두부')]
        with patch('semantic_search.embeddings', return_value=[[1.,0.],[0.,1.],[1.,0.]]):
            self.assertEqual(semantic_retrieve(docs, '질문', {}, ['새우'], 'recipe:a'), [])
            self.assertEqual(semantic_retrieve(docs, '질문', {}, selected='recipe:b')[0]['id'], 'recipe:b')

    def test_invalid_vectors(self):
        for v in ([], [0.,0.], [float('nan')]):
            with self.assertRaises(ValueError):
                unit(v)
