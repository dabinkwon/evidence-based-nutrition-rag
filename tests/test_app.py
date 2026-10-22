from pathlib import Path
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / 'scripts'))


class AppChecks(unittest.TestCase):
    def test_latest_question_pair_is_first(self):
        app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
        selected=app.session_state['selected_recipe']
        app.session_state['conversations'][selected]=[
            dict(role='user',content='FIRST_QUESTION'),
            dict(role='assistant',result=dict(answer='FIRST_ANSWER',citations=[]),excluded=[]),
            dict(role='user',content='LATEST_QUESTION'),
            dict(role='assistant',result=dict(answer='LATEST_ANSWER',citations=[]),excluded=[])]
        app.run()
        self.assertEqual(len(app.exception),0)
        text=[m.value for m in app.markdown if m.value in ('FIRST_QUESTION','FIRST_ANSWER','LATEST_QUESTION','LATEST_ANSWER')]
        self.assertEqual(text,['LATEST_QUESTION','LATEST_ANSWER','FIRST_QUESTION','FIRST_ANSWER'])
        self.assertEqual(len(app.chat_input),0)
        self.assertIn('영양정보',app.text_input(key='recipe_question_text').label)

    def test_clear_button_clears_only_current_recipe(self):
        app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
        selected=app.session_state['selected_recipe']
        app.session_state['conversations'][selected]=[dict(role='user',content='CLEAR_ME')]
        app.session_state['conversations']['other']=[dict(role='user',content='KEEP_ME')]
        app.session_state['nutrition_queries'][selected]='두부'
        app.button(key='clear_conversation').click().run()
        self.assertEqual(len(app.exception),0)
        self.assertEqual(app.session_state['conversations'][selected],[])
        self.assertNotIn(selected,app.session_state['nutrition_queries'])
        self.assertEqual(app.session_state['conversations']['other'][0]['content'],'KEEP_ME')
    def test_initial_render_and_recipe_switch(self):
        with patch('index_vectors.client_for'), patch('index_vectors.counts',return_value={'recipe_meta':100,'source_docs':1}):
            app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
            self.assertEqual(len(app.exception),0)
            self.assertEqual(len(app.metric),0)
            self.assertFalse(any('연결 상태' in e.label for e in app.expander))
            first=app.session_state['selected_recipe']
            app.session_state['conversations'][first]=[dict(role='user',content='합성 질문')]
            # selectbox options displayed labels; use the actual recipe ID list.
            import json
            recipes=json.loads((ROOT/'data/recipes.json').read_text(encoding='utf-8'))
            second_id='recipe:'+recipes[1]['recipe_id']
            app.sidebar.selectbox[0].select(second_id).run()
            self.assertEqual(len(app.exception),0)
            self.assertEqual(app.session_state['conversations'][first][0]['content'],'합성 질문')
            self.assertEqual(app.session_state['conversations'][second_id],[])

    def test_missing_database_is_safe(self):
        with patch('index_vectors.client_for',side_effect=RuntimeError('private internal detail')):
            app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
            self.assertEqual(len(app.exception),0)
            self.assertFalse(any('private internal detail' in w.value for w in app.warning))

    def test_excluded_selection_and_old_answer_hidden(self):
        with patch('index_vectors.client_for'), patch('index_vectors.counts',return_value={'recipe_meta':100,'source_docs':1}):
            app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
            app.session_state['conversations']['recipe:28']=[dict(role='assistant',result=dict(answer='OLD_RESULT',citations=[]),excluded=[])]
            app.sidebar.text_input[0].set_value('새우').run()
            self.assertEqual(len(app.exception),0)
            self.assertTrue(any('추천에서 차단' in w.value for w in app.warning))
            self.assertFalse(any('OLD_RESULT' in x.value for x in app.markdown))

    def test_nutrition_search_and_theme_native(self):
        import json
        foods=json.loads((ROOT/'data/foods_extended.json').read_text(encoding='utf-8'))
        with patch('index_vectors.client_for'), patch('index_vectors.counts',return_value={'recipe_meta':100,'source_docs':1}):
            app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
            self.assertFalse(any('영양정보 검색 결과' in x.value for x in app.subheader))
            app.text_input(key='recipe_question_text').set_value(foods[0]['name'])
            next(b for b in app.button if b.label=='검색·질문하기').click().run()
            self.assertEqual(len(app.exception),0)
            self.assertEqual(len(app.dataframe),1)
            self.assertTrue(any('영양정보 검색 결과' in x.value for x in app.subheader))
            self.assertIn('기준량',app.dataframe[0].value.columns)
            self.assertTrue(any(foods[0]['name']==x for x in app.dataframe[0].value['음식·재료']))
            self.assertFalse(any(s.label=='식품명과 기준량 확인' for s in app.selectbox))
        source=(ROOT/'app.py').read_text(encoding='utf-8')
        self.assertNotIn('background:#',source)
