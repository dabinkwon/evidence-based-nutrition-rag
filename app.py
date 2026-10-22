"""Local Streamlit interface. Conversation data stays in session memory."""
import json
from pathlib import Path
import sys
import re

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
import streamlit as st
from recipe_rag import documents, settings, excluded_hits, generate
from rag_graph import build_graph, answer_options, evidence_context

st.set_page_config(page_title='한끼의 근거', page_icon='🥬', layout='wide')
st.markdown('''<style>
.stButton>button {border-radius:12px} .block-container {padding-top:2.5rem;max-width:1250px}
[data-testid="stToolbar"] {display:none}
</style>''', unsafe_allow_html=True)


def show_generation(result):
    if result.get('answer'):
        st.markdown(result['answer'])
    else:
        st.warning({'not_configured':'현재 답변 서비스를 이용할 수 없습니다. 잠시 후 다시 시도해 주세요.', 'api_error':'답변 요청에 실패했습니다. 잠시 후 다시 시도해 주세요.',
                    'invalid_citations':'출처를 확인할 수 없어 답변을 표시하지 않습니다.'}.get(result.get('status'), '답변을 확인할 수 없습니다.'))
    if result.get('citation_notice'):
        st.caption(result['citation_notice'])
    for c in result.get('citations', []):
        with st.expander(f"근거 {c['number']} · {c['title']} · {c['source_label']}"):
            st.link_button('원문 출처 보기', c['source_url'])


docs = documents()
recipes = json.loads((ROOT / 'data/recipes.json').read_text(encoding='utf-8'))
by_id = {'recipe:'+r['recipe_id']:r for r in recipes}
st.session_state.setdefault('conversations', {})
st.session_state.setdefault('candidates', [])
st.session_state.setdefault('nutrition_queries', {})
foods=json.loads((ROOT/'data/foods_extended.json').read_text(encoding='utf-8'))


def clear_current_conversation():
    item=st.session_state.selected_recipe
    st.session_state.conversations[item]=[]
    st.session_state.nutrition_queries.pop(item,None)
    st.session_state.recipe_question_text=''
    st.session_state.cleared_recipe=item

with st.sidebar:
    st.title('🥬 한끼의 근거')
    st.caption('재료에서 시작하는 식생활 탐색')
    selected = st.selectbox('이야기할 요리', list(by_id), format_func=lambda i: by_id[i]['name'], key='selected_recipe')
    excluded_text = st.text_input('제외할 재료', placeholder='새우, 계란, 우유')
    excluded = [x.strip() for x in excluded_text.split(',') if x.strip()]
    st.caption('적용 중인 제외 재료: '+(', '.join(excluded) if excluded else '없음'))
    st.caption('제외 검사는 알려진 동의어 기준이며 알레르기 안전을 보장하지 않습니다.')
    st.divider()
    st.button('이 요리의 대화 지우기',width='stretch',on_click=clear_current_conversation,key='clear_conversation')
    if st.session_state.get('cleared_recipe')==selected:
        st.caption('이 요리의 대화를 지웠습니다.')

st.caption('RECIPE & EVIDENCE')
st.title('오늘의 한 끼, 근거와 함께.')
st.write('원하는 요리를 찾고, 재료와 만드는 방법을 출처와 함께 확인하세요.')
st.info('일반 식생활 정보입니다. 영양값 기준량은 미확인으로 제공량 환산·개인별 섭취량 계산은 지원하지 않습니다. 전문가 조언을 대신하지 않습니다.')
find_tab, chat_tab, compare_tab = st.tabs(['요리 찾기', '요리 대화·영양정보', '다른 요리와 비교'])

with find_tab:
    with st.form('find_recipes'):
        query = st.text_input('어떤 요리를 찾으세요?', placeholder='두부가 들어간 저녁 요리')
        search = st.form_submit_button('요리 찾기', type='primary')
    st.caption('제외 재료는 왼쪽 입력에 지정하세요. 저칼로리·조리시간 등 미확인 조건의 충족은 보장하지 않습니다.')
    if search and query.strip():
        with st.spinner('관련 레시피와 근거를 검색하고 있습니다…'):
            state = build_graph().invoke(dict(question=query,docs=docs,selected=None,excluded=excluded,
                config=settings(),options=answer_options(),retriever='chroma',do_generate=False))
        st.session_state.candidates = [d for d in state['evidence'] if d['collection']=='recipes' and not excluded_hits(d,excluded)]
        for warning in state['warnings']:
            st.warning('검색을 완료하지 못했습니다. 잠시 후 다시 시도해 주세요.')
    visible_candidates = [d for d in st.session_state.candidates if not excluded_hits(d,excluded)]
    if st.session_state.candidates and not visible_candidates:
        st.warning('현재 제외 조건을 적용하면 표시할 후보가 없습니다. 다른 요리를 검색해 주세요.')
    if not st.session_state.candidates:
        st.caption('검색하면 여기에서 후보 요리를 확인할 수 있습니다.')
    for d in st.session_state.candidates:
        if excluded_hits(d,excluded):
            continue
        with st.container(border=True):
            st.subheader(d['title'])
            st.write(d.get('ingredients',''))
            st.link_button('레시피 출처', d['source_url'])
            def choose(item_id):
                st.session_state.selected_recipe = item_id
            st.button('이 요리 선택',key='choose_'+d['id'], on_click=choose,args=(d['id'],))

with chat_tab:
    st.subheader('요리의 영양 원문과 음식별 성분')
    st.write('선택 요리: '+by_id[selected]['name'])
    raw=by_id[selected]['nutrition_raw']
    recipe_fields=[('열량','INFO_ENG','kcal'),('탄수화물','INFO_CAR','g'),('단백질','INFO_PRO','g'),('지방','INFO_FAT','g'),('나트륨','INFO_NA','mg')]
    st.table([{'영양소':label,'API 원문 값':raw.get(key) or '미제공','단위':unit} for label,key,unit in recipe_fields])
    st.caption('레시피 API 원문 값 · 기준량 미확인. 1인분 또는 100g으로 해석하지 않습니다.')
    st.link_button('레시피 영양정보 출처',by_id[selected]['source_url'])
    st.divider()
    r = by_id[selected]
    st.subheader(r['name'])
    selected_hits=excluded_hits(next(d for d in docs if d['id']==selected),excluded)
    if selected_hits:
        st.warning('선택 요리에 제외 재료가 있습니다: '+', '.join(selected_hits)+'. 이 요리는 추천에서 차단됩니다.')
    with st.expander('재료와 조리법 원문'):
        st.write(r['ingredients_text'])
        for step in r['steps']:
            st.write(step['text'])
    if not any(d.get('related_item_id')==selected for d in docs if d['collection']!='recipes'):
        st.caption('현재 제공된 레시피 원문을 바탕으로 답변합니다. 원문에 없는 정보는 확인이 어려울 수 있습니다.')
    messages = st.session_state.conversations.setdefault(selected, [])
    with st.form('recipe_question',clear_on_submit=True):
        question = st.text_input('요리 질문 또는 음식·재료 영양정보 검색',placeholder='만드는 법 알려줘 / 두부 영양성분 / 음식 이름',key='recipe_question_text')
        submitted = st.form_submit_button('검색·질문하기',type='primary')
    prompt = question.strip() if submitted else ''
    nutrient_search=bool(prompt and (any(t in prompt for t in ('영양','성분','단백질','탄수화물','나트륨')) or any(prompt==f['name'] for f in foods)))
    if nutrient_search:
        term=re.split(r'영양|성분|단백질|탄수화물|나트륨',prompt,maxsplit=1)[0].strip()
        term=re.sub(r'(의|에는|은|는|을|를)$','',term).strip()
        st.session_state.nutrition_queries[selected]=term
        messages.append(dict(role='user',content=prompt))
        found=[f for f in foods if term and term.casefold() in f['name'].casefold()]
        notice=f'음식 영양 DB에서 {len(found)}개 항목을 찾았습니다. 아래 기준량·출처 표를 확인하세요.' if found else '현재 음식 영양 DB에서 일치 항목을 찾지 못했습니다. 선택 요리의 영양 원문은 아래에서 확인할 수 있습니다.'
        messages.append(dict(role='assistant',result=dict(answer=notice,citations=[]),excluded=sorted(excluded)))
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
    for turn in reversed(turns):
        for message in turn:
            with st.chat_message(message['role']):
                if message['role']=='user': st.write(message['content'])
                elif message.get('excluded',[]) == sorted(excluded): show_generation(message['result'])
                else: st.caption('이전 제외 조건으로 생성한 답변입니다. 현재 조건으로 다시 질문해 주세요.')

with chat_tab:
    nutrition_query=st.session_state.nutrition_queries.get(selected,'')
    if selected in st.session_state.nutrition_queries:
        st.divider()
        st.subheader('음식·재료 영양정보 검색 결과')
        st.caption('음식별 기준량과 조리 상태를 확인하세요. 선택 요리의 영양값과 별도입니다.')
    matches=[f for f in foods if nutrition_query.strip() and nutrition_query.strip().casefold() in f['name'].casefold()]
    if selected in st.session_state.nutrition_queries and not matches:
        st.info('현재 확보한 데이터에는 일치하는 항목이 없습니다. 다른 음식의 값을 대신 연결하지 않습니다.')
    if matches:
        st.caption(f'일치 항목 {len(matches)}개')
        fields=[('열량','energy_kcal','kcal'),('탄수화물','carbohydrate_g','g'),('단백질','protein_g','g'),('지방','fat_g','g'),('당류','sugars_g','g'),('식이섬유','fiber_g','g'),('나트륨','sodium_mg','mg')]
        rows=[]
        for food in matches:
            row={'음식·재료':food['name'],'기준량':food['basis_label']}
            row.update({f'{label} ({unit})':str(food[key]) if food.get(key) is not None else '미제공' for label,key,unit in fields})
            row['출처']=food['source_url']
            rows.append(row)
        st.dataframe(rows,hide_index=True,width='stretch',
            column_config={'출처':st.column_config.LinkColumn('출처',display_text='원문 보기')})

with compare_tab:
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
