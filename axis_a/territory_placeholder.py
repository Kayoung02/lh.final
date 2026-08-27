import streamlit as st


def render_territory_placeholder() -> None:
    st.subheader("시공사 영토·도급순위")
    st.info(
        "다음 구현 대상입니다. `company_alias_map.csv`를 사용해 회사명을 정규화하고, "
        "2007~2026 시공능력평가 변화와 시군구별 보정 점유율을 함께 보여줍니다."
    )
