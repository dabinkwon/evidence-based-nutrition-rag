import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from nutrition_search import protein_request, search, rank_by_ingredient
from recipe_rag import documents
from rag_graph import build_graph


class NutritionSearchChecks(unittest.TestCase):
    def test_ingredient_rank_converts_basis_and_rejects_wrong_state(self):
        request=protein_request('단백질 함량이 높은 재료가 들어간 요리')
        self.assertEqual(request['mode'],'ingredient_rank')
        tofu=self.doc('두부', 99) | dict(ingredients='두부 100g')
        egg=self.doc('달걀', 1) | dict(ingredients='달걀 50g')
        def food(name,protein,basis=100):
            return dict(name=name,protein_g=protein,basis_amount=basis,basis_unit='g',data_group='원재료성',source_url='https://example.org/food')
        records=[food('두부',4,50),food('두부, 유부',40),food('달걀, 전란, 생것',12),food('달걀, 난백, 말린것',80)]
        result=rank_by_ingredient([tofu,egg],request,records=records)
        self.assertEqual([d['title'] for d in result['evidence']],['달걀','두부'])
        self.assertEqual(result['evidence'][1]['ingredient_protein_per100'],8)
        self.assertEqual(len(result['generation']['citations']),4)
        self.assertEqual(len(rank_by_ingredient([tofu,egg],request,excluded=['달걀'],records=records)['evidence']),1)
        self.assertEqual(rank_by_ingredient([tofu],request,records=[food('두부, 유부',40)])['evidence'],[])

    def test_actual_ingredient_rank_returns_sorted_supported_candidates(self):
        result=search(documents(),protein_request('단백질 함량이 높은 재료가 들어간 요리'))
        self.assertTrue(result['evidence'])
        values=[d['ingredient_protein_per100'] for d in result['evidence']]
        self.assertEqual(values,sorted(values,reverse=True))
        self.assertTrue(all(d['ingredient_source_url'] for d in result['evidence']))

    def doc(self, name, protein, **extra):
        return dict(id='recipe:'+name, collection='recipes', title=name,
                    ingredients=name, text=name, source_url='https://example.org/recipe',
                    nutrition_raw=dict(INFO_PRO=protein), **extra)

    def test_presence_validates_own_value_without_content_ranking(self):
        docs=[self.doc('두부', '2'), self.doc('달걀', '50')]
        docs += [self.doc(str(x), x) for x in (None, '', 0, -1, 'nan', 'inf', True)]
        result=search(docs, protein_request('단백질이 들어간 요리'))
        self.assertEqual([d['title'] for d in result['evidence']], ['달걀', '두부'])
        self.assertIn('기준량 미확인', result['evidence'][0]['nutrition_reason'])
        self.assertEqual(len(result['generation']['citations']), 2)
        self.assertIn('이름순', result['generation']['answer'])

    def test_does_not_infer_protein_from_ingredient_or_generic_food(self):
        doc=self.doc('두부 달걀', '')
        self.assertEqual(search([doc],protein_request('단백질 요리 추천'))['evidence'], [])

    def test_ingredient_and_exclusion_constraints(self):
        docs=[self.doc('두부 새우', 5), self.doc('두부', 3), self.doc('호박', 1)]
        request=protein_request('새우 빼고 두부가 들어간 단백질 요리 추천')
        self.assertEqual([d['title'] for d in search(docs,request)['evidence']], ['두부'])
        self.assertEqual(search(docs, request, excluded=['두부'])['evidence'], [])

    def test_ambiguous_and_combined_constraints_ask_for_clarification(self):
        for question in ('고단백 요리 추천', '단백질 많은 음식', '단백질 25g 이상 요리',
                         '저염 단백질 요리', '단백질 안 들어간 요리', '1인분 단백질 -25g 이상 요리', '1인분 단백질 30g 이상 20g 이하 요리'):
            request=protein_request(question)
            self.assertEqual(request['mode'],'clarify',question)
            self.assertEqual(search([],request)['generation']['status'],'nutrition_clarify')
        self.assertIsNone(protein_request('두부 단백질은 얼마야?'))
        self.assertIsNone(protein_request('이 요리의 단백질은?'))

    def test_quantity_uses_verified_same_basis_only(self):
        def verified(protein,basis='serving',verified=True):
            return dict(protein_g=protein,basis=basis,serving_grams=200,verified=verified,source_url='https://example.org/verified')
        docs=[self.doc('미확인', 99), self.doc('통과', 1, verified_nutrition=verified(25)),
              self.doc('낮음', 99, verified_nutrition=verified(24.9)),
              self.doc('다른기준', 99, verified_nutrition=verified(30,'100g')),
              self.doc('미검증', 99, verified_nutrition=verified(30,verified=False))]
        result=search(docs,protein_request('1인분 단백질 25g 이상 요리'))
        self.assertEqual([d['title'] for d in result['evidence']], ['통과'])
        self.assertEqual(result['generation']['citations'][0]['source_url'], 'https://example.org/verified')
        result=search(docs,protein_request('100g당 단백질 30g 이하 요리'))
        self.assertEqual([d['title'] for d in result['evidence']], ['다른기준'])
        docs[1]['verified_nutrition'].pop('serving_grams')
        self.assertEqual(search(docs,protein_request('1인분 단백질 25g 이상 요리'))['evidence'], [])

    def test_graph_uses_structured_retrieval_not_embedding_or_generation(self):
        state=dict(question='단백질이 들어간 요리', docs=[self.doc('두부', 2)], selected=None,
                   excluded=[],config={},options=dict(top_k=3,min_score=.3),retriever='chroma',do_generate=True)
        with patch('index_vectors.retrieve') as backend, patch('recipe_rag.generate') as generate:
            result=build_graph().invoke(state)
        self.assertEqual(result['generation']['status'],'ingredient_blocked')
        self.assertEqual(result['evidence'],[])
        backend.assert_not_called()
        generate.assert_not_called()

    def test_actual_local_data_matches_have_positive_source_values(self):
        docs=documents()
        result=search(docs,protein_request('단백질이 들어간 요리'))
        self.assertTrue(result['evidence'])
        for doc in result['evidence']:
            self.assertGreater(float(doc['nutrition_raw']['INFO_PRO']),0)
            self.assertTrue(doc['source_url'])
        self.assertEqual(search(docs,protein_request('1인분 단백질 25g 이상 요리'))['generation']['status'], 'nutrition_no_match')
