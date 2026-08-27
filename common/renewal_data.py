"""정비사업 추진현황과 시공사 선정 근거를 안전하게 연결하는 데이터 함수."""

import json
import re
from pathlib import Path

import pandas as pd
import shapefile
import streamlit as st
from pyproj import Transformer

from common.config import RENEWAL_AREA_SHP_PATH, RENEWAL_EVIDENCE_PATH, RENEWAL_PROJECTS_PATH


EVIDENCE_COLUMNS = [
    "evidence_id", "정비사업_매칭키", "사업명_원문", "자치구", "시공사_표준화", "브랜드명",
    "선정상태", "선정일", "근거유형", "근거등급", "원문제목", "원문URL", "DART_접수번호",
    "확인일", "검증상태", "비고",
]


def project_name_key(value) -> str:
    """명칭이 완전히 같은 경우에만 연결하기 위한 보수적 비교키."""
    text = "" if pd.isna(value) else str(value)
    text = re.sub(r"[\s·ㆍ_()\[\]{}.,-]", "", text)
    return text.replace("정비구역", "").replace("정비사업", "").upper()


@st.cache_data(show_spinner="정비사업 추진현황을 불러오는 중입니다...")
def load_renewal_projects(path: str = str(RENEWAL_PROJECTS_PATH)) -> pd.DataFrame:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"정비사업 추진현황 파일을 찾을 수 없습니다: {source.name}")
    projects = pd.read_csv(source, encoding="utf-8-sig")
    required = {"정비사업_매칭키", "자치구", "구역명", "공공민간", "사업유형", "추진단계", "공급세대수_합계"}
    missing = required - set(projects.columns)
    if missing:
        raise ValueError(f"정비사업 추진현황의 필수 열이 없습니다: {', '.join(sorted(missing))}")
    projects = projects.copy()
    projects["구역명"] = projects["구역명"].fillna("").astype(str).str.strip()
    projects["구역명_비교키"] = projects["구역명"].map(project_name_key)
    projects["공급세대수_합계"] = pd.to_numeric(projects["공급세대수_합계"], errors="coerce").fillna(0)
    return projects


@st.cache_data(show_spinner=False)
def load_renewal_evidence(path: str = str(RENEWAL_EVIDENCE_PATH)) -> pd.DataFrame:
    source = Path(path)
    if not source.exists():
        return pd.DataFrame(columns=EVIDENCE_COLUMNS)
    evidence = pd.read_csv(source, encoding="utf-8-sig")
    missing = set(EVIDENCE_COLUMNS) - set(evidence.columns)
    if missing:
        raise ValueError(f"시공사 선정 근거 파일의 필수 열이 없습니다: {', '.join(sorted(missing))}")
    evidence = evidence.copy()
    for column in EVIDENCE_COLUMNS:
        evidence[column] = evidence[column].fillna("").astype(str).str.strip()
    return evidence


def _transform_coordinates(coordinates, transformer: Transformer):
    if coordinates and isinstance(coordinates[0], (int, float)):
        longitude, latitude = transformer.transform(coordinates[0], coordinates[1])
        return [longitude, latitude]
    return [_transform_coordinates(item, transformer) for item in coordinates]


def _json_safe_value(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


@st.cache_data(show_spinner="의제처리구역 도형을 불러오는 중입니다...")
def load_renewal_areas(path: str = str(RENEWAL_AREA_SHP_PATH)) -> dict:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"의제처리구역 공간파일을 찾을 수 없습니다: {source.name}")
    reader = shapefile.Reader(str(source), encoding="cp949")
    field_names = [field[0] for field in reader.fields[1:]]
    transformer = Transformer.from_crs("EPSG:5174", "EPSG:4326", always_xy=True)
    features = []
    for item in reader.iterShapeRecords():
        geometry = item.shape.__geo_interface__
        geometry["coordinates"] = _transform_coordinates(geometry["coordinates"], transformer)
        properties = {
            field: _json_safe_value(value)
            for field, value in zip(field_names, item.record)
        }
        features.append({"type": "Feature", "geometry": geometry, "properties": properties})
    return {"type": "FeatureCollection", "features": features}


def selected_evidence(evidence: pd.DataFrame) -> pd.DataFrame:
    return evidence.loc[
        evidence["선정상태"].eq("시공사 선정") & evidence["검증상태"].eq("검증완료")
    ].copy()

