import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from collect_source_docs import collect, split_text, string_array, store_chunks, load_bundle


class SourceChecks(unittest.TestCase):
    def setUp(self):
        self.options = dict(chunk_size=10, chunk_overlap=3, min_document_chars=100,
                            max_candidates_per_query=1)
        self.item = dict(id='recipe:1', name='tofu', ingredients='bean')
        self.bundle = [dict(document_id='own', title='tofu', summary='own source', text='short',
                            source_url='https://example.invalid/own', item_ids=['recipe:1']),
                       dict(document_id='shared', title='tofu beans', summary='related source',
                            text='abcdefghij' * 15, source_url='https://example.invalid/shared', item_ids=[])]

    def test_own_document_overrides_llm_rejection_length_and_candidate_cap(self):
        calls = []
        def ask(prompt, payload, config):
            calls.append(payload)
            return '["beans"]' if isinstance(payload, dict) and 'candidates' not in payload else '[]'
        with tempfile.TemporaryDirectory() as t:
            chunks, report = collect(self.item, self.bundle, self.options, {}, Path(t), ask)
            self.assertEqual(report['queries'][0], 'tofu')
            self.assertEqual(report['mandatory_ids'], ['own'])
            self.assertEqual([c['document_id'] for c in chunks], ['own'])
            self.assertEqual(chunks[0]['text'], 'short')
            self.assertNotIn('text', calls[1]['candidates'][0])
            repeat, cached = collect(self.item, self.bundle, self.options, {}, Path(t),
                                     lambda *a: self.fail('LLM called on cache hit'))
            self.assertEqual(chunks, repeat)
            self.assertEqual(cached['query_cache_hits'], len(cached['queries']))

    def test_chunk_overlap_and_shared_document_item_ids(self):
        self.options['max_candidates_per_query'] = 2
        def ask(prompt, payload, config):
            return '["tofu"]' if 'candidates' not in payload else '["shared"]'
        with tempfile.TemporaryDirectory() as t:
            first, _ = collect(self.item, self.bundle, self.options, {}, Path(t), ask)
            other = dict(id='recipe:2', name='tofu', ingredients='bean')
            bundle = [d | {'item_ids': ['recipe:1', 'recipe:2']} if d['document_id'] == 'own' else d for d in self.bundle]
            second, _ = collect(other, bundle, self.options, {}, Path(t), ask)
            self.assertFalse({c['id'] for c in first} & {c['id'] for c in second})
            shared = [c for c in first if c['document_id'] == 'shared']
            self.assertEqual(shared[0]['text'][-3:], shared[1]['text'][:3])
            rebuilt = shared[0]['text'] + ''.join(c['text'][3:] for c in shared[1:])
            self.assertEqual(rebuilt, self.bundle[1]['text'])
            out = Path(t) / 'chunks.jsonl'
            store_chunks(first, self.item['id'], out)
            store_chunks(second, other['id'], out)
            store_chunks(first, self.item['id'], out)
            self.assertEqual(len(out.read_text(encoding='utf-8').splitlines()), len(first) + len(second))

    def test_invalid_json_and_configuration_fail(self):
        for raw in ('plain text', '{}', '[1]', '[""]'):
            with self.assertRaises((ValueError, json.JSONDecodeError)):
                string_array(raw)
        with self.assertRaises(ValueError):
            string_array('["unknown"]', allowed={'own'})
        with self.assertRaises(ValueError):
            list(split_text('abc', 10, 10))

    def test_real_bundle_has_all_selected_recipes(self):
        bundle = load_bundle()
        recipes = json.loads((Path(__file__).resolve().parents[1] / 'data/recipes.json').read_text(encoding='utf-8'))
        item_ids = {i for d in bundle for i in d['item_ids']}
        self.assertTrue({'recipe:' + r['recipe_id'] for r in recipes} <= item_ids)
