import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

from common.data_loader import load_apartment_data
from common.map_utils import build_supply_subject_choropleth
from common.public_supply import (
    SUBJECT_COLORS,
    SUPPLY_SUBJECT_ORDER,
    prepare_supply_subject_data,
    summarize_subject_by_district,
    summarize_supply_subjects,
)


def _donut(summary: pd.DataFrame) -> None:
    figure = px.pie(
        summary,
        names="공급주체",
        values="보정 공급 기여지수(%)",
        hole=0.58,
        color="공급주체",
        color_discrete_map=SUBJECT_COLORS,
        category_orders={"공급주체": SUPPLY_SUBJECT_ORDER},
    )
    figure.update_traces(
        textinfo="percent",
        texttemplate="%{percent:.1%}",
        hovertemplate="<b>%{label}</b><br>보정 공급 기여지수: %{value:.1f}%<extra></extra>",
    )
    figure.update_layout(
        margin=dict(l=0, r=0, t=18, b=0),
        legend_title_text="공급주체",
        annotations=[dict(text="서울<br>전체", x=0.5, y=0.5, showarrow=False, font_size=16)],
    )
    st.plotly_chart(figure, use_container_width=True, config={"displayModeBar": False})


def _selected_row(summary: pd.DataFrame, subject: str) -> pd.Series:
    return summary.loc[summary["공급주체"].eq(subject)].iloc[0]


def render_public_supply_map() -> None:
    st.subheader("아파트 공급주체 구성·지역분포")
    st.caption(
        "서울 아파트 공급에서 공공·민간·조합·공동 시행이 각각 어느 정도를 차지하고, "
        "그 비중이 자치구별로 어떻게 다른지 확인합니다."
    )

    try:
        apartment = load_apartment_data()
    except (FileNotFoundError, ValueError) as error:
        st.error(str(error))
        return

    classified, excluded = prepare_supply_subject_data(apartment)
    if classified.empty:
        st.warning("공급주체가 분류된 아파트 단지가 없습니다.")
        return
    summary = summarize_supply_subjects(classified)

    composition_column, map_column = st.columns([0.88, 1.65], gap="large")
    with composition_column:
        st.markdown("#### 서울 전체 공급주체 구성")
        st.caption("보정 공급 기여지수 = 세대수 비중 70% + 동수 비중 30%")
        _donut(summary)
        selected_subject = st.radio(
            "지도와 상세 수치에서 볼 공급주체",
            SUPPLY_SUBJECT_ORDER,
            horizontal=False,
        )
        st.caption("공동 시행 단지는 공공과 민간·조합에 중복 산입하지 않고 별도 주체로 계산합니다.")

    district_summary = summarize_subject_by_district(classified, selected_subject)
    selected = _selected_row(summary, selected_subject)

    with map_column:
        st.markdown(f"#### 자치구별 {selected_subject} 공급 기여도")
        st.caption(
            "색이 진할수록 해당 자치구의 분류된 아파트 공급에서 선택한 주체의 기여도가 높습니다. "
            "지도 위에 마우스를 올리면 상세 수치를 볼 수 있습니다."
        )
        try:
            supply_map = build_supply_subject_choropleth(district_summary, selected_subject)
        except (FileNotFoundError, ValueError) as error:
            st.error(str(error))
        else:
            st_folium(supply_map, height=590, use_container_width=True, returned_objects=[])

    st.divider()
    st.markdown(f"#### {selected_subject} 상세")
    detail1, detail2, detail3, detail4 = st.columns(4)
    detail1.metric("보정 공급 기여지수", f"{selected['보정 공급 기여지수(%)']:.1f}%")
    detail2.metric("세대수 비중", f"{selected['세대수 비중(%)']:.1f}%")
    detail3.metric("동수 비중", f"{selected['동수 비중(%)']:.1f}%")
    detail4.metric("분류 단지 수", f"{int(selected['단지수']):,}개")

    chart_column, table_column = st.columns([1, 1.25], gap="large")
    with chart_column:
        st.markdown(f"#### {selected_subject} 비중이 높은 자치구")
        st.bar_chart(
            district_summary.set_index("시군구")["보정 공급 기여지수(%)"],
            horizontal=True,
            color="#2F6B9A",
        )
    with table_column:
        st.markdown("#### 자치구별 상세 수치")
        display = district_summary[
            [
                "시군구",
                "보정 공급 기여지수(%)",
                "선택_단지수",
                "선택_세대수",
                "선택_동수",
                "전체_세대수",
            ]
        ]
        st.dataframe(
            display,
            hide_index=True,
            use_container_width=True,
            height=430,
            column_config={
                "보정 공급 기여지수(%)": st.column_config.NumberColumn(format="%.1f%%")
            },
        )

    if len(excluded):
        st.caption(
            f"분류 기준: 기타공공은 공공에 통합했습니다. 미상·확인필요 {len(excluded):,}개 단지는 "
            "공급주체 비율의 분모에서 제외했으며, 원자료에는 유지합니다."
        )
