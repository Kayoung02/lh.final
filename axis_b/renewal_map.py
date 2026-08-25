import streamlit as st


def render_axis_b():
    """
    축 B: 실시간 정비사업 및 수주 정보
    """

    st.markdown(
        '<h1 class="main-title">정비사업 수주 전선</h1>',
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="main-description">
            진행 중인 재개발·재건축 사업과
            시공사 수주 신호를 추적하는 화면입니다.
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.info(
        "축 B는 추후 DART 공시, 정비사업 구역경계, "
        "시공사 선정 및 뉴스 데이터를 연결할 예정입니다."
    )

    st.markdown(
        """
        #### 예정 기능

        - 정비사업 구역경계 표시
        - 사업 단계별 필터
        - 선정·계약된 시공사 표시
        - DART 수주 공시 연결
        - 뉴스 및 출처 확인
        - 공시·총회·뉴스별 확정도 등급
        """
    )
