# axis_a/territory_map.py

import copy
import json
from pathlib import Path
from urllib.request import Request, urlopen

import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium


# =========================================================
# 1. 파일 위치
# =========================================================

ROOT = Path(__file__).resolve().parents[1]

CSV_PATH = ROOT / "data" / "서울시_공동주택_1차전처리.csv"
BOUNDARY_PATH = ROOT / "data" / "seoul_gu.geojson"

# 로컬 경계파일이 없을 때 사용하는 임시 경계
BOUNDARY_URL = (
    "https://raw.githubusercontent.com/"
    "southkorea/seoul-maps/master/kostat/2013/json/"
    "seoul_municipalities_geo_simple.json"
)


# =========================================================
# 2. 데이터 불러오기
# =========================================================

@st.cache_data(show_spinner=False)
def load_apartment_data():
    """CSV를 불러오고 분석에 필요한 열만 정리합니다."""

    if not CSV_PATH.exists():
        raise FileNotFoundError(
            f"CSV 파일을 찾을 수 없습니다: {CSV_PATH}"
        )

    # 한글 CSV 인코딩 자동 확인
    for encoding in ["utf-8-sig", "cp949", "euc-kr"]:
        try:
            df = pd.read_csv(CSV_PATH, encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("CSV 파일 인코딩을 확인해주세요.")

    required_columns = [
        "주소(시군구)",
        "k-전체세대수",
        "k-사용검사일-사용승인일",
        "기업그룹",
    ]

    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f"CSV에 필요한 열이 없습니다: {missing}"
        )

    # 자치구
    df["자치구"] = (
        df["주소(시군구)"]
        .astype("string")
        .str.strip()
    )

    # 세대수
    df["세대수"] = pd.to_numeric(
        df["k-전체세대수"]
        .astype(str)
        .str.replace(",", "", regex=False),
        errors="coerce",
    )

    # 사용승인연도
    df["승인일"] = pd.to_datetime(
        df["k-사용검사일-사용승인일"],
        errors="coerce",
    )
    df["승인연도"] = df["승인일"].dt.year

    # 기업그룹 결측값 → 기타
    df["기업그룹"] = (
        df["기업그룹"]
        .astype("string")
        .fillna("기타")
        .str.strip()
    )

    none_values = ["", "none", "nan", "null", "<na>"]

    df.loc[
        df["기업그룹"].str.lower().isin(none_values),
        "기업그룹",
    ] = "기타"

    # 분석에 필요한 값이 없는 행 제거
    df = df.dropna(
        subset=["자치구", "세대수", "승인연도"]
    )

    df = df[
        (df["세대수"] > 0)
        & (df["자치구"].str.endswith("구"))
    ].copy()

    df["승인연도"] = df["승인연도"].astype(int)

    return df


@st.cache_data(show_spinner=False)
def load_seoul_boundary():
    """로컬 경계를 우선 사용하고, 없으면 임시 경계를 불러옵니다."""

    if BOUNDARY_PATH.exists():
        with open(
            BOUNDARY_PATH,
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(file)

    request = Request(
        BOUNDARY_URL,
        headers={"User-Agent": "Mozilla/5.0"},
    )

    with urlopen(request, timeout=20) as response:
        return json.loads(
            response.read().decode("utf-8")
        )


# =========================================================
# 3. 컨소시엄 1/n 배분 및 점유율 계산
# =========================================================

def calculate_share(df, metric, household_weight=0.5):
    """세대수와 단지수를 참여 시공사 수만큼 나눠 계산합니다."""

    work = df.reset_index(drop=True).copy()
    work["단지ID"] = work.index

    # 기업그룹에 ';'가 있으면 컨소시엄으로 판단
    work["참여기업"] = work["기업그룹"].str.split(";")
    work["참여사수"] = (
        work["참여기업"]
        .str.len()
        .clip(lower=1)
    )

    expanded = work.explode("참여기업")

    expanded["참여기업"] = (
        expanded["참여기업"]
        .astype("string")
        .str.strip()
        .replace("", "기타")
        .fillna("기타")
    )

    # 컨소시엄 1/n 배분
    expanded["배분세대수"] = (
        expanded["세대수"]
        / expanded["참여사수"]
    )
    expanded["배분단지수"] = (
        1
        / expanded["참여사수"]
    )

    stats = (
        expanded
        .groupby(
            ["자치구", "참여기업"],
            as_index=False,
        )
        .agg(
            세대수=("배분세대수", "sum"),
            단지수=("배분단지수", "sum"),
        )
    )

    # 자치구별 전체 공급량
    stats["자치구전체세대수"] = (
        stats.groupby("자치구")["세대수"]
        .transform("sum")
    )
    stats["자치구전체단지수"] = (
        stats.groupby("자치구")["단지수"]
        .transform("sum")
    )

    stats["세대수점유율"] = (
        stats["세대수"]
        / stats["자치구전체세대수"]
        * 100
    )

    stats["단지수점유율"] = (
        stats["단지수"]
        / stats["자치구전체단지수"]
        * 100
    )

    stats["종합영토지수"] = (
        household_weight
        * stats["세대수점유율"]
        + (1 - household_weight)
        * stats["단지수점유율"]
    )

    metric_column = {
        "세대수 점유율": "세대수점유율",
        "단지수 점유율": "단지수점유율",
        "종합 영토지수": "종합영토지수",
    }[metric]

    stats["점유율"] = stats[metric_column]

    return stats


# =========================================================
# 4. 고정 라벨 없는 Folium 지도
# =========================================================

def build_map(boundary, stats):
    """자치구 폴리곤과 마우스 툴팁만 표시합니다."""

    boundary = copy.deepcopy(boundary)

    # 기타는 분모에는 포함하지만 1위 시공사에서는 제외
    ranking = stats[
        stats["참여기업"] != "기타"
    ].copy()

    if ranking.empty:
        ranking = stats.copy()

    leader_index = (
        ranking.groupby("자치구")["점유율"]
        .idxmax()
    )

    leaders = (
        ranking.loc[leader_index]
        .set_index("자치구")
        .to_dict("index")
    )

    # GeoJSON 속성에 통계정보 넣기
    for feature in boundary["features"]:
        properties = feature.setdefault(
            "properties",
            {},
        )

        gu_name = (
            properties.get("name")
            or properties.get("SIG_KOR_NM")
            or properties.get("자치구")
        )

        result = leaders.get(gu_name)

        properties["자치구"] = gu_name

        if result:
            properties["1위 시공사"] = result["참여기업"]
            properties["점유율 표시"] = (
                f"{result['점유율']:.1f}%"
            )
            properties["점유율 숫자"] = float(
                result["점유율"]
            )
        else:
            properties["1위 시공사"] = "데이터 없음"
            properties["점유율 표시"] = "-"
            properties["점유율 숫자"] = 0.0

    territory_map = folium.Map(
        location=[37.5665, 126.9780],
        zoom_start=10,
        tiles=None,
        control_scale=True,
    )

    # 밝은 배경지도
    folium.TileLayer(
        tiles="CartoDB positron",
        name="밝은 지도",
        control=True,
    ).add_to(territory_map)

    folium.TileLayer(
        tiles="OpenStreetMap",
        name="일반 지도",
        control=True,
    ).add_to(territory_map)

    def style_function(feature):
        share = feature["properties"].get(
            "점유율 숫자",
            0,
        )

        return {
            "fillColor": "#2563EB",
            "color": "#475569",
            "weight": 1.2,
            "fillOpacity": min(
                0.18 + share / 60,
                0.75,
            ),
        }

    def highlight_function(_):
        return {
            "color": "#111827",
            "weight": 3,
            "fillOpacity": 0.8,
        }

    folium.GeoJson(
        boundary,
        name="자치구별 시공사 점유율",
        style_function=style_function,
        highlight_function=highlight_function,

        # 고정 네모 박스 대신 마우스를 올렸을 때 표시
        tooltip=folium.GeoJsonTooltip(
            fields=[
                "자치구",
                "1위 시공사",
                "점유율 표시",
            ],
            aliases=[
                "자치구",
                "1위 시공사",
                "점유율",
            ],
            sticky=False,
            labels=True,
            style="""
                background-color: white;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                padding: 8px;
                color: #111827;
                font-size: 13px;
            """,
        ),
    ).add_to(territory_map)

    # 서울 전체가 첫 화면에 들어오도록 설정
    territory_map.fit_bounds(
        [
            [37.41, 126.76],
            [37.71, 127.19],
        ]
    )

    folium.LayerControl(
        collapsed=True
    ).add_to(territory_map)

    return territory_map


# =========================================================
# 5. 선택 자치구 원형 그래프
# =========================================================

def draw_donut(stats, selected_gu, metric):
    selected = (
        stats[stats["자치구"] == selected_gu]
        .sort_values("점유율", ascending=False)
        .copy()
    )

    if selected.empty:
        st.info("표시할 데이터가 없습니다.")
        return

    fig = px.pie(
        selected,
        names="참여기업",
        values="점유율",
        hole=0.58,
    )

    fig.update_traces(
        textposition="inside",
        textinfo="percent",
        hovertemplate=(
            "<b>%{label}</b><br>"
            "%{value:.1f}%"
            "<extra></extra>"
        ),
    )

    fig.update_layout(
        title=f"{selected_gu} · {metric}",
        margin=dict(l=10, r=10, t=60, b=10),
        height=430,
        legend_title_text="시공사",
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
    )

    table = selected[
        [
            "참여기업",
            "세대수",
            "단지수",
            "점유율",
        ]
    ].copy()

    table.columns = [
        "시공사",
        "배분 세대수",
        "배분 단지수",
        "점유율(%)",
    ]

    table["배분 세대수"] = (
        table["배분 세대수"].round(0)
    )
    table["배분 단지수"] = (
        table["배분 단지수"].round(1)
    )
    table["점유율(%)"] = (
        table["점유율(%)"].round(1)
    )

    st.dataframe(
        table,
        hide_index=True,
        use_container_width=True,
    )


# =========================================================
# 6. Streamlit 화면
# =========================================================

def render_territory_map():
    st.subheader("서울 시공사 영토지도")

    try:
        df = load_apartment_data()
        boundary = load_seoul_boundary()

    except Exception as error:
        st.error(str(error))
        return

    min_year = int(df["승인연도"].min())
    max_year = int(df["승인연도"].max())

    with st.sidebar:
        st.markdown("### 영토지도 설정")

        period_mode = st.radio(
            "시간 기준",
            ["기간 공급", "누적 공급"],
            horizontal=True,
        )

        if period_mode == "기간 공급":
            start_year, end_year = st.slider(
                "사용승인연도",
                min_year,
                max_year,
                (min_year, max_year),
            )

            filtered = df[
                df["승인연도"].between(
                    start_year,
                    end_year,
                )
            ].copy()

        else:
            end_year = st.slider(
                "누적 기준연도",
                min_year,
                max_year,
                max_year,
            )

            filtered = df[
                df["승인연도"] <= end_year
            ].copy()

        metric = st.radio(
            "점유율 기준",
            [
                "세대수 점유율",
                "단지수 점유율",
                "종합 영토지수",
            ],
        )

        household_weight = 0.5

        if metric == "종합 영토지수":
            household_weight = (
                st.slider(
                    "세대수 가중치",
                    0,
                    100,
                    50,
                    step=10,
                )
                / 100
            )

            st.caption(
                f"세대수 {household_weight:.0%} · "
                f"단지수 {1-household_weight:.0%}"
            )

    if filtered.empty:
        st.warning(
            "선택한 기간에 표시할 데이터가 없습니다."
        )
        return

    stats = calculate_share(
        filtered,
        metric,
        household_weight,
    )

    territory_map = build_map(
        boundary,
        stats,
    )

    map_column, chart_column = st.columns(
        [1.7, 1],
        gap="large",
    )

    with map_column:
        map_result = st_folium(
            territory_map,
            height=650,
            use_container_width=True,
            key="territory_map",
        )

    # 지도에서 클릭한 자치구 확인
    drawing = map_result.get(
        "last_active_drawing"
    )

    if drawing:
        properties = drawing.get(
            "properties",
            {},
        )

        clicked_gu = properties.get("자치구")

        if clicked_gu:
            st.session_state["selected_gu"] = clicked_gu

    selected_gu = st.session_state.get(
        "selected_gu"
    )

    with chart_column:
        if selected_gu:
            draw_donut(
                stats,
                selected_gu,
                metric,
            )
        else:
            st.info(
                "지도에서 자치구를 클릭하면 "
                "시공사별 점유율이 표시됩니다."
            )


# streamlit_app.py에서 render()로 불러와도 작동
def render():
    render_territory_map()


if __name__ == "__main__":
    render_territory_map()
