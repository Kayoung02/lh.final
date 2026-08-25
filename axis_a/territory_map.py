import streamlit as st
from streamlit_folium import st_folium

from .data import (
    load_apartment_data,
    load_seoul_boundary,
    prepare_apartment_data,
)

from .analysis import (
    calculate_district_share,
    calculate_district_breakdown,
)

from .visuals import (
    create_territory_map,
    create_donut_chart,
)


def render_axis_a():
    st.title("서울시 시공사별 점유율")

    # 1. 데이터 불러오기
    apartment_df, company_df, quality = (
        prepare_apartment_data(
            load_apartment_data()
        )
    )

    boundary = load_seoul_boundary()

    # 2. 사이드바 필터
    share_type = st.sidebar.radio(
        "점유율 기준",
        [
            "세대수 점유율",
            "단지수 점유율",
        ],
    )

    selected_company = st.sidebar.selectbox(
        "시공사",
        [
            "구별 1위 시공사",
            "삼성물산",
            "현대건설",
            "GS건설",
        ],
    )

    # 3. 자치구별 통계
    district_share = calculate_district_share(
        apartment_df,
        company_df,
        selected_company,
        share_type,
    )

    # 4. 지도와 차트
    map_column, chart_column = st.columns(
        [1.7, 1]
    )

    with map_column:
        territory_map = create_territory_map(
            boundary,
            district_share,
            share_type,
            st.session_state.get(
                "selected_district",
                "강남구",
            ),
        )

        map_result = st_folium(
            territory_map,
            height=720,
            use_container_width=True,
        )

    with chart_column:
        selected_district = (
            st.session_state.get(
                "selected_district",
                "강남구",
            )
        )

        breakdown = (
            calculate_district_breakdown(
                apartment_df,
                company_df,
                selected_district,
            )
        )

        donut_chart = create_donut_chart(
            breakdown,
            selected_district,
            share_type,
        )

        st.plotly_chart(
            donut_chart,
            use_container_width=True,
        )
