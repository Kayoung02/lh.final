"""2번 탭: 시공능력평가 변화와 서울 공동주택 시공 점유율."""

import copy
import json

import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

from common.config import SEOUL_GU_GEOJSON_PATH, SEOUL_CENTER
from common.contractor_data import (
    get_top20_companies,
    load_ranking_data,
    prepare_apartment_contractors,
    summarize_contractor_share,
)
from common.data_loader import load_apartment_data
from common.map_utils import _district_name, _ensure_wgs84


MAP_COLORS = [
    "#205493", "#C65B28", "#4B8B63", "#8A5AA5", "#B64B67",
    "#8E6B25", "#387C8B", "#6B7280", "#B979B2", "#719B45",
]


@st.cache_data(show_spinner=False)
def _load_gu_boundaries() -> dict:
    if not SEOUL_GU_GEOJSON_PATH.exists():
        raise FileNotFoundError(f"자치구 경계 파일을 찾을 수 없습니다: {SEOUL_GU_GEOJSON_PATH.name}")
    with SEOUL_GU_GEOJSON_PATH.open(encoding="utf-8") as file:
        boundaries = json.load(file)
    _ensure_wgs84(boundaries)
    return boundaries


def _build_leader_map(boundaries: dict, leaders: pd.DataFrame):
    boundary = copy.deepcopy(boundaries)
    leader_lookup = leaders.set_index("시군구").to_dict("index")
    companies = leaders["1위 시공사"].drop_duplicates().tolist()
    colors = {company: MAP_COLORS[index % len(MAP_COLORS)] for index, company in enumerate(companies)}

    for feature in boundary.get("features", []):
        properties = feature.setdefault("properties", {})
        district = _district_name(properties)
        record = leader_lookup.get(district, {})
        leader = record.get("1위 시공사", "Top20 시공사 없음")
        properties["자치구"] = district or "미상"
        properties["1위 시공사"] = leader
        properties["보정 점유율"] = round(float(record.get("1위 보정 점유율(%)", 0)), 1)
        properties["단지수"] = round(float(record.get("1위 단지수", 0)), 1)
        properties["세대수"] = round(float(record.get("1위 세대수", 0)))
        properties["동수"] = round(float(record.get("1위 동수", 0)))
        properties["색상"] = colors.get(leader, "#E5E7EB")

    territory_map = folium.Map(
        location=[SEOUL_CENTER["lat"], SEOUL_CENTER["lon"]],
        zoom_start=10.6,
        tiles=None,
        control_scale=True,
    )
    folium.TileLayer("CartoDB positron", control=False).add_to(territory_map)
    folium.GeoJson(
        boundary,
        style_function=lambda feature: {
            "fillColor": feature["properties"].get("색상", "#E5E7EB"),
            "color": "#4B5563",
            "weight": 1.1,
            "fillOpacity": 0.73,
        },
        highlight_function=lambda _: {"color": "#111827", "weight": 2.2, "fillOpacity": 0.9},
        tooltip=folium.GeoJsonTooltip(
            fields=["자치구", "1위 시공사", "보정 점유율", "단지수", "세대수", "동수"],
            aliases=["자치구", "Top20 내 1위 시공사", "보정 시공 점유율(%)", "단지수", "세대수", "동수"],
            localize=True,
            sticky=False,
        ),
    ).add_to(territory_map)
    territory_map.fit_bounds([[37.41, 126.76], [37.71, 127.19]])

    legend = "".join(
        f"<div><span style='display:inline-block;width:10px;height:10px;background:{color};margin-right:6px;border-radius:2px;'></span>{company}</div>"
        for company, color in colors.items()
    )
    territory_map.get_root().html.add_child(
        folium.Element(
            "<div style='position:fixed;bottom:24px;left:24px;z-index:1000;"
            "background:rgba(255,255,255,.94);border:1px solid #d1d5db;border-radius:6px;"
            "padding:9px 11px;font-size:12px;line-height:1.55;max-height:230px;overflow:auto;'>"
            "<strong>자치구별 Top20 내 1위 시공사</strong>" + legend + "</div>"
        )
    )
    return territory_map


def _ranking_chart(data: pd.DataFrame, metric: str) -> None:
    if metric == "순위":
        figure = px.line(
            data, x="평가연도", y="순위", color="시공사", markers=True,
            labels={"평가연도": "평가연도", "순위": "시공능력평가 순위", "시공사": "시공사"},
        )
        figure.update_yaxes(autorange="reversed", dtick=1)
    else:
        chart_data = data.copy()
        chart_data["시공능력평가액_억원"] = chart_data["시공능력평가액_백만원"] / 100
        figure = px.line(
            chart_data, x="평가연도", y="시공능력평가액_억원", color="시공사", markers=True,
            labels={"평가연도": "평가연도", "시공능력평가액_억원": "시공능력평가액(억원)", "시공사": "시공사"},
        )
    figure.update_layout(margin=dict(l=0, r=0, t=20, b=0), legend_title_text="시공사")
    st.plotly_chart(figure, use_container_width=True, config={"displayModeBar": False})


def _district_detail(all_by_company: pd.DataFrame, district: str, focus_company: str) -> None:
    district_data = all_by_company.loc[all_by_company["시군구"].eq(district)].copy()
    if district_data.empty:
        st.info("선택한 기간에 해당 자치구의 시공사 데이터가 없습니다.")
        return

    focus = district_data.loc[district_data["시공사"].eq(focus_company)]
    focus = focus.iloc[0] if not focus.empty else None
    st.markdown(f"#### {district} · 시공사 점유율")
    if focus is not None:
        metric1, metric2, metric3 = st.columns(3)
        metric1.metric(f"{focus_company} 보정 점유율", f"{focus['보정 시공 점유율(%)']:.1f}%")
        metric2.metric("배분 단지 수", f"{focus['단지수']:.1f}개")
        metric3.metric("배분 세대 수", f"{focus['세대수']:,.0f}세대")
    else:
        st.caption(f"{focus_company}는 선택 기간의 {district} 시공 단지에 없습니다.")

    chart_data = district_data.sort_values("보정 시공 점유율(%)", ascending=False).head(9).copy()
    remainder = district_data.iloc[9:]["보정 시공 점유율(%)"].sum()
    if remainder:
        chart_data = pd.concat(
            [chart_data, pd.DataFrame([{"시공사": "기타 시공사", "보정 시공 점유율(%)": remainder}])],
            ignore_index=True,
        )
    figure = px.pie(
        chart_data, names="시공사", values="보정 시공 점유율(%)", hole=0.55,
        title=f"{district}의 시공사 구성",
    )
    figure.update_traces(textinfo="percent", texttemplate="%{percent:.1%}")
    figure.update_layout(margin=dict(l=0, r=0, t=55, b=0), legend_title_text="시공사")
    st.plotly_chart(figure, use_container_width=True, config={"displayModeBar": False})


def render_axis_a() -> None:
    st.subheader("시공사 시공능력평가·서울 시공 점유율")
    st.caption(
        "선택 업종의 기준연도 Top 20 시공사가 시공능력평가에서 어떻게 변화했는지와, "
        "서울 자치구별 공동주택 시공 점유율을 함께 살펴봅니다."
    )

    try:
        ranking = load_ranking_data()
        apartment = load_apartment_data()
        boundaries = _load_gu_boundaries()
    except (FileNotFoundError, ValueError) as error:
        st.error(str(error))
        return

    industries = sorted(ranking["업종코드"].dropna().unique())
    years = sorted(ranking["평가연도"].unique())
    control1, control2, control3 = st.columns([1, 1, 2])
    with control1:
        industry = st.selectbox("시공능력평가 업종", industries, index=industries.index("토건") if "토건" in industries else 0)
    with control2:
        base_year = st.selectbox("Top 20 선정 기준연도", years, index=len(years) - 1)

    top20 = get_top20_companies(ranking, industry, base_year)
    default_companies = top20[:5]
    with control3:
        selected_companies = st.multiselect(
            "추이와 지도에서 비교할 시공사", top20, default=default_companies
        )
    if not selected_companies:
        st.info("Top 20 시공사 중 하나 이상을 선택하세요.")
        return

    trend = ranking.loc[
        ranking["업종코드"].eq(industry) & ranking["시공사"].isin(selected_companies)
    ].copy()
    trend = trend.sort_values(["평가연도", "순위"])
    chart_column, note_column = st.columns([1.7, 0.8], gap="large")
    with chart_column:
        st.markdown(f"#### {industry} 시공능력평가 변화")
        metric = st.radio("그래프 기준", ["순위", "시공능력평가액"], horizontal=True)
        _ranking_chart(trend, metric)
    with note_column:
        st.markdown("#### 해석 기준")
        st.info(
            "평가액은 건설공사 도급순위의 지표인 시공능력평가액이며, 실제 계약금액이나 아파트 매출과는 다릅니다."
        )
        st.caption(
            f"{base_year}년 {industry} Top 20을 후보군으로 삼았습니다. "
            "회사명은 별칭표를 통해 법인 기준으로 연결합니다."
        )

    expanded = prepare_apartment_contractors(apartment)
    available_years = expanded["사용승인연도"].dropna().astype(int)
    min_year, max_year = int(available_years.min()), int(available_years.max())
    start_year, end_year = st.slider(
        "서울 공동주택 사용승인 기간", min_year, max_year, (min_year, max_year)
    )
    candidate_stats, leaders, all_by_company = summarize_contractor_share(
        expanded, selected_companies, start_year, end_year
    )
    if candidate_stats.empty:
        st.warning("선택한 Top 20 시공사의 서울 공동주택 시공 이력이 없습니다.")
        return

    st.divider()
    st.markdown("#### 자치구별 Top 20 시공사 1위")
    st.caption(
        "자치구 전체 시공 물량을 분모로 계산합니다. 보정 시공 점유율 = 세대수 비중 70% + 동수 비중 30%. "
        "공동시공 단지는 참여사 수만큼 균등 배분합니다."
    )
    map_column, detail_column = st.columns([1.7, 1], gap="large")
    with map_column:
        map_result = st_folium(
            _build_leader_map(boundaries, leaders),
            height=600,
            use_container_width=True,
            returned_objects=["last_active_drawing"],
            key="contractor_share_map",
        )
        drawing = map_result.get("last_active_drawing") if map_result else None
        clicked = (drawing or {}).get("properties", {}).get("자치구")
        if clicked:
            st.session_state["contractor_selected_gu"] = clicked

    districts = sorted(all_by_company["시군구"].unique())
    selected_gu = st.session_state.get("contractor_selected_gu", districts[0])
    if selected_gu not in districts:
        selected_gu = districts[0]
    with detail_column:
        selected_gu = st.selectbox(
            "상세 자치구", districts, index=districts.index(selected_gu), key="contractor_gu_select"
        )
        st.session_state["contractor_selected_gu"] = selected_gu
        companies_in_gu = sorted(all_by_company.loc[all_by_company["시군구"].eq(selected_gu), "시공사"].unique())
        preferred = leaders.loc[leaders["시군구"].eq(selected_gu), "1위 시공사"]
        default_company = preferred.iloc[0] if not preferred.empty else companies_in_gu[0]
        focus_company = st.selectbox(
            "상세 시공사", companies_in_gu, index=companies_in_gu.index(default_company) if default_company in companies_in_gu else 0
        )
        _district_detail(all_by_company, selected_gu, focus_company)


def render() -> None:
    render_axis_a()
