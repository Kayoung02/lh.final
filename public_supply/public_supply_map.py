import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from common.data_loader import load_apartment_data
from common.map_utils import build_public_supply_map
from common.public_supply import summarize_by_agency, summarize_by_developer_type, summarize_by_district


def _filter_apartment_data(apartment: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("1. 시행주체 현황 지도 필터")
    districts = sorted(apartment.loc[apartment["시군구"].ne("미상"), "시군구"].unique())
    agencies = sorted(apartment["시행사_표시"].dropna().unique())
    years = sorted(apartment["사용승인연도"].dropna().astype(int).unique())

    selected_districts = st.sidebar.multiselect("시군구", districts, placeholder="전체 시군구")
    selected_agencies = st.sidebar.multiselect("시행사", agencies, placeholder="전체 시행사")
    selected_types = st.sidebar.multiselect(
        "시행주체 구분",
        sorted(apartment["시행주체 구분"].dropna().unique()),
        default=sorted(apartment["시행주체 구분"].dropna().unique()),
    )
    selected_years = st.sidebar.slider(
        "사용승인 연도", min_value=min(years), max_value=max(years), value=(min(years), max(years))
    )

    filtered = apartment.copy()
    if selected_districts:
        filtered = filtered[filtered["시군구"].isin(selected_districts)]
    if selected_agencies:
        filtered = filtered[filtered["시행사_표시"].isin(selected_agencies)]
    if selected_types:
        filtered = filtered[filtered["시행주체 구분"].isin(selected_types)]
    return filtered[filtered["사용승인연도"].between(*selected_years, inclusive="both")]


def _share(numerator: pd.DataFrame, denominator: pd.DataFrame, base: str) -> float:
    if base == "세대수":
        denominator_value = denominator["세대수"].sum()
        return float(numerator["세대수"].sum() / denominator_value * 100) if denominator_value else 0.0
    return float(len(numerator) / len(denominator) * 100) if len(denominator) else 0.0


def render_public_supply_map() -> None:
    st.subheader("시행주체 현황 지도")
    st.caption("전체 아파트 단지를 기준으로 시행주체별 비중과 개별 단지의 시행사를 함께 확인합니다.")

    try:
        apartment = load_apartment_data()
    except (FileNotFoundError, ValueError) as error:
        st.error(str(error))
        return

    filtered = _filter_apartment_data(apartment)

    total_households = int(filtered["세대수"].sum())
    total_buildings = int(filtered["동수"].sum())
    valid_points = int(filtered["좌표유효"].sum())
    ratio_base = st.radio("비율 기준", ["세대수", "단지수"], horizontal=True, key="developer_ratio_base")
    public_direct = filtered[filtered["시행주체 구분"].isin(["공공", "기타공공"])]
    public_participating = filtered[filtered["시행주체 구분"].astype(str).str.contains("공공", na=False)]

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("전체 단지", f"{len(filtered):,}개")
    kpi2.metric("전체 세대수", f"{total_households:,}세대")
    kpi3.metric(f"공공 직접 시행 비율 ({ratio_base})", f"{_share(public_direct, filtered, ratio_base):.1f}%")
    kpi4.metric(f"공공 참여 비율 ({ratio_base})", f"{_share(public_participating, filtered, ratio_base):.1f}%")

    st.markdown("#### 시행주체 유형별 공급 비율")
    developer_type_summary = summarize_by_developer_type(filtered)
    ratio_field = ratio_base
    ratio_column, ratio_table_column = st.columns([1, 1.25])
    with ratio_column:
        st.vega_lite_chart(
            developer_type_summary,
            {
                "mark": {"type": "arc", "innerRadius": 58},
                "encoding": {
                    "theta": {"field": ratio_field, "type": "quantitative", "stack": True},
                    "color": {"field": "시행주체 구분", "type": "nominal", "legend": {"title": None}},
                    "tooltip": [
                        {"field": "시행주체 구분", "type": "nominal", "title": "시행주체"},
                        {"field": "단지수", "type": "quantitative", "format": ","},
                        {"field": "단지수_비중(%)", "type": "quantitative", "format": ".1f"},
                        {"field": "세대수", "type": "quantitative", "format": ","},
                        {"field": "세대수_비중(%)", "type": "quantitative", "format": ".1f"},
                    ],
                },
                "view": {"stroke": None},
            },
            use_container_width=True,
        )
    with ratio_table_column:
        st.dataframe(
            developer_type_summary,
            hide_index=True,
            use_container_width=True,
            column_config={
                "단지수_비중(%)": st.column_config.NumberColumn(format="%.1f%%"),
                "세대수_비중(%)": st.column_config.NumberColumn(format="%.1f%%"),
            },
        )

    map_column, ranking_column = st.columns([1.7, 1])
    with map_column:
        st_folium(build_public_supply_map(filtered), height=620, use_container_width=True, returned_objects=[])
    with ranking_column:
        st.markdown("#### 시군구별 아파트 현황")
        district_summary = summarize_by_district(filtered)
        st.bar_chart(district_summary.set_index("시군구")["총세대수"], horizontal=True)
        st.dataframe(
            district_summary,
            hide_index=True,
            use_container_width=True,
            column_config={"세대수_비중(%)": st.column_config.NumberColumn(format="%.1f%%")},
        )

    st.markdown("#### 시행사별 아파트 현황")
    agency_summary = summarize_by_agency(filtered)
    st.dataframe(agency_summary, hide_index=True, use_container_width=True)

    with st.expander("지도 해석 및 다음 단계"):
        st.markdown(
            "- `공공 직접 시행`은 `공공`과 `기타공공`의 합계이며, `공공 참여`는 공공 공동 시행을 추가로 포함합니다.\n"
            "- `세대수`와 `단지수` 기준의 비율을 바꿔 보면 대규모 단지 중심과 단지 수 중심의 차이를 확인할 수 있습니다.\n"
            "- `seoul_adm_dong_simplified.geojson` 파일을 추가하면 지도 레이어에서 행정동 경계를 켜고 끌 수 있습니다.\n"
            "- 아파트 실거래가 데이터가 준비되면 같은 필터를 사용해 지역별 공급량과 가격 지표의 상관관계 탐색을 추가합니다."
        )
