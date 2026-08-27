import streamlit as st


def render_guidebook() -> None:
    st.subheader("분석 범위와 활용 방법")
    st.write(
        "서울 아파트 단지의 시행주체 구성, 시공사 분포와 시공능력평가 변화, "
        "그리고 정비사업 추진 현황을 같은 공간 맥락에서 탐색합니다."
    )

    left, right = st.columns(2)
    with left:
        st.markdown("**현재 사용 데이터**")
        st.markdown("- 서울시 공동주택 2차 전처리 데이터\n- 연도별 시공능력평가 데이터\n- 의제처리구역 및 정비사업 추진현황 데이터")
    with right:
        st.markdown("**해석 원칙**")
        st.markdown("- 단지 분포는 인과관계가 아닌 현황 비교입니다.\n- 미확인 회사명과 시공사 선정 정보는 추정하지 않습니다.\n- 시공사 지표는 법인·기업그룹 기준을 구분합니다.")

    st.info("단기 목표: 0 분석 안내, 1 시행주체 현황 지도, 2 시공사 분포·시공능력평가까지 구현합니다.")
