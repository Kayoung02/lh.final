import streamlit as st

from axis_a.territory_map import render_axis_a
from axis_b.renewal_map import render_renewal_map
from guidebook.guidebook import render_guidebook
from public_supply.public_supply_map import render_public_supply_map


st.set_page_config(
    page_title="서울 아파트 사업주체·시공사 분석",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("서울 아파트 사업주체·시공사 분석")
st.caption("아파트 단지의 공급주체 구성, 시공사 점유율과 시공능력평가 변화, 정비사업 분석의 확장 방향을 함께 제시합니다.")

tab_guide, tab_public, tab_territory, tab_renewal = st.tabs(
    ["0. 분석 안내", "1. 아파트 공급주체 구성·지역분포", "2. 시공사 시공능력평가·서울 시공 점유율", "3. 정비사업 분석 확장 방향"]
)

with tab_guide:
    render_guidebook()

with tab_public:
    render_public_supply_map()

with tab_territory:
    render_axis_a()

with tab_renewal:
    render_renewal_map()

