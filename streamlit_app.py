import streamlit as st

from axis_a import render_axis_a
from axis_b import render_axis_b


# ---------------------------------------------------------
# Streamlit 기본 설정
# 반드시 다른 st 명령보다 먼저 실행되어야 합니다.
# ---------------------------------------------------------

st.set_page_config(
    page_title="서울 시공사 영토지도",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------
# 전체 화면 디자인
# ---------------------------------------------------------

st.markdown(
    """
    <style>
        .stApp {
            background-color: #f5f7fa;
        }

        [data-testid="stSidebar"] {
            background-color: #ffffff;
            border-right: 1px solid #e2e8f0;
        }

        .main-title {
            margin-bottom: 0;
            color: #172033;
            font-size: 2.1rem;
            font-weight: 700;
        }

        .main-description {
            margin-top: 6px;
            margin-bottom: 20px;
            color: #64748b;
            font-size: 0.95rem;
        }

        .sidebar-brand {
            padding: 6px 0 18px 0;
        }

        .sidebar-brand-title {
            color: #172033;
            font-size: 1.25rem;
            font-weight: 700;
        }

        .sidebar-brand-caption {
            margin-top: 4px;
            color: #64748b;
            font-size: 0.8rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------
# 사이드바
# ---------------------------------------------------------

with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-brand">
            <div class="sidebar-brand-title">
                🏗️ 시공사 영토지도
            </div>

            <div class="sidebar-brand-caption">
                서울 공동주택과 정비사업 분석
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    selected_axis = st.radio(
        "분석 화면",
        options=[
            "축 A · 기존 아파트 영토",
            "축 B · 정비사업 수주 전선",
        ],
        index=0,
    )

    st.divider()

    st.caption(
        "축 A는 준공된 아파트를 분석하고, "
        "축 B는 진행 중인 정비사업과 수주 정보를 추적합니다."
    )


# ---------------------------------------------------------
# 선택된 분석 화면 실행
# ---------------------------------------------------------

if selected_axis == "축 A · 기존 아파트 영토":
    render_axis_a()

elif selected_axis == "축 B · 정비사업 수주 전선":
    render_axis_b()
