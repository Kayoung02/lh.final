# =========================================================
# 0. 라이브러리
# =========================================================

from pathlib import Path
import html
import io
import json
import math
import re

import folium
import geopandas as gpd
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

from branca.colormap import LinearColormap
from folium.features import DivIcon, GeoJsonTooltip
from shapely.geometry import Point
from streamlit_folium import st_folium


# =========================================================
# 1. 기본 설정
# 나중에 데이터 파일명이나 경계 파일을 바꿀 때 수정
# =========================================================

DATA_PATH = Path(
    "data/서울시_공동주택_1차전처리.csv"
)

BOUNDARY_PATH = Path(
    "data/seoul_gu.geojson"
)

# 로컬 경계 파일이 없을 때 임시로 사용하는 서울 자치구 경계
BOUNDARY_URL = (
    "https://raw.githubusercontent.com/"
    "southkorea/seoul-maps/master/kostat/2013/json/"
    "seoul_municipalities_geo_simple.json"
)

# 기타는 전체 세대수에는 포함하지만
# 1위 시공사 선정과 시공사 선택 목록에서는 제외
EXCLUDED_COMPANIES = {
    "기타",
    "미상",
}


# =========================================================
# 2. 데이터 불러오기
# =========================================================

@st.cache_data(show_spinner=False)
def load_apartment_data() -> pd.DataFrame:
    """아파트 CSV를 UTF-8 또는 CP949 방식으로 불러옵니다."""

    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"파일을 찾을 수 없습니다: {DATA_PATH}"
        )

    file_bytes = DATA_PATH.read_bytes()

    for encoding in [
        "utf-8-sig",
        "cp949",
        "utf-8",
    ]:
        try:
            return pd.read_csv(
                io.BytesIO(file_bytes),
                encoding=encoding,
                low_memory=False,
            )

        except UnicodeDecodeError:
            continue

    raise ValueError(
        "CSV 파일의 인코딩을 확인할 수 없습니다."
    )


@st.cache_data(show_spinner=False)
def load_seoul_boundary() -> gpd.GeoDataFrame:
    """서울 자치구 경계를 불러옵니다."""

    if BOUNDARY_PATH.exists():
        boundary = gpd.read_file(
            BOUNDARY_PATH
        )

    else:
        response = requests.get(
            BOUNDARY_URL,
            timeout=30,
        )
        response.raise_for_status()

        boundary = gpd.GeoDataFrame.from_features(
            response.json()["features"],
            crs="EPSG:4326",
        )

    boundary = boundary.to_crs(
        "EPSG:4326"
    )

    # 경계 파일마다 자치구 열 이름이 다를 수 있음
    name_column = next(
        (
            column
            for column in [
                "자치구",
                "name",
                "SIG_KOR_NM",
                "시군구명",
                "구명",
            ]
            if column in boundary.columns
        ),
        None,
    )

    if name_column is None:
        raise ValueError(
            "경계 파일에서 자치구 이름 열을 찾지 못했습니다."
        )

    boundary = boundary.rename(
        columns={
            name_column: "자치구"
        }
    )

    return boundary[
        [
            "자치구",
            "geometry",
        ]
    ].copy()


# =========================================================
# 3. 데이터 전처리
# 기업그룹, 결측값, 컨소시엄 규칙을 바꿀 때 수정
# =========================================================

def split_companies(value) -> list[str]:
    """컨소시엄 기업그룹을 개별 회사로 분리합니다."""

    if pd.isna(value):
        return ["기타"]

    text = str(value).strip()

    if text.lower() in {
        "",
        "none",
        "nan",
        "null",
        "-",
        "없음",
        "미상",
    }:
        return ["기타"]

    companies = re.split(
        r"\s*(?:;|,|/|\||\+|&|·)\s*",
        text,
    )

    # 중복 회사 제거
    return list(
        dict.fromkeys(
            company.strip()
            for company in companies
            if company.strip()
        )
    ) or ["기타"]


@st.cache_data(show_spinner=False)
def prepare_data(
    raw_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """
    분석용 단지 데이터와 시공사별 데이터를 만듭니다.

    - 기업그룹 결측: 기타
    - 자치구·세대수·준공연도 결측: 제거
    - 컨소시엄: 세대수와 단지 수 모두 1/n
    """

    required = [
        "주소(시군구)",
        "k-전체세대수",
        "기업그룹",
        "k-사용검사일-사용승인일",
    ]

    missing = [
        column
        for column in required
        if column not in raw_df.columns
    ]

    if missing:
        raise ValueError(
            "필요한 열이 없습니다: "
            + ", ".join(missing)
        )

    df = raw_df.copy()
    original_count = len(df)

    # 자치구
    df["자치구"] = (
        df["주소(시군구)"]
        .astype(str)
        .str.extract(
            r"([가-힣]+구)",
            expand=False,
        )
    )

    # 세대수
    df["세대수"] = pd.to_numeric(
        df["k-전체세대수"]
        .astype(str)
        .str.replace(",", "", regex=False),
        errors="coerce",
    )

    # 사용승인연도
    df["준공연도"] = pd.to_numeric(
        df["k-사용검사일-사용승인일"]
        .astype(str)
        .str.extract(
            r"((?:19|20)\d{2})",
            expand=False,
        ),
        errors="coerce",
    )

    # 기업그룹 결측 → 기타
    group = (
        df["기업그룹"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    none_mask = (
        group
        .str.lower()
        .isin(
            {
                "",
                "none",
                "nan",
                "null",
                "-",
                "없음",
                "미상",
            }
        )
    )

    other_count = int(
        none_mask.sum()
    )

    df["기업그룹정리"] = (
        group.mask(
            none_mask,
            "기타",
        )
    )

    # 분석 필수값 결측 제거
    df = df[
        df["자치구"].notna()
        & df["준공연도"].notna()
        & df["세대수"].notna()
        & (df["세대수"] > 0)
    ].copy()

    df["준공연도"] = (
        df["준공연도"].astype(int)
    )

    # 컨소시엄 처리
    df["시공사목록"] = (
        df["기업그룹정리"]
        .apply(split_companies)
    )

    df["컨소시엄수"] = (
        df["시공사목록"]
        .apply(
            lambda companies: max(
                len(companies),
                1,
            )
        )
    )

    # 300세대, 2개 회사 컨소시엄
    # → 각 회사 150세대, 0.5개 단지
    df["배분세대수"] = (
        df["세대수"]
        / df["컨소시엄수"]
    )

    df["배분단지수"] = (
        1
        / df["컨소시엄수"]
    )

    company_df = (
        df
        .explode("시공사목록")
        .rename(
            columns={
                "시공사목록": "시공사"
            }
        )
        .copy()
    )

    quality = {
        "원본": original_count,
        "사용": len(df),
        "제거": original_count - len(df),
        "기타": other_count,
    }

    return df, company_df, quality


# =========================================================
# 4. 점유율 계산
# 계산 기준을 바꾸고 싶을 때 수정
# =========================================================

def calculate_gu_share(
    apartment_df: pd.DataFrame,
    company_df: pd.DataFrame,
    selected_company: str,
    share_type: str,
) -> pd.DataFrame:
    """
    세대수 점유율:
    시공사 공급세대수 ÷ 자치구 전체세대수

    단지수 점유율:
    시공사 공급단지수 ÷ 자치구 전체단지수
    """

    gu_total = (
        apartment_df
        .groupby(
            "자치구",
            as_index=False,
        )
        .agg(
            전체세대수=("세대수", "sum"),
            전체단지수=("세대수", "size"),
        )
    )

    company_supply = (
        company_df[
            ~company_df["시공사"].isin(
                EXCLUDED_COMPANIES
            )
        ]
        .groupby(
            [
                "자치구",
                "시공사",
            ],
            as_index=False,
        )
        .agg(
            공급세대수=("배분세대수", "sum"),
            공급단지수=("배분단지수", "sum"),
        )
    )

    ranking_column = (
        "공급세대수"
        if share_type == "세대수 점유율"
        else "공급단지수"
    )

    if selected_company == "구별 1위 시공사":
        selected = (
            company_supply
            .sort_values(
                [
                    "자치구",
                    ranking_column,
                ],
                ascending=[
                    True,
                    False,
                ],
            )
            .drop_duplicates(
                "자치구"
            )
        )

        empty_company = "자료 없음"

    else:
        selected = company_supply[
            company_supply["시공사"]
            == selected_company
        ].copy()

        empty_company = selected_company

    result = gu_total.merge(
        selected,
        on="자치구",
        how="left",
    )

    result["시공사"] = (
        result["시공사"]
        .fillna(empty_company)
    )

    result[
        [
            "공급세대수",
            "공급단지수",
        ]
    ] = (
        result[
            [
                "공급세대수",
                "공급단지수",
            ]
        ]
        .fillna(0)
    )

    result["세대수점유율"] = (
        result["공급세대수"]
        / result["전체세대수"]
        * 100
    ).fillna(0)

    result["단지수점유율"] = (
        result["공급단지수"]
        / result["전체단지수"]
        * 100
    ).fillna(0)

    result["지도점유율"] = (
        result["세대수점유율"]
        if share_type == "세대수 점유율"
        else result["단지수점유율"]
    )

    return result


def calculate_gu_breakdown(
    company_df: pd.DataFrame,
    gu_name: str,
) -> pd.DataFrame:
    """선택한 자치구의 전체 시공사 구성을 계산합니다."""

    breakdown = (
        company_df[
            company_df["자치구"]
            == gu_name
        ]
        .groupby(
            "시공사",
            as_index=False,
        )
        .agg(
            공급세대수=("배분세대수", "sum"),
            공급단지수=("배분단지수", "sum"),
        )
    )

    household_total = (
        breakdown["공급세대수"].sum()
    )

    complex_total = (
        breakdown["공급단지수"].sum()
    )

    breakdown["세대수점유율"] = (
        breakdown["공급세대수"]
        / household_total
        * 100
    ).fillna(0)

    breakdown["단지수점유율"] = (
        breakdown["공급단지수"]
        / complex_total
        * 100
    ).fillna(0)

    return breakdown


# =========================================================
# 5. 지도 생성
# 지도 색상이나 라벨 디자인을 바꿀 때 수정
# =========================================================

def create_map(
    boundary: gpd.GeoDataFrame,
    gu_share: pd.DataFrame,
    share_type: str,
    selected_gu: str,
) -> folium.Map:

    map_data = boundary.merge(
        gu_share,
        on="자치구",
        how="left",
    )

    map_data["시공사"] = (
        map_data["시공사"]
        .fillna("자료 없음")
    )

    numeric_columns = [
        "전체세대수",
        "전체단지수",
        "공급세대수",
        "공급단지수",
        "세대수점유율",
        "단지수점유율",
        "지도점유율",
    ]

    for column in numeric_columns:
        map_data[column] = pd.to_numeric(
            map_data[column],
            errors="coerce",
        ).fillna(0)

    map_data["세대수점유율"] = (
        map_data["세대수점유율"].round(1)
    )

    map_data["단지수점유율"] = (
        map_data["단지수점유율"].round(1)
    )

    map_data["지도점유율"] = (
        map_data["지도점유율"].round(1)
    )

    maximum = max(
        10,
        math.ceil(
            float(
                map_data["지도점유율"].max()
            ) / 10
        ) * 10,
    )

    colors = LinearColormap(
        [
            "#eff6ff",
            "#bfdbfe",
            "#60a5fa",
            "#2563eb",
            "#1e3a8a",
        ],
        vmin=0,
        vmax=maximum,
        caption=f"{share_type} (%)",
    )

    territory_map = folium.Map(
        location=[
            37.5665,
            126.9780,
        ],
        zoom_start=10,
        tiles=None,
        control_scale=True,
    )

    folium.TileLayer(
        "OpenStreetMap",
        name="일반 지도",
        show=True,
    ).add_to(territory_map)

    folium.TileLayer(
        "CartoDB positron",
        name="밝은 지도",
        show=False,
    ).add_to(territory_map)

    geojson = json.loads(
        map_data.to_json()
    )

    def polygon_style(feature):
        gu_name = (
            feature["properties"]["자치구"]
        )

        return {
            "fillColor": colors(
                feature["properties"][
                    "지도점유율"
                ]
            ),
            "fillOpacity": 0.75,
            "color": (
                "#f97316"
                if gu_name == selected_gu
                else "#475569"
            ),
            "weight": (
                4
                if gu_name == selected_gu
                else 1.2
            ),
        }

    folium.GeoJson(
        geojson,
        name="시공사 점유율",
        style_function=polygon_style,
        highlight_function=lambda feature: {
            "color": "#111827",
            "weight": 3,
            "fillOpacity": 0.9,
        },
        tooltip=GeoJsonTooltip(
            fields=[
                "자치구",
                "시공사",
                "세대수점유율",
                "단지수점유율",
                "공급세대수",
                "공급단지수",
            ],
            aliases=[
                "자치구",
                "대표 시공사",
                "세대수 점유율",
                "단지수 점유율",
                "공급 세대수",
                "공급 단지수",
            ],
            localize=True,
        ),
    ).add_to(territory_map)

    colors.add_to(
        territory_map
    )

    # 자치구 중앙 라벨
    label_points = (
        map_data
        .to_crs("EPSG:5179")
        .representative_point()
        .to_crs("EPSG:4326")
    )

    for point, (_, row) in zip(
        label_points,
        map_data.iterrows(),
    ):
        gu_name = html.escape(
            str(row["자치구"])
        )

        company = html.escape(
            str(row["시공사"])
        )

        share = float(
            row["지도점유율"]
        )

        label = f"""
        <div style="
            transform:translate(-50%,-50%);
            min-width:72px;
            padding:4px 6px;
            border:1px solid #94a3b8;
            border-radius:6px;
            background:rgba(255,255,255,0.90);
            text-align:center;
            font-size:10px;
            line-height:1.35;
            white-space:nowrap;
            pointer-events:none;
        ">
            <b>{gu_name}</b><br>
            {company}<br>
            <span style="
                color:#1d4ed8;
                font-size:12px;
                font-weight:700;
            ">
                {share:.1f}%
            </span>
        </div>
        """

        folium.Marker(
            [
                point.y,
                point.x,
            ],
            icon=DivIcon(
                icon_size=(0, 0),
                icon_anchor=(0, 0),
                html=label,
            ),
        ).add_to(territory_map)

    min_x, min_y, max_x, max_y = (
        map_data.total_bounds
    )

    territory_map.fit_bounds(
        [
            [min_y, min_x],
            [max_y, max_x],
        ]
    )

    folium.LayerControl(
        collapsed=True
    ).add_to(territory_map)

    return territory_map


# =========================================================
# 6. 도넛 차트
# 표시할 시공사 개수를 바꿀 때 head(8)을 수정
# =========================================================

def create_donut_chart(
    breakdown: pd.DataFrame,
    gu_name: str,
    share_type: str,
    selected_company: str,
):
    value_column = (
        "공급세대수"
        if share_type == "세대수 점유율"
        else "공급단지수"
    )

    ranked = breakdown.sort_values(
        value_column,
        ascending=False,
    )

    # 차트에는 상위 8개 우선 표시
    visible = ranked.head(8).copy()

    # 선택한 회사가 상위 8개 밖이면 추가
    if (
        selected_company != "구별 1위 시공사"
        and selected_company
        in ranked["시공사"].values
        and selected_company
        not in visible["시공사"].values
    ):
        visible = pd.concat(
            [
                visible,
                ranked[
                    ranked["시공사"]
                    == selected_company
                ],
            ],
            ignore_index=True,
        )

    remaining = ranked[
        ~ranked["시공사"].isin(
            visible["시공사"]
        )
    ]

    if not remaining.empty:
        other_row = pd.DataFrame(
            {
                "시공사": [
                    "그 외 시공사"
                ],
                value_column: [
                    remaining[
                        value_column
                    ].sum()
                ],
            }
        )

        visible = pd.concat(
            [
                visible,
                other_row,
            ],
            ignore_index=True,
        )

    visible["시공사"] = (
        visible["시공사"]
        .replace(
            {
                "기타": "기타·미분류"
            }
        )
    )

    figure = px.pie(
        visible,
        names="시공사",
        values=value_column,
        hole=0.58,
        color_discrete_sequence=(
            px.colors.qualitative.Set3
        ),
    )

    figure.update_traces(
        textinfo="percent",
        textposition="inside",
        hovertemplate=(
            "<b>%{label}</b><br>"
            "값: %{value:,.1f}<br>"
            "점유율: %{percent}"
            "<extra></extra>"
        ),
    )

    figure.update_layout(
        height=500,
        margin={
            "l": 10,
            "r": 10,
            "t": 20,
            "b": 10,
        },
        legend={
            "orientation": "h",
            "y": -0.05,
            "x": 0.5,
            "xanchor": "center",
        },
        annotations=[
            {
                "text": (
                    f"<b>{gu_name}</b><br>"
                    f"{share_type}"
                ),
                "x": 0.5,
                "y": 0.5,
                "showarrow": False,
            }
        ],
    )

    return figure


# =========================================================
# 7. 지도 클릭 좌표를 자치구로 변환
# =========================================================

def find_clicked_gu(
    boundary: gpd.GeoDataFrame,
    clicked,
):
    if not clicked:
        return None

    latitude = clicked.get("lat")
    longitude = clicked.get("lng")

    if (
        latitude is None
        or longitude is None
    ):
        return None

    point = Point(
        longitude,
        latitude,
    )

    matched = boundary[
        boundary.geometry.intersects(
            point
        )
    ]

    if matched.empty:
        return None

    return matched.iloc[0][
        "자치구"
    ]


# =========================================================
# 8. Streamlit 화면
# 필터나 화면 배치를 바꿀 때 수정
# =========================================================

def render_axis_a():
    st.title(
        "기존 아파트 시공사 영토"
    )

    st.caption(
        "공급 세대수와 단지 수를 기준으로 "
        "서울 자치구별 시공사 점유율을 비교합니다."
    )

    try:
        raw_df = load_apartment_data()

        (
            apartment_df,
            company_df,
            quality,
        ) = prepare_data(raw_df)

        boundary = load_seoul_boundary()

    except Exception as error:
        st.error(
            f"데이터 처리 오류: {error}"
        )
        return

    minimum_year = int(
        apartment_df["준공연도"].min()
    )

    maximum_year = int(
        apartment_df["준공연도"].max()
    )

    company_options = (
        company_df[
            ~company_df["시공사"].isin(
                EXCLUDED_COMPANIES
            )
        ]
        .groupby("시공사")[
            "배분세대수"
        ]
        .sum()
        .sort_values(
            ascending=False
        )
        .index
        .tolist()
    )

    # -----------------------------------------------------
    # 사이드바 필터
    # -----------------------------------------------------

    with st.sidebar:
        st.divider()
        st.subheader("축 A 필터")

        share_type = st.radio(
            "점유율 기준",
            [
                "세대수 점유율",
                "단지수 점유율",
            ],
            help=(
                "세대수는 공급 규모, "
                "단지수는 지역 진입 빈도를 의미합니다."
            ),
        )

        time_type = st.radio(
            "시간 기준",
            [
                "누적 영토",
                "기간 공급",
            ],
        )

        if time_type == "누적 영토":
            end_year = st.slider(
                "기준연도",
                minimum_year,
                maximum_year,
                maximum_year,
            )

            filtered_apartments = (
                apartment_df[
                    apartment_df["준공연도"]
                    <= end_year
                ]
            )

            filtered_companies = (
                company_df[
                    company_df["준공연도"]
                    <= end_year
                ]
            )

            period_text = (
                f"{end_year}년까지"
            )

        else:
            default_start = max(
                minimum_year,
                min(
                    2000,
                    maximum_year,
                ),
            )

            start_year, end_year = st.slider(
                "준공연도 범위",
                minimum_year,
                maximum_year,
                (
                    default_start,
                    maximum_year,
                ),
            )

            filtered_apartments = (
                apartment_df[
                    apartment_df[
                        "준공연도"
                    ].between(
                        start_year,
                        end_year,
                    )
                ]
            )

            filtered_companies = (
                company_df[
                    company_df[
                        "준공연도"
                    ].between(
                        start_year,
                        end_year,
                    )
                ]
            )

            period_text = (
                f"{start_year}~{end_year}년"
            )

        selected_company = st.selectbox(
            "시공사",
            [
                "구별 1위 시공사"
            ] + company_options,
        )

    if filtered_apartments.empty:
        st.warning(
            "선택한 기간에 데이터가 없습니다."
        )
        return

    gu_share = calculate_gu_share(
        filtered_apartments,
        filtered_companies,
        selected_company,
        share_type,
    )

    # -----------------------------------------------------
    # 상단 통계
    # -----------------------------------------------------

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "분석 단지",
        f"{len(filtered_apartments):,}개",
        period_text,
    )

    col2.metric(
        "분석 세대수",
        (
            f"{filtered_apartments['세대수'].sum():,.0f}"
            "세대"
        ),
    )

    col3.metric(
        "컨소시엄 단지",
        (
            f"{(filtered_apartments['컨소시엄수'] > 1).sum():,}"
            "개"
        ),
        "1/n 배분",
    )

    st.caption(
        f"원본 {quality['원본']:,}행 · "
        f"분석 {quality['사용']:,}행 · "
        f"필수값 결측 제거 {quality['제거']:,}행 · "
        f"기업그룹 기타 분류 {quality['기타']:,}행"
    )

    # 선택 자치구 기본값
    if "axis_a_selected_gu" not in st.session_state:
        st.session_state[
            "axis_a_selected_gu"
        ] = "강남구"

    selected_gu = st.session_state[
        "axis_a_selected_gu"
    ]

    # -----------------------------------------------------
    # 지도 + 도넛 차트
    # -----------------------------------------------------

    map_column, chart_column = st.columns(
        [1.7, 1],
        gap="large",
    )

    with map_column:
        st.subheader(
            f"{selected_company} · {share_type}"
        )

        st.caption(
            "자치구를 클릭하면 오른쪽 구성이 변경됩니다."
        )

        territory_map = create_map(
            boundary,
            gu_share,
            share_type,
            selected_gu,
        )

        map_result = st_folium(
            territory_map,
            height=720,
            use_container_width=True,
            returned_objects=[
                "last_object_clicked"
            ],
            key="axis_a_map",
        )

        clicked_gu = find_clicked_gu(
            boundary,
            map_result.get(
                "last_object_clicked"
            ),
        )

        if (
            clicked_gu
            and clicked_gu
            != st.session_state[
                "axis_a_selected_gu"
            ]
        ):
            st.session_state[
                "axis_a_selected_gu"
            ] = clicked_gu

            st.rerun()

    selected_gu = st.session_state[
        "axis_a_selected_gu"
    ]

    breakdown = calculate_gu_breakdown(
        filtered_companies,
        selected_gu,
    )

    with chart_column:
        st.subheader(
            f"{selected_gu} 시공사 구성"
        )

        st.caption(
            f"{share_type} 기준입니다."
        )

        if breakdown.empty:
            st.info(
                "선택한 자치구의 데이터가 없습니다."
            )

        else:
            donut_chart = create_donut_chart(
                breakdown,
                selected_gu,
                share_type,
                selected_company,
            )

            st.plotly_chart(
                donut_chart,
                use_container_width=True,
                config={
                    "displayModeBar": False
                },
            )

    # -----------------------------------------------------
    # 상세 구성표
    # -----------------------------------------------------

    if not breakdown.empty:
        with st.expander(
            f"{selected_gu} 전체 시공사 구성표"
        ):
            table = (
                breakdown[
                    [
                        "시공사",
                        "공급세대수",
                        "세대수점유율",
                        "공급단지수",
                        "단지수점유율",
                    ]
                ]
                .sort_values(
                    "공급세대수",
                    ascending=False,
                )
                .reset_index(
                    drop=True
                )
                .rename(
                    columns={
                        "공급세대수": "공급 세대수",
                        "세대수점유율": "세대수 점유율(%)",
                        "공급단지수": "공급 단지수",
                        "단지수점유율": "단지수 점유율(%)",
                    }
                )
            )

            st.dataframe(
                table,
                use_container_width=True,
                hide_index=True,
            )

    st.caption(
        "'기타'는 전체 점유율의 분모와 도넛 차트에는 포함되지만, "
        "자치구 1위 시공사 선정에서는 제외됩니다."
    )
