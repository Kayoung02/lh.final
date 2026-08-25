from pathlib import Path
import io
import re
import html
import json
import math

import pandas as pd
import geopandas as gpd
import requests
import streamlit as st
import folium

from branca.colormap import LinearColormap
from folium.features import DivIcon, GeoJsonTooltip
from streamlit_folium import st_folium


# =========================================================
# 파일 경로
# =========================================================

DATA_PATH = Path(
    "data/서울시_공동주택_1차전처리.csv"
)

BOUNDARY_PATH = Path(
    "data/seoul_gu.geojson"
)

# 자치구 경계 파일이 없을 때 사용하는 임시 경계
BOUNDARY_FALLBACK_URL = (
    "https://raw.githubusercontent.com/"
    "southkorea/seoul-maps/master/kostat/2013/json/"
    "seoul_municipalities_geo_simple.json"
)


# =========================================================
# CSV 불러오기
# =========================================================

@st.cache_data(show_spinner=False)
def load_apartment_data(
    file_bytes: bytes,
) -> pd.DataFrame:
    """
    UTF-8 또는 CP949 형식의 CSV를 자동으로 불러옵니다.
    """

    encodings = [
        "utf-8-sig",
        "cp949",
        "utf-8",
    ]

    for encoding in encodings:
        try:
            return pd.read_csv(
                io.BytesIO(file_bytes),
                encoding=encoding,
                low_memory=False,
            )

        except UnicodeDecodeError:
            continue

    raise ValueError(
        "CSV 파일의 한글 인코딩을 확인할 수 없습니다."
    )


# =========================================================
# 서울 자치구 경계 불러오기
# =========================================================

@st.cache_data(show_spinner=False)
def load_seoul_boundary() -> gpd.GeoDataFrame:
    """
    data/seoul_gu.geojson 파일을 우선 사용합니다.

    파일이 없으면 임시 자치구 경계 데이터를
    인터넷에서 불러옵니다.
    """

    if BOUNDARY_PATH.exists():
        boundary = gpd.read_file(
            BOUNDARY_PATH
        )

    else:
        response = requests.get(
            BOUNDARY_FALLBACK_URL,
            timeout=30,
        )

        response.raise_for_status()

        geojson_data = response.json()

        boundary = (
            gpd.GeoDataFrame.from_features(
                geojson_data["features"],
                crs="EPSG:4326",
            )
        )

    boundary = boundary.to_crs(
        "EPSG:4326"
    )

    possible_name_columns = [
        "자치구",
        "name",
        "SIG_KOR_NM",
        "시군구명",
        "구명",
    ]

    district_column = next(
        (
            column
            for column in possible_name_columns
            if column in boundary.columns
        ),
        None,
    )

    if district_column is None:
        raise ValueError(
            "자치구 이름이 들어 있는 경계 열을 "
            "찾지 못했습니다."
        )

    boundary = boundary.rename(
        columns={
            district_column: "자치구"
        }
    )

    return boundary[
        [
            "자치구",
            "geometry",
        ]
    ].copy()


# =========================================================
# 기업그룹 처리
# =========================================================

def split_company_names(
    company_value,
) -> list[str]:
    """
    기업그룹의 컨소시엄 표기를 개별 시공사로 분리합니다.

    예:
    삼성물산; 현대건설
    → ["삼성물산", "현대건설"]
    """

    if pd.isna(company_value):
        return ["기타"]

    company_text = str(
        company_value
    ).strip()

    if company_text.lower() in {
        "",
        "none",
        "nan",
        "null",
        "-",
        "없음",
        "미상",
    }:
        return ["기타"]

    # 기업그룹 열은 이미 표준화되어 있으므로
    # 회사 이름은 변경하지 않고 구분자만 처리합니다.
    companies = re.split(
        r"\s*(?:;|,|/|\||\+|&|·)\s*",
        company_text,
    )

    cleaned_companies = []

    for company in companies:
        company = re.sub(
            r"\s+",
            " ",
            company,
        ).strip()

        if not company:
            continue

        if company not in cleaned_companies:
            cleaned_companies.append(
                company
            )

    return cleaned_companies or ["기타"]


# =========================================================
# 아파트 데이터 전처리
# =========================================================

@st.cache_data(show_spinner=False)
def prepare_apartment_data(
    raw_df: pd.DataFrame,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    dict,
]:
    """
    지도 분석에 필요한 데이터를 생성합니다.

    처리 원칙:
    1. 기업그룹 결측값은 '기타'로 처리
    2. 자치구·세대수·사용승인연도 결측은 제거
    3. 점유율은 단지 수가 아닌 세대수로 계산
    4. 컨소시엄은 참여 시공사 수만큼 1/n 배분
    """

    required_columns = [
        "주소(시군구)",
        "k-전체세대수",
        "기업그룹",
        "k-사용검사일-사용승인일",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in raw_df.columns
    ]

    if missing_columns:
        raise ValueError(
            "필요한 열이 없습니다: "
            + ", ".join(missing_columns)
        )

    apartment_df = raw_df.copy()

    original_row_count = len(
        apartment_df
    )

    # -----------------------------------------------------
    # 자치구 정리
    # -----------------------------------------------------

    apartment_df["자치구"] = (
        apartment_df["주소(시군구)"]
        .astype(str)
        .str.extract(
            r"([가-힣]+구)",
            expand=False,
        )
    )

    # -----------------------------------------------------
    # 세대수 정리
    # -----------------------------------------------------

    apartment_df["세대수"] = pd.to_numeric(
        apartment_df["k-전체세대수"]
        .astype(str)
        .str.replace(
            ",",
            "",
            regex=False,
        )
        .str.strip(),
        errors="coerce",
    )

    # -----------------------------------------------------
    # 사용승인연도 정리
    # -----------------------------------------------------

    apartment_df["준공연도"] = pd.to_numeric(
        apartment_df[
            "k-사용검사일-사용승인일"
        ]
        .astype(str)
        .str.extract(
            r"((?:19|20)\d{2})",
            expand=False,
        ),
        errors="coerce",
    )

    # -----------------------------------------------------
    # 기업그룹 결측값 → 기타
    # -----------------------------------------------------

    group_series = (
        apartment_df["기업그룹"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    none_values = {
        "",
        "none",
        "nan",
        "null",
        "-",
        "없음",
        "미상",
    }

    none_mask = (
        group_series
        .str.lower()
        .isin(none_values)
    )

    other_count = int(
        none_mask.sum()
    )

    apartment_df["기업그룹정리"] = (
        group_series.mask(
            none_mask,
            "기타",
        )
    )

    # -----------------------------------------------------
    # 필수 분석값 결측 제거
    # -----------------------------------------------------

    valid_mask = (
        apartment_df["자치구"].notna()
        & apartment_df["준공연도"].notna()
        & apartment_df["세대수"].notna()
        & (apartment_df["세대수"] > 0)
    )

    apartment_df = apartment_df[
        valid_mask
    ].copy()

    valid_row_count = len(
        apartment_df
    )

    removed_row_count = (
        original_row_count
        - valid_row_count
    )

    apartment_df["준공연도"] = (
        apartment_df["준공연도"]
        .astype(int)
    )

    # -----------------------------------------------------
    # 컨소시엄 분리
    # -----------------------------------------------------

    apartment_df["시공사목록"] = (
        apartment_df["기업그룹정리"]
        .apply(split_company_names)
    )

    apartment_df["컨소시엄수"] = (
        apartment_df["시공사목록"]
        .apply(
            lambda companies: max(
                len(companies),
                1,
            )
        )
    )

    # 예:
    # 300세대 단지를 삼성물산과 현대건설이 공동시공
    # → 삼성물산 150세대, 현대건설 150세대
    apartment_df["배분세대수"] = (
        apartment_df["세대수"]
        / apartment_df["컨소시엄수"]
    )

    company_df = (
        apartment_df
        .explode("시공사목록")
        .rename(
            columns={
                "시공사목록": "시공사"
            }
        )
        .copy()
    )

    quality_info = {
        "원본행수": original_row_count,
        "분석행수": valid_row_count,
        "제거행수": removed_row_count,
        "기타변환행수": other_count,
    }

    return (
        apartment_df,
        company_df,
        quality_info,
    )


# =========================================================
# 자치구별 점유율 계산
# =========================================================

def calculate_district_share(
    apartment_df: pd.DataFrame,
    company_df: pd.DataFrame,
    selected_company: str,
) -> pd.DataFrame:
    """
    점유율 계산식:

    시공사 공급 세대수
    ÷ 자치구 전체 분석 세대수
    × 100
    """

    # 분모:
    # 기타를 포함한 자치구 전체 아파트 세대수
    district_total = (
        apartment_df
        .groupby(
            "자치구",
            as_index=False,
        )["세대수"]
        .sum()
        .rename(
            columns={
                "세대수": "자치구전체세대수"
            }
        )
    )

    # 분자:
    # 기업그룹으로 확인된 시공사의 공급 세대수
    # 기타는 1위 경쟁에서 제외
    company_supply = (
        company_df[
            ~company_df["시공사"].isin(
                [
                    "기타",
                    "미상",
                ]
            )
        ]
        .groupby(
            [
                "자치구",
                "시공사",
            ],
            as_index=False,
        )["배분세대수"]
        .sum()
        .rename(
            columns={
                "배분세대수": "공급세대수"
            }
        )
    )

    if (
        selected_company
        == "구별 1위 시공사"
    ):
        result = (
            company_supply
            .sort_values(
                [
                    "자치구",
                    "공급세대수",
                ],
                ascending=[
                    True,
                    False,
                ],
            )
            .drop_duplicates(
                subset=["자치구"],
                keep="first",
            )
        )

        missing_company_name = (
            "자료 없음"
        )

    else:
        result = company_supply[
            company_supply["시공사"]
            == selected_company
        ].copy()

        missing_company_name = (
            selected_company
        )

    result = district_total.merge(
        result,
        on="자치구",
        how="left",
    )

    result["시공사"] = (
        result["시공사"]
        .fillna(
            missing_company_name
        )
    )

    result["공급세대수"] = (
        result["공급세대수"]
        .fillna(0)
    )

    result["점유율"] = (
        result["공급세대수"]
        / result["자치구전체세대수"]
        * 100
    ).fillna(0)

    return result


# =========================================================
# Folium 지도 생성
# =========================================================

def create_territory_map(
    boundary: gpd.GeoDataFrame,
    district_share: pd.DataFrame,
) -> folium.Map:
    """
    서울 25개 자치구의 시공사 점유율 지도를 생성합니다.
    """

    map_data = boundary.merge(
        district_share,
        on="자치구",
        how="left",
    )

    map_data["시공사"] = (
        map_data["시공사"]
        .fillna("자료 없음")
    )

    numeric_columns = [
        "공급세대수",
        "자치구전체세대수",
        "점유율",
    ]

    for column in numeric_columns:
        map_data[column] = pd.to_numeric(
            map_data[column],
            errors="coerce",
        ).fillna(0)

    map_data["점유율"] = (
        map_data["점유율"]
        .round(1)
    )

    map_data["공급세대수"] = (
        map_data["공급세대수"]
        .round(0)
    )

    map_data["자치구전체세대수"] = (
        map_data["자치구전체세대수"]
        .round(0)
    )

    observed_maximum = float(
        map_data["점유율"].max()
    )

    scale_maximum = max(
        10,
        math.ceil(
            observed_maximum / 10
        ) * 10,
    )

    color_scale = LinearColormap(
        colors=[
            "#eff6ff",
            "#bfdbfe",
            "#60a5fa",
            "#2563eb",
            "#1e3a8a",
        ],
        vmin=0,
        vmax=scale_maximum,
        caption=(
            "자치구 내 공급 세대 점유율 (%)"
        ),
    )

    seoul_map = folium.Map(
        location=[
            37.5665,
            126.9780,
        ],
        zoom_start=10,
        tiles=None,
        control_scale=True,
        prefer_canvas=True,
    )

    # 주변 도로와 지명이 표시되는 기본 지도
    folium.TileLayer(
        tiles="OpenStreetMap",
        name="일반 지도",
        show=True,
        control=True,
    ).add_to(seoul_map)

    # 밝고 단순한 발표용 지도
    folium.TileLayer(
        tiles="CartoDB positron",
        name="밝은 지도",
        show=False,
        control=True,
    ).add_to(seoul_map)

    map_geojson = json.loads(
        map_data.to_json()
    )

    folium.GeoJson(
        data=map_geojson,
        name="시공사 점유율",
        style_function=lambda feature: {
            "fillColor": color_scale(
                feature["properties"]["점유율"]
            ),
            "color": "#475569",
            "weight": 1.3,
            "fillOpacity": 0.70,
        },
        highlight_function=lambda feature: {
            "color": "#111827",
            "weight": 3,
            "fillOpacity": 0.85,
        },
        tooltip=GeoJsonTooltip(
            fields=[
                "자치구",
                "시공사",
                "점유율",
                "공급세대수",
                "자치구전체세대수",
            ],
            aliases=[
                "자치구",
                "대표 시공사",
                "점유율",
                "시공사 공급 세대수",
                "자치구 전체 세대수",
            ],
            localize=True,
            sticky=False,
            labels=True,
        ),
    ).add_to(seoul_map)

    color_scale.add_to(
        seoul_map
    )

    # -----------------------------------------------------
    # 자치구 내부 라벨
    # -----------------------------------------------------

    projected_boundary = (
        map_data.to_crs(
            "EPSG:5179"
        )
    )

    label_points = (
        projected_boundary
        .representative_point()
        .to_crs("EPSG:4326")
    )

    for point, (_, row) in zip(
        label_points,
        map_data.iterrows(),
    ):
        district_name = html.escape(
            str(row["자치구"])
        )

        company_name = html.escape(
            str(row["시공사"])
        )

        share = float(
            row["점유율"]
        )

        label_html = f"""
        <div style="
            transform: translate(-50%, -50%);
            min-width: 76px;
            padding: 4px 6px;
            border: 1px solid rgba(51, 65, 85, 0.35);
            border-radius: 6px;
            background: rgba(255, 255, 255, 0.90);
            color: #172033;
            text-align: center;
            font-family: Arial, sans-serif;
            font-size: 10px;
            line-height: 1.35;
            white-space: nowrap;
            pointer-events: none;
        ">
            <strong>{district_name}</strong><br>
            {company_name}<br>
            <span style="
                color: #1d4ed8;
                font-size: 12px;
                font-weight: 700;
            ">
                {share:.1f}%
            </span>
        </div>
        """

        folium.Marker(
            location=[
                point.y,
                point.x,
            ],
            icon=DivIcon(
                icon_size=(0, 0),
                icon_anchor=(0, 0),
                html=label_html,
            ),
        ).add_to(
            seoul_map
        )

    # 서울 전체를 첫 화면에 표시
    min_x, min_y, max_x, max_y = (
        map_data.total_bounds
    )

    seoul_map.fit_bounds(
        [
            [
                min_y,
                min_x,
            ],
            [
                max_y,
                max_x,
            ],
        ],
        padding=(
            15,
            15,
        ),
    )

    folium.LayerControl(
        collapsed=True,
    ).add_to(
        seoul_map
    )

    return seoul_map


# =========================================================
# 축 A Streamlit 화면
# =========================================================

def render_axis_a():
    st.markdown(
        """
        <h1 class="main-title">
            기존 아파트 시공사 영토
        </h1>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="main-description">
            준공 아파트의 공급 세대수를 기준으로
            서울 자치구별 시공사 점유율을 비교합니다.
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not DATA_PATH.exists():
        st.error(
            "`data/서울시_공동주택_1차전처리.csv` "
            "파일을 찾을 수 없습니다."
        )
        return

    try:
        raw_df = load_apartment_data(
            DATA_PATH.read_bytes()
        )

        (
            apartment_df,
            company_df,
            quality_info,
        ) = prepare_apartment_data(
            raw_df
        )

        boundary = (
            load_seoul_boundary()
        )

    except Exception as error:
        st.error(
            "데이터 처리 중 오류가 발생했습니다: "
            f"{error}"
        )
        return

    minimum_year = int(
        apartment_df["준공연도"]
        .min()
    )

    maximum_year = int(
        apartment_df["준공연도"]
        .max()
    )

    # 기타는 분모에는 포함되지만
    # 시공사 선택 목록에서는 제외
    company_ranking = (
        company_df[
            ~company_df["시공사"].isin(
                [
                    "기타",
                    "미상",
                ]
            )
        ]
        .groupby(
            "시공사"
        )["배분세대수"]
        .sum()
        .sort_values(
            ascending=False
        )
    )

    company_options = (
        company_ranking
        .index
        .tolist()
    )

    # -----------------------------------------------------
    # 사이드바 필터
    # -----------------------------------------------------

    with st.sidebar:
        st.divider()

        st.subheader(
            "축 A 필터"
        )

        analysis_mode = st.radio(
            "시간 분석 방식",
            options=[
                "누적 영토",
                "기간 공급",
            ],
            help=(
                "누적 영토는 기준연도까지 준공된 "
                "모든 단지를 계산합니다. "
                "기간 공급은 선택한 기간에 준공된 "
                "단지만 계산합니다."
            ),
        )

        if analysis_mode == "누적 영토":
            selected_year = st.slider(
                "기준연도",
                min_value=minimum_year,
                max_value=maximum_year,
                value=maximum_year,
            )

            filtered_apartments = (
                apartment_df[
                    apartment_df["준공연도"]
                    <= selected_year
                ]
                .copy()
            )

            filtered_companies = (
                company_df[
                    company_df["준공연도"]
                    <= selected_year
                ]
                .copy()
            )

            period_label = (
                f"{selected_year}년까지 누적"
            )

        else:
            default_start_year = max(
                minimum_year,
                min(
                    2000,
                    maximum_year,
                ),
            )

            selected_period = st.slider(
                "준공연도 범위",
                min_value=minimum_year,
                max_value=maximum_year,
                value=(
                    default_start_year,
                    maximum_year,
                ),
            )

            start_year, end_year = (
                selected_period
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
                .copy()
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
                .copy()
            )

            period_label = (
                f"{start_year}~{end_year}년 공급"
            )

        selected_company = st.selectbox(
            "시공사",
            options=[
                "구별 1위 시공사"
            ] + company_options,
        )

    if filtered_apartments.empty:
        st.warning(
            "선택한 기간에 해당하는 "
            "아파트가 없습니다."
        )
        return

    # -----------------------------------------------------
    # 점유율 계산
    # -----------------------------------------------------

    district_share = (
        calculate_district_share(
            filtered_apartments,
            filtered_companies,
            selected_company,
        )
    )

    total_complexes = len(
        filtered_apartments
    )

    total_households = float(
        filtered_apartments[
            "세대수"
        ].sum()
    )

    consortium_complexes = int(
        (
            filtered_apartments[
                "컨소시엄수"
            ] > 1
        ).sum()
    )

    metric_1, metric_2, metric_3 = (
        st.columns(3)
    )

    metric_1.metric(
        "분석 단지",
        f"{total_complexes:,}개",
        period_label,
    )

    metric_2.metric(
        "분석 세대수",
        f"{total_households:,.0f}세대",
        "세대수 가중치 적용",
    )

    metric_3.metric(
        "컨소시엄 단지",
        f"{consortium_complexes:,}개",
        "참여 시공사별 1/n",
    )

    st.caption(
        f"원본 {quality_info['원본행수']:,}행 중 "
        f"{quality_info['분석행수']:,}행을 분석에 사용했습니다. "
        f"필수값 결측 {quality_info['제거행수']:,}행은 제거하고, "
        f"기업그룹 결측 {quality_info['기타변환행수']:,}행은 "
        f"'기타'로 분류했습니다."
    )

    if (
        selected_company
        == "구별 1위 시공사"
    ):
        st.subheader(
            "자치구별 1위 시공사"
        )

        st.caption(
            "각 자치구에서 공급 세대수가 "
            "가장 많은 시공사와 자치구 내 "
            "세대수 점유율을 표시합니다."
        )

    else:
        st.subheader(
            f"{selected_company} 자치구별 점유율"
        )

        st.caption(
            f"자치구 전체 분석 세대 중 "
            f"{selected_company}이 공급한 "
            "세대의 비율입니다."
        )

    # -----------------------------------------------------
    # 지도 출력
    # -----------------------------------------------------

    territory_map = (
        create_territory_map(
            boundary,
            district_share,
        )
    )

    st_folium(
        territory_map,
        height=760,
        use_container_width=True,
        returned_objects=[],
        key="axis_a_territory_map",
    )

    # -----------------------------------------------------
    # 계산 결과 표
    # -----------------------------------------------------

    with st.expander(
        "자치구별 계산 결과 확인"
    ):
        result_table = (
            district_share[
                [
                    "자치구",
                    "시공사",
                    "공급세대수",
                    "자치구전체세대수",
                    "점유율",
                ]
            ]
            .sort_values(
                "점유율",
                ascending=False,
            )
            .reset_index(
                drop=True
            )
        )

        result_table = (
            result_table.rename(
                columns={
                    "공급세대수": (
                        "시공사 공급세대수"
                    ),
                    "자치구전체세대수": (
                        "자치구 전체세대수"
                    ),
                    "점유율": (
                        "세대수 점유율(%)"
                    ),
                }
            )
        )

        st.dataframe(
            result_table,
            use_container_width=True,
            hide_index=True,
        )

    st.caption(
        "'기타' 세대는 자치구 전체 세대수인 분모에는 "
        "포함되지만, 1위 시공사 선정과 시공사 선택 목록에서는 "
        "제외됩니다."
    )
