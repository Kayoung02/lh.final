import streamlit as st

from axis_a.territory_placeholder import render_territory_placeholder
from axis_b.renewal_map import render_renewal_placeholder
from guidebook.guidebook import render_guidebook
from public_supply.public_supply_map import render_public_supply_map


st.set_page_config(
    page_title="서울 아파트 공급 현황",
    page_icon="🏙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("서울 주택공급·브랜드 영토 레이더")
st.caption("공공 시행 공급 · 시공사 점유율 · 정비사업 흐름을 하나의 지도 위에서 읽는 대시보드")

tab_guide, tab_public, tab_territory, tab_renewal = st.tabs(
    ["0. 가이드북", "1. 공공 시행 공급지도", "2. 시공사 영토·도급순위", "3. 정비사업 레이더"]
)

with tab_guide:
    render_guidebook()

with tab_public:
    render_public_supply_map()

with tab_territory:
    render_territory_placeholder()

with tab_renewal:
    render_renewal_placeholder()
