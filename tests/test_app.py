from pathlib import Path
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / 'scripts'))


class AppChecks(unittest.TestCase):
    def test_expanded_health_lookup_and_unsupported_food_notice(self):
        app = self.open_page()
        with patch('openai.OpenAI') as api:
            app.text_input(key='recipe_question_text').set_value('마늘이 몸에 뭐가 좋아?')
            next(b for b in app.button if b.label == '검색·질문하기').click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertTrue(any('마늘' in m.value and '확보한 자료' in m.value for m in app.markdown))
            app.text_input(key='recipe_question_text').set_value('두부 효능 알려줘')
            next(b for b in app.button if b.label == '검색·질문하기').click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any('두부의 효능 연구는' in m.value for m in app.markdown))
        self.assertTrue(any('현재 연구자료가 확보된 식품' in c.value for c in app.caption))
        api.assert_not_called()

    def test_eggplant_health_question_uses_local_research_without_external_generation(self):
        app = self.open_page()
        with patch('openai.OpenAI') as api:
            app.text_input(key='recipe_question_text').set_value('가지가 몸에 뭐가 좋아?')
            next(b for b in app.button if b.label == '검색·질문하기').click().run()
        self.assertEqual(len(app.exception), 0)
        api.assert_not_called()
        self.assertTrue(any('인체적용시험' in m.value and '혈압 조절' in m.value for m in app.markdown))
        self.assertTrue(any('동물시험' in m.value for m in app.markdown))
        self.assertTrue(any('효과의 크기나 확실성' in m.value for m in app.markdown))
        self.assertEqual(len(app.dataframe), 1)
        self.assertEqual(sum(button.label == '원문 출처 보기' for button in app.link_button), 2)

    def test_uncollected_ingredient_nutrition_is_not_recommendation_block(self):
        app=self.open_page()
        app.text_input(key='recipe_question_text').set_value('방울토마토 영양정보')
        next(b for b in app.button if b.label=='검색·질문하기').click().run()
        self.assertEqual(len(app.exception),0)
        self.assertTrue(any('아직 데이터가 없는 재료: 방울토마토' in m.value for m in app.markdown))
        self.assertFalse(any('검색은 중단' in m.value for m in app.markdown))
    def test_ingredient_only_find_and_chat(self):
        app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
        app.text_input(key='ui_recipe_search').set_value('두부')
        next(b for b in app.button if b.label=='요리 찾기').click().run()
        self.assertTrue(app.session_state['candidates'])
        self.assertTrue(all('두부' in d['ingredients'] for d in app.session_state['candidates']))
        app.text_input(key='ui_recipe_search').set_value('단백질이 많은 요리')
        next(b for b in app.button if b.label=='요리 찾기').click().run()
        self.assertEqual(app.session_state['candidates'],[])
        self.assertTrue(any('중단' in i.value for i in app.info))
        app.sidebar.radio[0].set_value('요리 대화·영양정보').run()
        app.text_input(key='recipe_question_text').set_value('계란')
        next(b for b in app.button if b.label=='검색·질문하기').click().run()
        self.assertTrue(any('재료 원문에서' in m.value for m in app.markdown))
        self.assertEqual(len(app.exception),0)
    def test_selected_recipe_ingredient_question_and_recent_search_anchor(self):
        app=self.open_page()
        result=dict(answer='원재료 후보',citations=[],nutrition_rows=[{'레시피 재료':'연두부','기준량':'100g','출처':'https://example.org'}])
        with patch('ingredient_lookup.lookup',return_value=result) as find:
            app.text_input(key='recipe_question_text').set_value('그 재료들의 영양성분은?')
            next(b for b in app.button if b.label=='검색·질문하기').click().run()
        self.assertEqual(len(app.exception),0)
        self.assertIn('연두부',find.call_args.args[0])
        self.assertEqual(len(app.dataframe),1)
        self.assertFalse(any('중단' in m.value for m in app.markdown))
        self.assertTrue(any('chat-turn-2' in m.value for m in app.markdown))
    def open_page(self,profile=False):
        app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
        app.sidebar.radio[0].set_value('내 정보로 음식 비교' if profile else '요리 대화·영양정보').run()
        return app

    def test_navigation_only_renders_selected_page_and_keeps_input(self):
        app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
        self.assertEqual(len(app.tabs),0)
        self.assertFalse(any(b.label=='계산하고 음식 찾기' for b in app.button))
        app.sidebar.radio[0].set_value('내 정보로 음식 비교').run()
        app.number_input(key='ui_weight').set_value(80.)
        next(b for b in app.button if b.label=='계산하고 음식 찾기').click().run()
        app.sidebar.radio[0].set_value('요리 찾기').run()
        self.assertFalse(any(b.label=='계산하고 음식 찾기' for b in app.button))
        app.sidebar.radio[0].set_value('내 정보로 음식 비교').run()
        self.assertEqual(app.number_input(key='ui_weight').value,80.)
        self.assertEqual(len(app.exception),0)
    def test_profile_resubmit_clears_old_result_before_work(self):
        import streamlit as st
        import energy_profile
        app=self.open_page(profile=True)
        next(c for c in app.checkbox if '임신' in c.label).check()
        submit=lambda: next(b for b in app.button if b.label=='계산하고 음식 찾기')
        submit().click().run()
        self.assertTrue(app.session_state['profile_result']['rows'])
        original=energy_profile.calculate
        cleared=[]
        def checked_calculate(*args,**kwargs):
            cleared.append('profile_result' not in st.session_state)
            return original(*args,**kwargs)
        with patch('energy_profile.calculate',side_effect=checked_calculate):
            submit().click().run()
        self.assertEqual(cleared,[True])
        self.assertEqual(len(app.exception),0)
        self.assertTrue(any('profile-result-focus' in m.value for m in app.markdown))
        with patch('energy_profile.calculate',side_effect=RuntimeError('INTERNAL_ERROR')):
            submit().click().run()
        self.assertIn('error',app.session_state['profile_result'])
        self.assertFalse(any('열량_kcal' in t.value.columns for t in app.dataframe))
        self.assertFalse(any('INTERNAL_ERROR' in w.value for w in app.warning))
    def test_stale_energy_module_is_refreshed(self):
        import energy_profile
        import importlib
        try:
            del energy_profile.assess_foods
            app=self.open_page(profile=True)
            self.assertEqual(len(app.exception),0)
            self.assertTrue(callable(energy_profile.assess_foods))
        finally:
            importlib.reload(energy_profile)
    def test_recipe_question_answers_in_chat_without_source_panel(self):
        app=self.open_page(profile=False)
        self.assertFalse(any(e.label=='재료와 조리법 원문' for e in app.expander))
        with patch('rag_graph.build_graph') as build:
            build.return_value.stream.return_value=iter([{'generate':{'generation':dict(answer='합성 답변',citations=[])}}])
            app.text_input(key='recipe_question_text').set_value('조리법 알려줘')
            next(b for b in app.button if b.label=='검색·질문하기').click().run()
        self.assertEqual(len(app.exception),0)
        self.assertFalse(any(e.label=='재료와 조리법 원문' for e in app.expander))
        self.assertTrue(any('합성 답변' in m.value for m in app.markdown))
        self.assertTrue(any('chat-turn-' in m.value for m in app.markdown))
        app.button(key='clear_conversation').click().run()
        self.assertFalse(any(e.label=='재료와 조리법 원문' for e in app.expander))
    def test_profile_calculation_form(self):
        app=self.open_page(profile=True)
        app.session_state['main_tabs']='내 정보로 음식 비교'
        app.run()
        next(c for c in app.checkbox if '임신' in c.label).check()
        next(b for b in app.button if b.label=='계산하고 음식 찾기').click().run()
        self.assertEqual(len(app.exception),0)
        self.assertTrue(any(m.label=='하루 유지 에너지 참고값' for m in app.metric))
        self.assertEqual(app.session_state['main_tabs'],'내 정보로 음식 비교')
        self.assertTrue(app.session_state['profile_result']['rows'])
        self.assertTrue(any('열량_kcal' in table.value.columns for table in app.dataframe))
        self.assertEqual(len(app.session_state['profile_result']['rows']),5)
        self.assertTrue(any('비교 예산 이내' in x.value for x in app.markdown))
        self.assertTrue(any('예산 초과' in x.value for x in app.markdown))
        self.assertEqual(len(app.metric),3)
        self.assertFalse(any('판단에 필요한 정보 부족' in x.value for x in app.markdown))
        self.assertFalse(any(any(icon in x.value for icon in ('✅','⚠️','❔')) for x in app.markdown))
        app.run()
        self.assertTrue(any(m.label=='하루 유지 에너지 참고값' for m in app.metric))
        self.assertTrue(any('열량_kcal' in table.value.columns for table in app.dataframe))

    def test_profile_excluded_candidate_block_is_explained(self):
        app=self.open_page(profile=True)
        app.sidebar.text_input[0].set_value('새우').run()
        next(c for c in app.checkbox if '임신' in c.label).check()
        next(b for b in app.button if b.label=='계산하고 음식 찾기').click().run()
        self.assertEqual(len(app.exception),0)
        self.assertTrue(any('### 비교 예산 이내' in x.value for x in app.markdown))
        self.assertFalse(any('재료 목록이 없어' in x.value for x in app.caption))
        first=[(a['food']['food_id'],a.get('delta_kcal')) for a in app.session_state['profile_result']['assessments']]
        app.sidebar.text_input[0].set_value('닭').run()
        self.assertEqual(first,[(a['food']['food_id'],a.get('delta_kcal')) for a in app.session_state['profile_result']['assessments']])
        previous=app.session_state['profile_result']
        previous.pop('comparison_version')
        for item in previous['assessments']:
            item.update(status='unknown',nutrition=None,reason='OLD_EXCLUSION_MESSAGE')
        app.session_state['profile_result']=previous
        app.run()
        self.assertEqual(first,[(a['food']['food_id'],a.get('delta_kcal')) for a in app.session_state['profile_result']['assessments']])
        self.assertFalse(any('OLD_EXCLUSION_MESSAGE' in m.value for m in app.markdown))
        self.assertFalse(any('### 에너지 조건 충족' in x.value for x in app.markdown))
        self.assertTrue(any('열량_kcal' in table.value.columns for table in app.dataframe))

    def test_profile_activity_and_validation_result(self):
        app=self.open_page(profile=True)
        next(b for b in app.button if b.label=='계산하고 음식 찾기').click().run()
        self.assertIn('error',app.session_state['profile_result'])
        self.assertTrue(any('확인란이 체크되지 않았습니다' in w.value and '체크한 뒤 다시 계산' in w.value for w in app.warning))
        next(c for c in app.checkbox if '임신' in c.label).check()
        next(s for s in app.selectbox if s.label=='활동 범주').select('active')
        next(b for b in app.button if b.label=='계산하고 음식 찾기').click().run()
        self.assertEqual(len(app.exception),0)
        self.assertEqual(app.session_state['profile_result']['calc']['activity_factor'],1.75)
    def test_latest_question_pair_is_first(self):
        app=self.open_page(profile=False)
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
        app=self.open_page(profile=False)
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
            app=self.open_page(profile=False)
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
            app=self.open_page(profile=False)
            self.assertEqual(len(app.exception),0)
            self.assertFalse(any('private internal detail' in w.value for w in app.warning))

    def test_excluded_selection_and_old_answer_hidden(self):
        with patch('index_vectors.client_for'), patch('index_vectors.counts',return_value={'recipe_meta':100,'source_docs':1}):
            app=self.open_page(profile=False)
            app.session_state['conversations']['recipe:28']=[dict(role='assistant',result=dict(answer='OLD_RESULT',citations=[]),excluded=[])]
            app.sidebar.text_input[0].set_value('새우').run()
            self.assertEqual(len(app.exception),0)
            self.assertTrue(any('추천에서 차단' in w.value for w in app.warning))
            self.assertFalse(any('OLD_RESULT' in x.value for x in app.markdown))

    def test_nutrition_search_and_theme_native(self):
        import json
        foods=json.loads((ROOT/'data/foods_extended.json').read_text(encoding='utf-8'))
        with patch('index_vectors.client_for'), patch('index_vectors.counts',return_value={'recipe_meta':100,'source_docs':1}):
            app=self.open_page(profile=False)
            self.assertFalse(any('영양정보 검색 결과' in x.value for x in app.subheader))
            app.text_input(key='recipe_question_text').set_value(foods[0]['name'])
            next(b for b in app.button if b.label=='검색·질문하기').click().run()
            self.assertEqual(len(app.exception),0)
            self.assertEqual(len(app.dataframe),1)
            self.assertTrue(any('음식 영양정보' in x.value for x in app.markdown))
            self.assertFalse(any('영양정보 검색 결과' in x.value for x in app.subheader))
            self.assertIn('기준량',app.dataframe[0].value.columns)
            self.assertTrue(any(foods[0]['name']==x for x in app.dataframe[0].value['음식·재료']))
            self.assertFalse(any(s.label=='식품명과 기준량 확인' for s in app.selectbox))
        source=(ROOT/'app.py').read_text(encoding='utf-8')
        self.assertNotIn('background:#',source)
