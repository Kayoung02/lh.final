"""3번 탭: 서울시 정비사업 추진현황과 검증된 시공사 선정 근거."""

import copy
from datetime import date, timedelta

import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

from common.config import SEOUL_CENTER
from common.contractor_data import get_top20_companies, load_ranking_data
from common.dart_collector import (
    collect_dart_candidates,
    company_corp_codes,
    enrich_dart_candidates,
    get_dart_api_key,
)
from common.renewal_data import (
    load_renewal_areas,
    load_renewal_evidence,
    load_renewal_projects,
    project_name_key,
    selected_evidence,
)


def _filtered_projects(projects: pd.DataFrame, gu: str, project_type: str, stage: str) -> pd.DataFrame:
    data = projects.copy()
    if gu != "전체 자치구":
        data = data.loc[data["자치구"].eq(gu)]
    if project_type != "전체 사업유형":
        data = data.loc[data["사업유형"].eq(project_type)]
    if stage != "전체 추진단계":
        data = data.loc[data["추진단계"].eq(stage)]
    return data


def _match_dart_projects(candidates: pd.DataFrame, projects: pd.DataFrame) -> pd.DataFrame:
    """계약명·공급지역이 원장 사업명 또는 지번주소와 정확히 겹칠 때만 추천한다."""
    result = candidates.copy()
    project_rows = projects[["정비사업_매칭키", "구역명", "위치_지번주소"]].fillna("").to_dict("records")

    matched_keys, match_rules = [], []
    for _, candidate in result.iterrows():
        source_text = project_name_key(
            " ".join(str(candidate.get(column, "")) for column in ("계약명", "공급지역", "공사개요"))
        )
        match_key, match_rule = "", "자동 연결 없음"
        for project in project_rows:
            address_key = project_name_key(project["위치_지번주소"])
            if len(address_key) >= 6 and address_key in source_text:
                match_key, match_rule = project["정비사업_매칭키"], "주소 일치"
                break
        if not match_key:
            for project in project_rows:
                name_key = project_name_key(project["구역명"])
                if len(name_key) >= 5 and name_key in source_text:
                    match_key, match_rule = project["정비사업_매칭키"], "사업명 일치"
                    break
        matched_keys.append(match_key)
        match_rules.append(match_rule)

    result["추천 정비사업"] = matched_keys
    result["자동매칭 근거"] = match_rules
    result["판정"] = result["자동매칭 근거"].map(
        lambda value: "원문 확인 후 근거 등록" if value != "자동 연결 없음" else "사업 연결 확인 필요"
    )
    return result


def _renewal_map(areas: dict, evidence: pd.DataFrame) -> folium.Map:
    evidence_lookup = selected_evidence(evidence).set_index("정비사업_매칭키").to_dict("index")
    map_data = copy.deepcopy(areas)
    for feature in map_data.get("features", []):
        props = feature.setdefault("properties", {})
        area_name = str(props.get("DGM_NM", "")).strip()
        match_key = project_name_key(area_name)
        matching = next((row for key, row in evidence_lookup.items() if project_name_key(key.split("|", 1)[-1]) == match_key), None)
        props["구역명"] = area_name or "명칭 없음"
        props["시공사"] = matching.get("시공사_표준화", "미등록") if matching else "미등록"
        props["브랜드"] = matching.get("브랜드명", "") if matching else ""
        props["선정상태"] = matching.get("선정상태", "근거 미등록") if matching else "근거 미등록"
        props["근거등급"] = matching.get("근거등급", "") if matching else ""
        props["색상"] = "#0f766e" if matching else "#94a3b8"

    renewal_map = folium.Map(
        location=[SEOUL_CENTER["lat"], SEOUL_CENTER["lon"]], zoom_start=10.6,
        tiles="CartoDB positron", control_scale=True,
    )
    folium.GeoJson(
        map_data,
        style_function=lambda feature: {
            "fillColor": feature["properties"].get("색상", "#94a3b8"),
            "color": "#475569", "weight": 0.75, "fillOpacity": 0.42,
        },
        highlight_function=lambda _: {"color": "#0f172a", "weight": 2, "fillOpacity": 0.7},
        tooltip=folium.GeoJsonTooltip(
            fields=["구역명", "시공사", "브랜드", "선정상태", "근거등급"],
            aliases=["의제처리구역", "검증 시공사", "브랜드", "선정상태", "근거등급"],
            sticky=False,
        ),
        smooth_factor=1,
    ).add_to(renewal_map)
    renewal_map.fit_bounds([[37.41, 126.76], [37.71, 127.19]])
    renewal_map.get_root().html.add_child(folium.Element(
        "<div style='position:fixed;bottom:24px;left:24px;z-index:1000;background:#fff;"
        "border:1px solid #cbd5e1;border-radius:7px;padding:9px 11px;font-size:12px;'>"
        "<b>의제처리구역</b><br><span style='color:#0f766e'>■</span> 검증된 시공사 선정 근거 있음"
        "<br><span style='color:#94a3b8'>■</span> 시공사 선정 근거 미등록</div>"
    ))
    return renewal_map


def render_renewal_map() -> None:
    st.subheader("정비사업 추진 현황·시공사 선정 근거")
    st.caption("추진현황은 2026년 6월 서울시 원장 기준입니다. 시공사·브랜드는 검증완료된 근거가 있는 경우에만 표시합니다.")
    try:
        projects = load_renewal_projects()
        evidence = load_renewal_evidence()
        areas = load_renewal_areas()
    except (FileNotFoundError, ValueError) as error:
        st.error(str(error))
        return

    gu_options = ["전체 자치구"] + sorted(projects["자치구"].dropna().unique().tolist())
    type_options = ["전체 사업유형"] + sorted(projects["사업유형"].dropna().unique().tolist())
    stage_options = ["전체 추진단계"] + sorted(projects["추진단계"].dropna().unique().tolist())
    control1, control2, control3 = st.columns(3)
    gu = control1.selectbox("자치구", gu_options)
    project_type = control2.selectbox("사업유형", type_options)
    stage = control3.selectbox("추진단계", stage_options)
    filtered = _filtered_projects(projects, gu, project_type, stage)
    confirmed = selected_evidence(evidence)

    metric1, metric2, metric3, metric4 = st.columns(4)
    metric1.metric("대상 정비사업 구역", f"{len(filtered):,}곳")
    metric2.metric("계획 공급세대수", f"{filtered['공급세대수_합계'].sum():,.0f}세대")
    metric3.metric("사업유형 수", f"{filtered['사업유형'].nunique():,}개")
    metric4.metric("검증된 시공사 선정 근거", f"{len(confirmed):,}건")

    chart_col, table_col = st.columns([1, 1], gap="large")
    with chart_col:
        stage_data = filtered.groupby("추진단계", as_index=False).size().rename(columns={"size": "구역 수"})
        stage_data = stage_data.sort_values("구역 수", ascending=True)
        figure = px.bar(stage_data, x="구역 수", y="추진단계", orientation="h", text="구역 수")
        figure.update_traces(marker_color="#2563eb", textposition="outside")
        figure.update_layout(title="추진단계별 정비사업 구역 수", height=360, margin=dict(l=0, r=15, t=45, b=0), showlegend=False)
        st.plotly_chart(figure, use_container_width=True, config={"displayModeBar": False})
    with table_col:
        st.markdown("#### 선택 조건의 사업 목록")
        st.dataframe(
            filtered[["자치구", "구역명", "공공민간", "사업유형", "추진단계", "공급세대수_합계"]]
            .sort_values(["자치구", "구역명"]),
            hide_index=True, use_container_width=True, height=360,
        )

    st.divider()
    st.markdown("#### 의제처리구역·시공사 선정 근거 지도")
    st.caption("회색은 의제처리구역 공간정보만 있는 구역, 녹색은 검증완료된 시공사 선정 근거가 연결된 구역입니다.")
    st_folium(_renewal_map(areas, evidence), height=620, use_container_width=True, key="renewal_area_map")

    st.markdown("#### 시공사 선정 근거")
    if evidence.empty:
        st.info("아직 등록된 근거가 없습니다. DART·조합 공식자료·건설사 보도자료를 확인한 뒤 `renewal_builder_evidence.csv`에 추가하면 지도와 이 표에 반영됩니다.")
    else:
        visible_evidence = evidence.loc[evidence["자치구"].eq(gu)] if gu != "전체 자치구" else evidence
        st.dataframe(
            visible_evidence[["사업명_원문", "자치구", "시공사_표준화", "브랜드명", "선정상태", "근거유형", "근거등급", "검증상태", "확인일"]],
            hide_index=True, use_container_width=True,
        )
        for _, item in visible_evidence.loc[visible_evidence["원문URL"].ne("")].iterrows():
            st.link_button(f"근거 열기 · {item['사업명_원문']} ({item['시공사_표준화']})", item["원문URL"])

    st.divider()
    st.markdown("#### OpenDART 공시 검토 후보")
    st.caption("최근 공시 중 공급계약·공사수주·재개발·재건축 관련 제목을 후보로 찾습니다. 이 결과는 시공사 선정 확정 정보가 아니며, 원문 확인 후에만 근거 CSV에 등록하세요.")

    api_key = get_dart_api_key()
    if not api_key:
        st.warning("DART_API_KEY가 Secrets에 설정되지 않았습니다. App settings → Secrets를 확인하세요.")
        return

    try:
        ranking = load_ranking_data()
        ranking_year = int(ranking["평가연도"].max())
        dart_companies = get_top20_companies(ranking, "토건", ranking_year)
    except (FileNotFoundError, ValueError) as error:
        st.error(f"Top 20 시공사 목록을 불러오지 못했습니다: {error}")
        return

    dart_control1, dart_control2, dart_control3 = st.columns([2, 1, 1])
    monitored_companies = dart_control1.multiselect(
        f"조회 시공사 ({ranking_year}년 토건 Top 20)",
        dart_companies,
        default=dart_companies,
        key="dart_monitored_companies",
    )
    start_date = dart_control2.date_input("조회 시작일", value=date.today() - timedelta(days=365), key="dart_start_date")
    end_date = dart_control3.date_input("조회 종료일", value=date.today(), key="dart_end_date")

    if st.button("DART 공시 후보 조회", type="primary", disabled=not monitored_companies):
        if start_date > end_date:
            st.error("조회 시작일은 종료일보다 앞서야 합니다.")
        else:
            try:
                company_codes, unmatched = company_corp_codes(api_key, monitored_companies)
                candidates = collect_dart_candidates(
                    api_key, company_codes, start_date.isoformat(), end_date.isoformat()
                )
                candidates = _match_dart_projects(enrich_dart_candidates(api_key, candidates), projects)
                if unmatched:
                    st.caption("DART 법인코드를 자동 연결하지 못한 시공사: " + ", ".join(unmatched))
                if candidates.empty:
                    st.info("선택 기간에 제목 기준으로 추출된 검토 후보가 없습니다.")
                else:
                    st.dataframe(
                        candidates[["공시일", "시공사_표준화", "공시제목", "계약명", "공급지역", "추천 정비사업", "자동매칭 근거", "판정"]],
                        hide_index=True, use_container_width=True,
                    )
                    st.download_button(
                        "검토 후보 CSV 내려받기",
                        candidates.to_csv(index=False, encoding="utf-8-sig"),
                        file_name="DART_정비사업_시공사_검토후보.csv",
                        mime="text/csv",
                    )
                    for _, item in candidates.iterrows():
                        st.link_button(
                            f"공시 원문 열기 · {item['공시일']} · {item['시공사_표준화']} · {item['공시제목']}",
                            item["원문URL"],
                        )
            except Exception as error:
                st.error(f"DART 공시 조회 중 오류가 발생했습니다: {error}")

