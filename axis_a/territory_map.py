from pathlib import Path
import io

import pandas as pd
import streamlit as st


DATA_PATH = Path("data/서울시_공동주택_1차전처리.csv")


@st.cache_data(show_spinner=False)
def load_apartment_data(file_bytes: bytes) -> pd.DataFrame:
    """
    UTF-8 또는 CP949 형식의 CSV를 자동으로 불러옵니다.
    """

    encoding_list = [
        "utf-8-sig",
        "cp949",
        "utf-8",
    ]

    last_error = None

    for encoding in encoding_list:
        try:
            return pd.read_csv(
                io.BytesIO(file_bytes),
                encoding=encoding,
                low_memory=False,
            )

        except UnicodeDecodeError as error:
            last_error = error

    raise ValueError(
        "CSV 파일의 한글 인코딩을 확인할 수 없습니다."
    ) from last_error


def render_axis_a():
    """
    축 A: 기존 아파트 시공사 영토지도
    """

    st.markdown(
        '<h1 class="main-title">기존 아파트 시공사 영토</h1>',
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="main-description">
            준공된 아파트의 세대수와 시공사를 기준으로
            서울 자치구별 시공사 점유율을 분석합니다.
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not DATA_PATH.exists():
        st.error(
            "데이터 파일을 찾을 수 없습니다. "
            "`data/서울시_공동주택_1차전처리.csv` 경로를 확인해주세요."
        )
        return

    try:
        apartment_df = load_apartment_data(
            DATA_PATH.read_bytes()
        )

    except Exception as error:
        st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {error}")
        return

    total_complexes = len(apartment_df)

    if "k-전체세대수" in apartment_df.columns:
        household_series = pd.to_numeric(
            apartment_df["k-전체세대수"]
            .astype(str)
            .str.replace(",", "", regex=False),
            errors="coerce",
        )

        total_households = household_series.sum()

    else:
        total_households = 0

    if "주소(시군구)" in apartment_df.columns:
        total_districts = (
            apartment_df["주소(시군구)"]
            .dropna()
            .nunique()
        )

    else:
        total_districts = 0

    metric_1, metric_2, metric_3 = st.columns(3)

    metric_1.metric(
        "전체 단지",
        f"{total_complexes:,}개",
    )

    metric_2.metric(
        "전체 세대수",
        f"{total_households:,.0f}세대",
    )

    metric_3.metric(
        "확인된 자치구",
        f"{total_districts:,}개",
    )

    st.subheader("데이터 미리보기")

    st.dataframe(
        apartment_df.head(20),
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("CSV 열 이름 확인"):
        st.write(apartment_df.columns.tolist())

    st.info(
        "데이터가 정상적으로 표시되면 다음 단계에서 "
        "이 화면을 자치구별 Folium 점유율 지도로 교체합니다."
    )
