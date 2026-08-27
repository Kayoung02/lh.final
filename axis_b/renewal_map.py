import streamlit as st


def render_renewal_placeholder() -> None:
    st.subheader("정비사업 레이더")
    st.info(
        "정비사업 추진현황과 의제처리구역을 연결하는 단계입니다. "
        "시공사 선정 정보는 `renewal_builder_evidence.csv`가 준비된 뒤 근거 링크와 함께 표시합니다."
    )
