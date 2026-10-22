"""Local Streamlit interface. Conversation data stays in session memory."""
import json
from pathlib import Path
import sys
import re

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
import streamlit as st
from recipe_rag import documents, settings, excluded_hits, generate
from rag_graph import build_graph, answer_options, evidence_context, nutrition_discovery_notice
from nutrition_search import protein_request, search as search_protein
from ingredient_search import search as search_ingredients, nutrition_blocked, is_ingredient_query

st.set_page_config(page_title='한끼의 근거', layout='wide', initial_sidebar_state='expanded')
st.markdown('''<style>
.stButton>button {border-radius:12px} .block-container {padding-top:2.5rem;max-width:1250px}
[data-testid="stAppDeployButton"] {display:none}
h1 {font-size:2rem!important;letter-spacing:-.04em}
h2 {font-size:1.5rem!important;letter-spacing:-.025em}
h3 {font-size:1.15rem!important;line-height:1.5!important}
[data-testid="stMarkdownContainer"] p {line-height:1.8}
[data-testid="stWidgetLabel"] p {font-weight:600}
[data-testid="stChatMessage"] {padding:1.25rem;margin-bottom:1rem}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) p {font-weight:600}
[data-testid="stMetric"] {padding:1rem;border:1px solid color-mix(in srgb,var(--text-color) 14%,transparent);border-radius:12px}
[data-testid="stMetricValue"] {font-size:1.9rem;font-weight:700;letter-spacing:-.04em}
.st-key-profile_summary [data-testid="stColumn"]:last-child [data-testid="stMetricValue"] {font-size:1.45rem}
@media(max-width:760px) {
 .block-container {padding:1.25rem 1rem}
 [data-testid="stHorizontalBlock"] {flex-wrap:wrap;gap:.75rem}
 [data-testid="stColumn"] {width:100%!important;flex:1 1 100%!important;min-width:0!important}
}
</style>''', unsafe_allow_html=True)


def show_generation(result):
    if result.get('answer'):
        st.markdown(result['answer'])
    else:
        st.warning({'not_configured':'현재 답변 서비스를 이용할 수 없습니다. 잠시 후 다시 시도해 주세요.', 'api_error':'답변 요청에 실패했습니다. 잠시 후 다시 시도해 주세요.',
                    'invalid_citations':'출처를 확인할 수 없어 답변을 표시하지 않습니다.'}.get(result.get('status'), '답변을 확인할 수 없습니다.'))
    if result.get('citation_notice'):
        st.caption(result['citation_notice'])
    if result.get('nutrition_rows'):
        st.caption('음식별 기준량을 확인하세요. 선택 요리의 영양값과 별도입니다.')
        st.dataframe(result['nutrition_rows'],hide_index=True,width='stretch',
            column_config={'출처':st.column_config.LinkColumn('출처',display_text='원문 보기')})
    for c in result.get('citations', []):
        with st.expander(f"근거 {c['number']} · {c['title']} · {c['source_label']}"):
            st.link_button('원문 출처 보기', c['source_url'])


docs = documents()
recipes = json.loads((ROOT / 'data/recipes.json').read_text(encoding='utf-8'))
by_id = {'recipe:'+r['recipe_id']:r for r in recipes}
st.session_state.setdefault('conversations', {})
st.session_state.setdefault('candidates', [])
st.session_state.setdefault('nutrition_queries', {})
# Restore inputs after Streamlit cleans up widgets on a hidden page.
st.session_state.setdefault('saved_inputs',{})
for input_key,input_value in st.session_state.saved_inputs.items():
    if input_key not in st.session_state:
        st.session_state[input_key]=input_value
foods=json.loads((ROOT/'data/foods_extended.json').read_text(encoding='utf-8'))


def focus_profile_result(target_id='profile-result-focus'):
    """Move the viewport and keyboard focus to this submission's live status."""
    script='''<script>
    (() => {
    const root = document;
    let attempts = 0;
    function focusResult() {
      const target = root.getElementById(TARGET_ID);
      if (target) {
        target.focus({preventScroll:true});
        target.scrollIntoView({behavior:'instant',block:'start'});
      } else if (++attempts < 30) { setTimeout(focusResult, 50); }
    }
    focusResult();
    })();
    </script>'''
    st.html(script.replace('TARGET_ID',json.dumps(target_id)),unsafe_allow_javascript=True)


def clear_current_conversation():
    item=st.session_state.selected_recipe
    st.session_state.conversations[item]=[]
    st.session_state.nutrition_queries.pop(item,None)
    st.session_state.recipe_question_text=''
    st.session_state.cleared_recipe=item

with st.sidebar:
    st.title('한끼의 근거')
    st.caption('재료에서 시작하는 식생활 탐색')
    page=st.radio('메뉴',['요리 찾기','요리 대화·영양정보','다른 요리와 비교','내 정보로 음식 비교'],key='main_tabs',label_visibility='collapsed')
    st.divider()
    selected = st.selectbox('이야기할 요리', list(by_id), format_func=lambda i: by_id[i]['name'], key='selected_recipe')
    excluded_text = st.text_input('제외할 재료', placeholder='새우, 계란, 우유',key='ui_excluded')
    excluded = [x.strip() for x in excluded_text.split(',') if x.strip()]
    st.caption('적용 중인 제외 재료: '+(', '.join(excluded) if excluded else '없음'))
    st.caption('제외 검사는 알려진 동의어 기준이며 알레르기 안전을 보장하지 않습니다.')
    st.divider()
    if page=='요리 대화·영양정보':
        st.button('이 요리의 대화 지우기',width='stretch',on_click=clear_current_conversation,key='clear_conversation')
        if st.session_state.get('cleared_recipe')==selected:
            st.caption('이 요리의 대화를 지웠습니다.')

st.title('한끼의 근거')
st.caption('요리를 찾고, 영양정보와 선택 이유를 출처로 확인하세요.')
with st.expander('이용 범위 안내'):
    st.write('일반 식생활 정보이며 전문가 조언을 대신하지 않습니다. 레시피 영양 기준량은 미확인이므로 제공량 환산을 하지 않습니다. 내 정보의 에너지 계산은 참고 추정이며 음식 비교 조건은 사용자가 정합니다.')
if page=='요리 찾기':
    st.subheader('어떤 요리를 찾으세요?')
    with st.form('find_recipes'):
        query = st.text_input('어떤 요리를 찾으세요?', placeholder='두부 / 두부, 달걀',key='ui_recipe_search')
        search = st.form_submit_button('요리 찾기', type='primary')
    st.caption('재료 이름으로 검색합니다. 여러 재료는 쉼표로 구분하면 모두 포함된 요리를 찾습니다. 제외 재료는 왼쪽에 입력하세요.')
    if search and query.strip():
        with st.spinner('관련 레시피와 근거를 검색하고 있습니다…'):
            state = build_graph().invoke(dict(question=query,docs=docs,selected=None,excluded=excluded,
                config=settings(),options=answer_options(),retriever='chroma',do_generate=False))
        st.session_state.candidates = [d for d in state['evidence'] if d['collection']=='recipes' and not excluded_hits(d,excluded)]
        st.session_state.recipe_search_notice = state.get('generation', {}).get('answer') if not st.session_state.candidates else None
        protein_query=None
        st.session_state.recipe_search_summary = ('재료 영양 후보의 100g당 단백질 함량 내림차순입니다. 요리 전체·1인분 함량 순위가 아닙니다.' if protein_query and protein_query['mode']=='ingredient_rank' else ('단백질 포함은 고단백을 뜻하지 않습니다. API 기준량은 미확인이며 함량순이 아닌 이름순으로 표시합니다.'
            if protein_query['mode']=='presence' else '검증된 기준량의 단백질 값으로 조건을 검사했습니다. 이름순으로 표시합니다.')
            if protein_query and st.session_state.candidates else None)
        for warning in state['warnings']:
            st.warning('검색을 완료하지 못했습니다. 잠시 후 다시 시도해 주세요.')
    visible_candidates = [d for d in st.session_state.candidates if not excluded_hits(d,excluded)]
    if st.session_state.candidates and not visible_candidates:
        st.warning('현재 제외 조건을 적용하면 표시할 후보가 없습니다. 다른 요리를 검색해 주세요.')
    if st.session_state.get('recipe_search_notice'):
        st.info(st.session_state.recipe_search_notice)
    elif not st.session_state.candidates:
        st.caption('검색하면 여기에서 후보 요리를 확인할 수 있습니다.')
    if st.session_state.get('recipe_search_summary'):
        st.caption(st.session_state.recipe_search_summary)
    for d in st.session_state.candidates:
        if excluded_hits(d,excluded):
            continue
        with st.container(border=True):
            st.subheader(d['title'])
            if d.get('ingredient_reason'):
                st.write(d['ingredient_reason'])
            if d.get('nutrition_reason'):
                st.write(d['nutrition_reason'])
            if d.get('ingredient_source_url'):
                st.link_button('재료 영양정보 출처', d['ingredient_source_url'])
            st.write(d.get('ingredients',''))
            st.link_button('레시피 출처', d['source_url'])
            def choose(item_id):
                st.session_state.selected_recipe = item_id
                st.session_state.main_tabs='요리 대화·영양정보'
            st.button('이 요리 선택',key='choose_'+d['id'], on_click=choose,args=(d['id'],))

if page=='요리 대화·영양정보':
    st.subheader(by_id[selected]['name'])
    st.caption('선택 요리의 영양정보')
    raw=by_id[selected]['nutrition_raw']
    recipe_fields=[('열량','INFO_ENG','kcal'),('탄수화물','INFO_CAR','g'),('단백질','INFO_PRO','g'),('지방','INFO_FAT','g'),('나트륨','INFO_NA','mg')]
    st.table([{'영양소':label,'API 원문 값':raw.get(key) or '미제공','단위':unit} for label,key,unit in recipe_fields])
    st.caption('레시피 API 원문 값 · 기준량 미확인. 1인분 또는 100g으로 해석하지 않습니다.')
    st.link_button('레시피 영양정보 출처',by_id[selected]['source_url'])
    st.divider()
    r = by_id[selected]
    selected_hits=excluded_hits(next(d for d in docs if d['id']==selected),excluded)
    if selected_hits:
        st.warning('선택 요리에 제외 재료가 있습니다: '+', '.join(selected_hits)+'. 이 요리는 추천에서 차단됩니다.')
    if not any(d.get('related_item_id')==selected for d in docs if d['collection']!='recipes'):
        st.caption('현재 제공된 레시피 원문을 바탕으로 답변합니다. 원문에 없는 정보는 확인이 어려울 수 있습니다.')
    messages = st.session_state.conversations.setdefault(selected, [])
    with st.form('recipe_question',clear_on_submit=True):
        st.markdown('### 무엇이 궁금하세요?')
        question = st.text_input('요리 질문 또는 음식·재료 영양정보 검색',placeholder='만드는 법 알려줘 / 두부 영양성분 / 음식 이름',key='recipe_question_text')
        submitted = st.form_submit_button('검색·질문하기',type='primary')
    prompt = question.strip() if submitted else ''
    new_chat_result=bool(prompt)
    if prompt and (nutrition_blocked(prompt) or is_ingredient_query(docs,prompt)):
        messages.append(dict(role='user',content=prompt))
        ingredient_result=search_ingredients(docs,prompt,excluded,answer_options()['top_k'])
        messages.append(dict(role='assistant',result=ingredient_result['generation'],excluded=sorted(excluded)))
        prompt=''
    protein_condition=protein_request(prompt)
    if protein_condition:
        messages.append(dict(role='user',content=prompt))
        protein_result=search_protein(docs,protein_condition,excluded,answer_options()['top_k'])
        messages.append(dict(role='assistant',result=protein_result['generation'],excluded=sorted(excluded)))
        prompt=''
    discovery_notice=nutrition_discovery_notice(prompt)
    if discovery_notice:
        messages.append(dict(role='user',content=prompt))
        messages.append(dict(role='assistant',result=dict(answer=discovery_notice,citations=[]),excluded=sorted(excluded)))
        prompt=''
    nutrient_search=bool(prompt and (any(t in prompt for t in ('영양','성분','단백질','탄수화물','나트륨')) or any(prompt==f['name'] for f in foods)))
    from ingredient_lookup import query_ingredients, lookup as lookup_ingredients
    ingredient_names=query_ingredients(prompt,r) if nutrient_search else []
    if ingredient_names:
        messages.append(dict(role='user',content=prompt))
        messages.append(dict(role='assistant',result=lookup_ingredients(ingredient_names),excluded=sorted(excluded)))
        prompt=''
        nutrient_search=False
    if nutrient_search:
        term=re.split(r'영양|성분|단백질|탄수화물|나트륨',prompt,maxsplit=1)[0].strip()
        term=re.sub(r'(의|에는|은|는|을|를)$','',term).strip()
        st.session_state.nutrition_queries[selected]=term
        messages.append(dict(role='user',content=prompt))
        found=[f for f in foods if term and term.casefold() in f['name'].casefold()]
        notice=f'음식 영양정보 {len(found)}개를 찾았습니다.' if found else '현재 음식 영양 DB에서 일치 항목을 찾지 못했습니다. 다른 음식 이름으로 질문해 주세요.'
        fields=[('열량','energy_kcal','kcal'),('탄수화물','carbohydrate_g','g'),('단백질','protein_g','g'),('지방','fat_g','g'),('당류','sugars_g','g'),('식이섬유','fiber_g','g'),('나트륨','sodium_mg','mg')]
        nutrition_rows=[]
        for food in found:
            row={'음식·재료':food['name'],'기준량':food['basis_label'],'출처':food['source_url']}
            row.update({f'{label} ({unit})':str(food[key]) if food.get(key) is not None else '미제공' for label,key,unit in fields})
            nutrition_rows.append(row)
        messages.append(dict(role='assistant',result=dict(answer=notice,citations=[],nutrition_rows=nutrition_rows),excluded=sorted(excluded)))
        prompt=''
    if prompt:
        messages.append(dict(role='user',content=prompt))
        with st.container():
            try:
                with st.status('근거 검색 중',expanded=True) as progress:
                    graph=build_graph()
                    state=dict(question=prompt,docs=docs,selected=selected,excluded=excluded,config=settings(),
                               options=answer_options(),retriever='chroma',do_generate=True)
                    result={}
                    for update in graph.stream(state,stream_mode='updates'):
                        for node, values in update.items():
                            result.update(values)
                            progress.update(label='답변 생성·인용 확인 중' if node=='retrieve' else '답변 처리 완료')
                    progress.update(state='complete')
                for warning in result.get('warnings',[]): st.warning('일부 자료를 찾지 못해 확인 가능한 레시피 정보만 사용합니다.')
                generation=result['generation']
            except Exception:
                generation=dict(status='api_error',answer=None,citations=[])
            messages.append(dict(role='assistant',result=generation,excluded=sorted(excluded)))
    turns=[]
    for message in messages:
        if message['role']=='user' or not turns:
            turns.append([])
        turns[-1].append(message)
    for turn_index,turn in enumerate(reversed(turns)):
        if turn_index==0:
            st.markdown(f'<div id="chat-turn-{len(messages)}" tabindex="-1" role="region" aria-label="최근 검색" style="scroll-margin-top:5rem"></div>',unsafe_allow_html=True)
        for message in turn:
            with st.chat_message(message['role']):
                if message['role']=='user': st.write(message['content'])
                elif message.get('excluded',[]) == sorted(excluded):
                    show_generation(message['result'])
                else: st.caption('이전 제외 조건으로 생성한 답변입니다. 현재 조건으로 다시 질문해 주세요.')
    if new_chat_result:
        focus_profile_result(f'chat-turn-{len(messages)}')

if page=='다른 요리와 비교':
    st.subheader('재료와 조리법을 나란히')
    other=st.selectbox('비교할 요리', [i for i in by_id if i!=selected],format_func=lambda i:by_id[i]['name'])
    for col,item_id in zip(st.columns(2),(selected,other)):
        with col:
            st.markdown('### '+by_id[item_id]['name'])
            st.write(by_id[item_id]['ingredients_text'])
            hits=excluded_hits(next(d for d in docs if d['id']==item_id),excluded)
            st.caption('제외 재료 감지: '+(', '.join(hits) if hits else '등록한 제외 재료 감지 없음'))
    st.caption('영양값의 기준량이 미확인이므로 수치 우열·1인분 비교는 하지 않습니다.')
    if st.button('근거로 두 요리 비교',type='primary'):
        with st.spinner('두 레시피 원문을 비교하고 있습니다…'):
            chosen=[d for d in docs if d['id'] in (selected,other)]
            evidence=evidence_context(chosen,chosen)
            if any(excluded_hits(d,excluded) for d in chosen):
                st.warning('비교 대상에 제외 재료가 있습니다. 다른 메뉴를 선택해 주세요.')
            else:
                show_generation(generate('두 요리의 재료와 조리법 차이를 근거로 비교해줘. 영양 수치 우열은 판단하지 마.',evidence,settings()))

if page=='내 정보로 음식 비교':
    import energy_profile
    if not hasattr(energy_profile,'assess_foods'):
        # An already-running Streamlit process may retain the pre-W054 module.
        import importlib
        importlib.invalidate_caches()
        importlib.reload(energy_profile)
    from energy_profile import calculate, candidates, assess_foods, context, ACTIVITY, FORMULA_URL, ACTIVITY_URL, EXPLANATION_INSTRUCTIONS
    st.subheader('내 정보로 계산하고 음식 비교하기')
    st.caption('19~78세 일반 성인의 참고 추정입니다. RMR은 안정시 대사량이며 기초대사량 측정과 동일하지 않습니다. 감량 처방은 제공하지 않습니다.')
    with st.form('energy_profile'):
        left,right=st.columns(2)
        with left:
            st.markdown('### 신체 정보')
            age=st.number_input('나이',min_value=19,max_value=78,value=30,key='ui_age')
            height=st.number_input('키 (cm)',min_value=1.,value=170.,key='ui_height')
            weight=st.number_input('체중 (kg)',min_value=1.,value=70.,key='ui_weight')
            sex=st.selectbox('공식에 사용할 성별 계수',['male','female'],format_func=lambda x:'남성 계수' if x=='male' else '여성 계수',key='ui_sex')
        with right:
            st.markdown('### 활동량과 대사량')
            activity=st.selectbox('활동 범주',list(ACTIVITY),format_func=lambda x:{'sedentary':'일상 활동 위주 (1.0 이상 1.4 미만)','low':'일상 + 중강도 30~60분 (1.4 이상 1.6 미만)','active':'일상 + 중강도 60분 이상 (1.6 이상 1.9 미만)','very_active':'추가 고강도 활동 (1.9 이상 2.5 미만)'}[x],key='ui_activity')
            st.caption('활동계수는 선택 범주의 대표값(1.3 / 1.5 / 1.75 / 2.2)을 사용합니다. 대표값은 앱의 비교 설정입니다.')
            manual=st.checkbox('알고 있는 안정시 대사량을 직접 사용',key='ui_manual')
            resting=st.number_input('안정시 대사량 입력 (kcal/일)',min_value=1.,value=1500.,key='ui_resting')
        st.divider()
        st.markdown('### 적용 대상 확인')
        st.caption('아래 문장이 본인에게 맞으면 확인란을 체크해야 계산할 수 있습니다.')
        eligible=st.checkbox('임신·수유 중이 아니며 질환 치료나 특수 식단 관리가 필요하지 않습니다.',key='ui_eligible',
            help='이 문장이 본인에게 맞으면 체크한 뒤 계산 버튼을 누르세요. 임신·수유 중이거나 질환/특수 식단 관리가 필요하다면 이 계산을 사용하지 마세요.')
        st.markdown('### 음식 비교 조건')
        food_query=st.text_input('비교할 음식 이름 (선택)',placeholder='비워두면 전체 음식에서 찾습니다',key='ui_food_query')
        grams=st.number_input('비교할 음식 중량 (g)',min_value=1.,max_value=2000.,value=150.,key='ui_grams')
        share=st.slider('하루 유지 에너지 중 비교에 사용할 비율 (%)',min_value=5,max_value=50,value=30,key='ui_share')
        st.caption('비율과 중량은 사용자가 정하는 비교 조건이며 한 끼 권장량이 아닙니다. 후보는 완성 식단이 아닙니다.')
        explain=st.checkbox('계산 결과와 음식 근거로 추천 이유 설명받기',key='ui_explain')
        apply_profile=st.form_submit_button('계산하고 음식 찾기',type='primary')
    profile_output=st.empty()
    if apply_profile:
        st.session_state.pop('profile_result',None)
        profile_output.empty()
        with profile_output.container():
            st.markdown('<div id="profile-result-focus" tabindex="-1" role="status" aria-live="polite" style="scroll-margin-top:5rem">계산하고 음식을 찾고 있습니다.</div>',unsafe_allow_html=True)
            focus_profile_result()
            with st.status('입력 정보를 확인하고 있습니다…',expanded=True) as loading:
                try:
                    factor={'sedentary':1.3,'low':1.5,'active':1.75,'very_active':2.2}[activity]
                    calc=calculate(int(age),sex,height,weight,activity,factor,resting if manual else None,eligible)
                    budget=calc['maintenance_kcal']*share/100
                    loading.update(label='계산 완료 · 조건에 맞는 음식을 찾고 있습니다…')
                    rows=candidates(foods,food_query,grams,budget,excluded)
                    assessments=assess_foods(foods,food_query,grams,budget,excluded)
                    result=dict(calc=calc,budget=budget,share=share,excluded=list(excluded),rows=rows,assessments=assessments,generation=None)
                    if rows and explain:
                        loading.update(label='음식 검색 완료 · 근거를 바탕으로 설명을 작성하고 있습니다…')
                        result['generation']=generate('계산된 유지 에너지 참고값과 음식 비교 후보의 조건 및 한계를 설명해줘.',context(calc,rows),settings(),instructions=EXPLANATION_INSTRUCTIONS)
                    st.session_state.profile_result=result
                    loading.update(label='계산과 음식 검색을 완료했습니다.',state='complete')
                except ValueError as exc:
                    st.session_state.profile_result=dict(error=str(exc))
                    loading.update(label='입력 내용을 확인해 주세요.',state='error')
                except Exception:
                    st.session_state.profile_result=dict(error='처리 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.')
                    loading.update(label='요청을 완료하지 못했습니다.',state='error')
        profile_output.empty()
    profile_result=st.session_state.get('profile_result')
    with profile_output.container():
        if profile_result:
            st.markdown('<div id="profile-result-focus" tabindex="-1" style="scroll-margin-top:5rem"></div>',unsafe_allow_html=True)
            st.subheader('계산·음식 검색 결과')
            if profile_result.get('error'):
                st.warning(profile_result['error'])
            else:
                calc=profile_result['calc']; budget=profile_result['budget']; share=profile_result['share']; rows=profile_result['rows']
                factor=calc['activity_factor']
                st.caption('마지막으로 제출한 입력의 결과입니다. 값을 바꾼 뒤에는 다시 계산해 주세요.')
                with st.container(key='profile_summary'):
                    for col,label,value in zip(st.columns(3),('하루 유지 에너지 참고값','음식 비교 예산','안정시 대사량'),
                        (calc['maintenance_kcal'],budget,calc['rmr_kcal'])):
                        col.metric(label,f'{value:,.0f} kcal')
                st.caption(f"BMI {calc['bmi']} · 안정시 대사량은 {'직접 입력값' if calc['rmr_method']=='user_entered' else '공식 추정값'}입니다.")
                st.caption(f'계산: 안정시 대사량 × {factor}. 비교 예산: 유지 에너지 × {share}% = {budget:.1f} kcal')
                st.caption('직접 정한 중량과 에너지 예산으로 비교합니다. 한 끼 권장량이나 건강상 적합성 판정은 아닙니다.')
                with st.expander('계산 근거 보기'):
                    st.link_button('대사량 공식 출처',FORMULA_URL)
                    st.link_button('활동계수 출처',ACTIVITY_URL)
                if sorted(profile_result['excluded'])!=sorted(excluded):
                    st.warning('제외 조건이 변경되었습니다. 후보를 다시 계산해 주세요.')
                    rows=[]
                if profile_result['excluded']:
                    st.warning('음식 영양 DB에 재료 목록이 없어 제외 조건을 검증할 수 없습니다. 조건이 적용 중이면 영양 맞춤 후보는 제공하지 않습니다.')
                if sorted(profile_result['excluded'])==sorted(excluded):
                    assessments=profile_result.get('assessments',[])
                    groups=[(status,label,[a for a in assessments if a['status']==status]) for status,label in
                        (('within','에너지 조건 충족'),('over','현재 중량에서 예산 초과'),('unknown','판단에 필요한 정보 부족'))]
                    groups=[g for g in groups if g[2]]
                    if groups:
                        st.subheader('음식별 비교 결과')
                    for status,label,group in groups:
                        with st.container(key='food_'+status):
                            st.markdown(f'### {label}')
                            group.sort(key=lambda a:abs(a.get('delta_kcal',0)))
                            cards=st.columns(2)
                            for index,item in enumerate(group[:5]):
                                with cards[index%2]:
                                    with st.container(border=True):
                                        st.subheader(item['food']['name'])
                                        if item.get('nutrition'):
                                            st.markdown(f"**{item['nutrition']['energy_kcal']:,.1f} kcal · {item['grams']:g} g**")
                                            difference=abs(item['delta_kcal'])
                                            st.write(f"비교 예산보다 {difference:,.1f} kcal {'초과합니다.' if status=='over' else '여유가 있습니다.'}")
                                        else:
                                            st.write(item['reason'])
                                        st.caption('영양 기준량 '+str(item['food']['basis_label']))
                                        st.link_button('출처 확인',item['food']['source_url'])
                if not rows:
                    if not profile_result['excluded'] and sorted(profile_result['excluded'])==sorted(excluded):
                        st.info('입력한 음식 이름 또는 중량·에너지 조건에 맞는 음식이 없습니다. 음식 이름을 비우거나 중량을 줄여 다시 검색해 주세요.')
                else:
                    with st.expander('조건에 맞는 음식의 영양 성분 자세히'):
                        st.dataframe([dict(음식=r['food']['name'],중량_g=r['grams'],열량_kcal=r['nutrition']['energy_kcal'],단백질_g=r['nutrition']['protein_g'],기준량=r['food']['basis_label'],출처=r['food']['source_url']) for r in rows],hide_index=True,width='stretch')
                    if profile_result.get('generation'):
                        show_generation(profile_result['generation'])
            if apply_profile:
                focus_profile_result()

for input_key in list(st.session_state):
    if input_key.startswith("ui_") or input_key=="recipe_question_text":
        st.session_state.saved_inputs[input_key]=st.session_state[input_key]
