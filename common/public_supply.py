"""1번 탭: 아파트 공급주체 구성·지역분포에 쓰는 집계 함수."""

import pandas as pd


SUPPLY_SUBJECT_ORDER = ["공공", "민간", "조합", "공공·민간 공동 시행", "공공·조합 공동 시행"]

SUBJECT_COLORS = {
    "공공": "#2F6B9A",
    "민간": "#7A8794",
    "조합": "#D98B35",
    "공공·민간 공동 시행": "#5A9C78",
    "공공·조합 공동 시행": "#8A6FAE",
}


def prepare_supply_subject_data(apartment: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """분석용 다섯 주체로 재분류하고, 미상·확인필요는 분모에서 분리한다."""
    data = apartment.copy()
    mapping = {
        "공공": "공공",
        "기타공공": "공공",
        "민간": "민간",
        "조합": "조합",
        "공공·민간 공동": "공공·민간 공동 시행",
        "공공·조합 공동": "공공·조합 공동 시행",
    }
    data["공급주체"] = data["시행주체 구분"].map(mapping)
    classified = data.loc[data["공급주체"].notna()].copy()
    excluded = data.loc[data["공급주체"].isna()].copy()
    return classified, excluded


def _contribution_index(summary: pd.DataFrame) -> pd.DataFrame:
    """세대수 70%, 동수 30%로 공급 기여도를 보정한다."""
    result = summary.copy()
    household_total = result["세대수"].sum()
    building_total = result["동수"].sum()
    result["세대수 비중(%)"] = (result["세대수"] / household_total * 100).fillna(0)
    result["동수 비중(%)"] = (result["동수"] / building_total * 100).fillna(0)
    result["보정 공급 기여지수(%)"] = (
        result["세대수 비중(%)"] * 0.7 + result["동수 비중(%)"] * 0.3
    )
    return result


def summarize_supply_subjects(classified: pd.DataFrame) -> pd.DataFrame:
    """서울 전체에서 공급주체별 보정 기여지수를 계산한다."""
    summary = (
        classified.groupby("공급주체", as_index=False)
        .agg(단지수=("k-아파트명", "size"), 세대수=("세대수", "sum"), 동수=("동수", "sum"))
        .set_index("공급주체")
        .reindex(SUPPLY_SUBJECT_ORDER, fill_value=0)
        .rename_axis("공급주체")
        .reset_index()
    )
    return _contribution_index(summary)


def summarize_subject_by_district(classified: pd.DataFrame, subject: str) -> pd.DataFrame:
    """선택한 주체가 자치구 내부 공급에서 차지하는 보정 비율을 계산한다."""
    total = (
        classified.groupby("시군구", as_index=False)
        .agg(전체_단지수=("k-아파트명", "size"), 전체_세대수=("세대수", "sum"), 전체_동수=("동수", "sum"))
    )
    selected = (
        classified.loc[classified["공급주체"].eq(subject)]
        .groupby("시군구", as_index=False)
        .agg(선택_단지수=("k-아파트명", "size"), 선택_세대수=("세대수", "sum"), 선택_동수=("동수", "sum"))
    )
    result = total.merge(selected, on="시군구", how="left").fillna(0)
    for column in ["선택_단지수", "선택_세대수", "선택_동수"]:
        result[column] = result[column].astype(int)
    result["세대수 비중(%)"] = result["선택_세대수"] / result["전체_세대수"] * 100
    result["동수 비중(%)"] = result["선택_동수"] / result["전체_동수"] * 100
    result["보정 공급 기여지수(%)"] = result["세대수 비중(%)"] * 0.7 + result["동수 비중(%)"] * 0.3
    return result.sort_values("보정 공급 기여지수(%)", ascending=False)
