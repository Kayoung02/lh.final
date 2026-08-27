import streamlit as st

from axis_a.territory_placeholder import render_territory_placeholder
from axis_b.renewal_map import render_renewal_placeholder
from guidebook.guidebook import render_guidebook
from public_supply.public_supply_map import render_public_supply_map


st.set_page_config(
    page_title="서울 주택공급 현황",
    page_icon="🏙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("서울 공동주택 사업주체·시공사 입지 분석")
st.caption("아파트 단지의 시행주체, 시공사 분포, 정비사업 추진 현황을 공간적으로 분석합니다.")

tab_guide, tab_public, tab_territory, tab_renewal = st.tabs(
    ["0. 분석 안내", "1. 시행주체 현황", "2. 시공사 분포·시공능력평가", "3. 정비사업 현황"]
)

with tab_guide:
    render_guidebook()

with tab_public:
    render_public_supply_map()

with tab_territory:
    render_territory_placeholder()

with tab_renewal:
    render_renewal_placeholder()
