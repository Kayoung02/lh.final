import pandas as pd


def get_public_supply_data(apartment: pd.DataFrame) -> pd.DataFrame:
    """공공 단독 및 공공 공동 시행 단지만 남긴다."""
    return apartment.loc[apartment["공공시행여부"]].copy()


def summarize_by_district(public_supply: pd.DataFrame) -> pd.DataFrame:
    summary = (
        public_supply.groupby("시군구", as_index=False)
        .agg(단지수=("k-아파트명", "size"), 총세대수=("세대수", "sum"), 총동수=("동수", "sum"))
        .sort_values(["총세대수", "단지수"], ascending=False)
    )
    summary["세대수_비중(%)"] = (summary["총세대수"] / summary["총세대수"].sum() * 100).round(1)
    return summary


def summarize_by_agency(public_supply: pd.DataFrame) -> pd.DataFrame:
    summary = (
        public_supply.groupby("시행사_표시", as_index=False)
        .agg(단지수=("k-아파트명", "size"), 총세대수=("세대수", "sum"))
        .sort_values(["총세대수", "단지수"], ascending=False)
    )
    return summary.rename(columns={"시행사_표시": "시행사"})


def summarize_by_developer_type(public_supply: pd.DataFrame) -> pd.DataFrame:
    """시행주체 유형을 단지 수와 세대 수 기준으로 동시에 비교한다."""
    summary = (
        public_supply.groupby("시행주체 구분", as_index=False)
        .agg(단지수=("k-아파트명", "size"), 세대수=("세대수", "sum"), 동수=("동수", "sum"))
        .sort_values("세대수", ascending=False)
    )
    summary["단지수_비중(%)"] = (summary["단지수"] / summary["단지수"].sum() * 100).round(1)
    summary["세대수_비중(%)"] = (summary["세대수"] / summary["세대수"].sum() * 100).round(1)
    return summary


def summarize_public_share_by_district(apartment: pd.DataFrame, public_mode: str) -> pd.DataFrame:
    """자치구별 전체 아파트 대비 공공 시행 비율을 계산한다."""
    total = (
        apartment.groupby("시군구", as_index=False)
        .agg(전체_단지수=("k-아파트명", "size"), 전체_세대수=("세대수", "sum"))
    )
    subject_type = apartment["시행주체 구분"].astype(str)
    if public_mode == "공공 참여":
        public = apartment[subject_type.str.contains("공공", na=False)]
    else:
        public = apartment[subject_type.isin(["공공", "기타공공"])]

    public_summary = (
        public.groupby("시군구", as_index=False)
        .agg(공공_단지수=("k-아파트명", "size"), 공공_세대수=("세대수", "sum"))
    )
    summary = total.merge(public_summary, on="시군구", how="left").fillna(0)
    summary["공공_단지수"] = summary["공공_단지수"].astype(int)
    summary["공공_세대수"] = summary["공공_세대수"].astype(int)
    summary["공공_단지수_비율(%)"] = (summary["공공_단지수"] / summary["전체_단지수"] * 100).round(1)
    summary["공공_세대수_비율(%)"] = (summary["공공_세대수"] / summary["전체_세대수"] * 100).round(1)
    return summary.sort_values("공공_세대수_비율(%)", ascending=False)
