import streamlit as st


def render_guidebook() -> None:
    st.subheader("이 프로젝트로 보는 것")
    st.write(
        "서울의 공공 주택 공급, 시공사의 공급 영토와 시공능력평가 변화, "
        "그리고 정비사업의 잠재 물량을 같은 공간 맥락에서 탐색합니다."
    )

    left, right = st.columns(2)
    with left:
        st.markdown("**현재 사용 데이터**")
        st.markdown("- 서울시 공동주택 2차 전처리 데이터\n- 연도별 시공능력평가 데이터\n- 의제처리구역 및 정비사업 추진현황 데이터")
    with right:
        st.markdown("**해석 원칙**")
        st.markdown("- 공급 실적은 인과관계가 아닌 공간적 분포입니다.\n- 미확인 회사명과 시공사 선정 정보는 추정하지 않습니다.\n- 점유율은 법인·기업그룹 기준을 구분합니다.")

    st.info("단기 목표: 0 가이드북, 1 공공 시행 공급지도, 2 시공사 영토·도급순위까지 구현합니다.")

