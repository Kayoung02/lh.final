from pathlib import Path

import pandas as pd
import streamlit as st

from common.config import APARTMENT_DATA_PATH, PUBLIC_DEVELOPER_TYPES, SEOUL_BOUNDS


REQUIRED_APARTMENT_COLUMNS = {
    "k-아파트명",
    "주소(시군구)",
    "주소(읍면동)",
    "k-전체동수",
    "k-전체세대수",
    "k-시행사",
    "k-사용검사일-사용승인일",
    "시행사_표준화",
    "시행주체 구분",
    "좌표X_분석용",
    "좌표Y_분석용",
}


def _district_from_address(series: pd.Series) -> pd.Series:
    """주소에서 서울 자치구만 추출한다. 추출 실패는 원문을 억지로 추정하지 않는다."""
    return series.fillna("").astype(str).str.extract(r"([가-힣]+구)", expand=False).fillna("미상")


@st.cache_data(show_spinner="공동주택 데이터를 불러오는 중입니다...")
def load_apartment_data(path: str = str(APARTMENT_DATA_PATH)) -> pd.DataFrame:
    data_path = Path(path)
    if not data_path.exists():
        raise FileNotFoundError(f"공동주택 파일을 찾을 수 없습니다: {data_path.name}")

    apartment = pd.read_csv(data_path, encoding="utf-8-sig")
    missing = REQUIRED_APARTMENT_COLUMNS - set(apartment.columns)
    if missing:
        raise ValueError(f"필수 열이 없습니다: {', '.join(sorted(missing))}")

    apartment = apartment.copy()
    apartment["시군구"] = _district_from_address(apartment["주소(시군구)"])
    apartment["행정동"] = apartment["주소(읍면동)"].fillna("미상").astype(str).str.strip().replace("", "미상")
    apartment["세대수"] = pd.to_numeric(apartment["k-전체세대수"], errors="coerce").fillna(0).astype(int)
    apartment["동수"] = pd.to_numeric(apartment["k-전체동수"], errors="coerce").fillna(0).astype(int)
    apartment["경도"] = pd.to_numeric(apartment["좌표X_분석용"], errors="coerce")
    apartment["위도"] = pd.to_numeric(apartment["좌표Y_분석용"], errors="coerce")
    apartment["사용승인연도"] = pd.to_datetime(
        apartment.get("k-사용검사일-사용승인일"), errors="coerce"
    ).dt.year
    apartment["시행사_표시"] = apartment["시행사_표준화"].fillna("").astype(str).str.strip()
    apartment.loc[apartment["시행사_표시"].eq(""), "시행사_표시"] = apartment["k-시행사"].fillna("미상")
    apartment["공공시행여부"] = apartment["시행주체 구분"].isin(PUBLIC_DEVELOPER_TYPES)
    apartment["좌표유효"] = (
        apartment["경도"].between(SEOUL_BOUNDS["min_lon"], SEOUL_BOUNDS["max_lon"])
        & apartment["위도"].between(SEOUL_BOUNDS["min_lat"], SEOUL_BOUNDS["max_lat"])
    )
    return apartment

