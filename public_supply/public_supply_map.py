import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from common.data_loader import load_apartment_data
from common.map_utils import build_public_share_map
from common.public_supply import summarize_by_agency, summarize_by_developer_type, summarize_public_share_by_district


def _filter_analysis_data(apartment: pd.DataFrame) -> tuple[pd.DataFrame, str, str]:
    """선택 조건을 적용하되, 시행주체별 구성의 분모는 전체 단지로 유지한다."""
    districts = sorted(apartment.loc[apartment["시군구"].ne("미상"), "시군구"].unique())
    agencies = sorted(apartment["시행사_표시"].dropna().unique())
    years = sorted(apartment["사용승인연도"].dropna().astype(int).unique())

    st.markdown("#### 분석 조건")
    location_column, agency_column, mode_column, basis_column = st.columns([1, 1.25, 1, 0.85])
    with location_column:
        selected_district = st.selectbox("자치구", ["전체"] + districts)
    with agency_column:
        selected_agency = st.selectbox("시행사", ["전체"] + agencies)
    with mode_column:
        public_mode = st.selectbox("공공 기준", ["공공 직접 시행", "공공 참여"])
    with basis_column:
        ratio_base = st.selectbox("비율 기준", ["세대수", "단지수"])

    with st.expander("사용승인 연도 설정", expanded=False):
        selected_years = st.slider(
            "분석 기간", min_value=min(years), max_value=max(years), value=(min(years), max(years))
        )

    filtered = apartment.copy()
    if selected_district != "전체":
        filtered = filtered[filtered["시군구"].eq(selected_district)]
    if selected_agency != "전체":
        filtered = filtered[filtered["시행사_표시"].eq(selected_agency)]
    filtered = filtered[filtered["사용승인연도"].between(*selected_years, inclusive="both")]
    return filtered, public_mode, ratio_base


def _share(numerator: pd.DataFrame, denominator: pd.DataFrame, ratio_base: str) -> float:
    if ratio_base == "세대수":
        total = denominator["세대수"].sum()
        return float(numerator["세대수"].sum() / total * 100) if total else 0.0
    return float(len(numerator) / len(denominator) * 100) if len(denominator) else 0.0


def _render_developer_type_donut(summary: pd.DataFrame, ratio_base: str) -> None:
    st.markdown("#### 서울 전체 시행주체 구성")
    st.caption(f"선택한 조건의 전체 아파트를 {ratio_base} 기준으로 구분합니다.")
    st.vega_lite_chart(
        summary,
        {
            "mark": {"type": "arc", "innerRadius": 56},
            "encoding": {
                "theta": {"field": ratio_base, "type": "quantitative", "stack": True},
                "color": {"field": "시행주체 구분", "type": "nominal", "legend": {"title": None}},
                "tooltip": [
                    {"field": "시행주체 구분", "type": "nominal", "title": "시행주체"},
                    {"field": "단지수", "type": "quantitative", "format": ","},
                    {"field": "세대수", "type": "quantitative", "format": ","},
                    {"field": "단지수_비중(%)", "type": "quantitative", "format": ".1f"},
                    {"field": "세대수_비중(%)", "type": "quantitative", "format": ".1f"},
                ],
            },
            "view": {"stroke": None},
        },
        use_container_width=True,
    )


def render_public_supply_map() -> None:
    st.subheader("시행주체별 아파트 분포")
    st.caption("핵심 질문: 서울 아파트 중 공공이 시행한 비율은 얼마이며, 자치구별로 어떻게 다른가?")

    try:
        apartment = load_apartment_data()
    except (FileNotFoundError, ValueError) as error:
        st.error(str(error))
        return

    analysis_data, public_mode, ratio_base = _filter_analysis_data(apartment)
    if analysis_data.empty:
        st.warning("선택한 조건에 해당하는 아파트 단지가 없습니다.")
        return

    direct_public = analysis_data[analysis_data["시행주체 구분"].isin(["공공", "기타공공"])]
    public_participation = analysis_data[
        analysis_data["시행주체 구분"].astype(str).str.contains("공공", na=False)
    ]
    district_summary = summarize_public_share_by_district(analysis_data, public_mode)
    ratio_column = f"공공_{ratio_base}_비율(%)"

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("분석 대상 단지", f"{len(analysis_data):,}개")
    kpi2.metric("분석 대상 세대수", f"{int(analysis_data['세대수'].sum()):,}세대")
    kpi3.metric(f"공공 직접 시행 비율 ({ratio_base})", f"{_share(direct_public, analysis_data, ratio_base):.1f}%")
    kpi4.metric(f"공공 참여 비율 ({ratio_base})", f"{_share(public_participation, analysis_data, ratio_base):.1f}%")

    map_column, composition_column = st.columns([1.75, 1], gap="large")
    with map_column:
        st.markdown(f"#### 자치구별 {public_mode} 비율")
        st.caption("색이 진할수록 해당 자치구의 전체 아파트 중 공공이 차지하는 비중이 높습니다. 확대하면 행정동 경계와 자치구별 상세 수치를 볼 수 있습니다.")
        st_folium(
            build_public_share_map(district_summary, ratio_column, public_mode),
            height=640,
            use_container_width=True,
            returned_objects=[],
        )

    with composition_column:
        _render_developer_type_donut(summarize_by_developer_type(analysis_data), ratio_base)
        st.info(
            "공공 직접 시행은 `공공`·`기타공공`의 합계입니다. "
            "공공 참여는 여기에 공공 공동 시행을 포함합니다."
        )

    detail_column, agency_column = st.columns([1.35, 1], gap="large")
    with detail_column:
        st.markdown(f"#### 자치구별 {public_mode} 현황")
        st.caption("막대는 자치구 전체 아파트 대비 공공 세대수 비율입니다.")
        st.bar_chart(district_summary.set_index("시군구")["공공_세대수_비율(%)"], horizontal=True)
        display_columns = [
            "시군구",
            "전체_단지수",
            "공공_단지수",
            "공공_단지수_비율(%)",
            "전체_세대수",
            "공공_세대수",
            "공공_세대수_비율(%)",
        ]
        st.dataframe(
            district_summary[display_columns],
            hide_index=True,
            use_container_width=True,
            height=340,
            column_config={
                "공공_단지수_비율(%)": st.column_config.NumberColumn(format="%.1f%%"),
                "공공_세대수_비율(%)": st.column_config.NumberColumn(format="%.1f%%"),
            },
        )

    with agency_column:
        st.markdown("#### 공공 시행기관별 단지·세대 규모")
        st.caption("공공 직접 시행 단지만 대상으로, 어느 기관이 얼마나 시행했는지 보여줍니다.")
        public_agencies = summarize_by_agency(direct_public).head(15)
        st.dataframe(public_agencies, hide_index=True, use_container_width=True, height=260)
        st.bar_chart(public_agencies.set_index("시행사")["총세대수"], horizontal=True)
