"""시공능력평가와 서울 공동주택 시공사를 연결하는 데이터 함수."""

import re
from pathlib import Path

import pandas as pd
import streamlit as st

from common.config import COMPANY_ALIAS_MAP_PATH, RANKING_DATA_PATH


# 공동주택 원자료의 '시공사' 열에 시행·공급기관이 잘못 기입된 사례는
# 시공사 점유율 분석에서 제외한다. 실제 시공사 정보가 확인되지 않았다는 뜻이다.
NON_CONTRACTOR_DEVELOPER_KEYS = {
    "LH", "LH공사", "한국토지주택공사", "대한주택공사",
    "SH", "SH공사", "서울주택도시공사", "서울특별시도시개발공사",
}


def _is_non_contractor_developer(value) -> bool:
    return _compact_name(value) in {_compact_name(item) for item in NON_CONTRACTOR_DEVELOPER_KEYS}


def _compact_name(value) -> str:
    text = "" if pd.isna(value) else str(value)
    text = text.replace("(주)", "").replace("㈜", "").replace("주식회사", "")
    return re.sub(r"[^0-9A-Za-z가-힣]", "", text).upper()


@st.cache_data(show_spinner=False)
def load_company_aliases(path: str = str(COMPANY_ALIAS_MAP_PATH)) -> pd.DataFrame:
    aliases = pd.read_csv(Path(path), encoding="utf-8-sig")
    aliases = aliases.loc[aliases["source_scope"].isin(["apartment", "rank", "both"])].copy()
    aliases["정규화별칭"] = aliases["alias_name"].map(_compact_name)
    return aliases


def normalize_company_name(value, aliases: pd.DataFrame) -> str:
    """괄호·주식회사 표기 차이를 제거한 뒤 별칭표의 법인명으로 연결한다."""
    compact = _compact_name(value)
    if not compact:
        return "미상"

    apartment_group_map = {
        "아이파크현대산업개발HDC": "HDC현대산업개발",
        "한화": "한화 건설부문",
        "두산에너빌리티": "두산에너빌리티",
    }
    if compact in apartment_group_map:
        return apartment_group_map[compact]

    matches = aliases.loc[aliases["정규화별칭"].eq(compact)]
    if not matches.empty:
        return str(matches.iloc[0]["company_entity_name"])
    return str(value).strip()


@st.cache_data(show_spinner="시공능력평가 데이터를 불러오는 중입니다...")
def load_ranking_data(path: str = str(RANKING_DATA_PATH)) -> pd.DataFrame:
    ranking_path = Path(path)
    if not ranking_path.exists():
        raise FileNotFoundError(f"시공능력평가 파일을 찾을 수 없습니다: {ranking_path.name}")

    ranking = pd.read_excel(ranking_path, sheet_name="01_분석용_롱데이터")
    required = {"평가연도", "업종코드", "순위", "회사명_비교키", "시공능력평가액_백만원"}
    missing = required - set(ranking.columns)
    if missing:
        raise ValueError(f"시공능력평가 파일의 필수 열이 없습니다: {', '.join(sorted(missing))}")

    aliases = load_company_aliases()
    ranking = ranking.copy()
    ranking["평가연도"] = pd.to_numeric(ranking["평가연도"], errors="coerce")
    ranking["순위"] = pd.to_numeric(ranking["순위"], errors="coerce")
    ranking["시공능력평가액_백만원"] = pd.to_numeric(
        ranking["시공능력평가액_백만원"], errors="coerce"
    )
    ranking = ranking.dropna(subset=["평가연도", "순위", "시공능력평가액_백만원"]).copy()
    ranking["평가연도"] = ranking["평가연도"].astype(int)
    ranking["순위"] = ranking["순위"].astype(int)
    ranking["시공사"] = ranking["회사명_비교키"].map(
        lambda value: normalize_company_name(value, aliases)
    )
    return ranking


def get_top20_companies(ranking: pd.DataFrame, industry: str, base_year: int) -> list[str]:
    selected = ranking.loc[
        ranking["업종코드"].eq(industry) & ranking["평가연도"].eq(base_year) & ranking["순위"].le(20)
    ]
    selected = (
        selected.groupby("시공사", as_index=False)["순위"]
        .min()
        .sort_values("순위")
    )
    return selected["시공사"].tolist()


def prepare_apartment_contractors(apartment: pd.DataFrame) -> pd.DataFrame:
    """공동시공은 참여사 수로 세대수와 동수를 균등 배분한다."""
    aliases = load_company_aliases()
    data = apartment.copy()
    group_name = data.get("기업그룹", pd.Series(index=data.index, dtype="object"))
    raw_name = data["k-건설사(시공사)"].fillna("미상")
    data["시공사_원천"] = group_name.fillna("").astype(str).str.strip()
    data.loc[data["시공사_원천"].isin(["", "nan", "None"]), "시공사_원천"] = raw_name

    data["참여시공사"] = data["시공사_원천"].astype(str).str.split(";")
    data["참여사수"] = data["참여시공사"].str.len().clip(lower=1)
    expanded = data.explode("참여시공사").copy()
    # LH·SH 등 시행·공급기관이 시공사 열에 들어간 오기재는 분석 대상에서 제외한다.
    expanded = expanded.loc[
        ~expanded["참여시공사"].map(_is_non_contractor_developer)
    ].copy()
    expanded["시공사"] = expanded["참여시공사"].map(
        lambda value: normalize_company_name(value, aliases)
    )
    expanded = expanded.loc[
        ~expanded["시공사"].map(_is_non_contractor_developer)
        & expanded["시공사"].ne("미상")
    ].copy()
    expanded["배분세대수"] = expanded["세대수"] / expanded["참여사수"]
    expanded["배분동수"] = expanded["동수"] / expanded["참여사수"]
    expanded["배분단지수"] = 1 / expanded["참여사수"]
    return expanded


def summarize_contractor_share(
    expanded: pd.DataFrame,
    candidate_companies: list[str],
    start_year: int,
    end_year: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """전체 시공 물량을 분모로, Top20 후보사의 자치구별 보정 점유율을 계산한다."""
    period = expanded.loc[expanded["사용승인연도"].between(start_year, end_year)].copy()
    period = period.loc[period["시군구"].ne("미상")]
    totals = (
        period.groupby("시군구", as_index=False)
        .agg(전체세대수=("배분세대수", "sum"), 전체동수=("배분동수", "sum"))
    )
    all_by_company = (
        period.groupby(["시군구", "시공사"], as_index=False)
        .agg(단지수=("배분단지수", "sum"), 세대수=("배분세대수", "sum"), 동수=("배분동수", "sum"))
        .merge(totals, on="시군구", how="left")
    )
    all_by_company["세대수 비중(%)"] = all_by_company["세대수"] / all_by_company["전체세대수"] * 100
    all_by_company["동수 비중(%)"] = all_by_company["동수"] / all_by_company["전체동수"] * 100
    all_by_company["보정 시공 점유율(%)"] = (
        all_by_company["세대수 비중(%)"] * 0.7 + all_by_company["동수 비중(%)"] * 0.3
    )
    by_company = all_by_company.loc[all_by_company["시공사"].isin(candidate_companies)].copy()
    leaders = (
        by_company.loc[
            by_company.groupby("시군구")["보정 시공 점유율(%)"].idxmax(),
            ["시군구", "시공사", "보정 시공 점유율(%)", "단지수", "세대수", "동수"],
        ]
        .rename(
            columns={
                "시공사": "1위 시공사",
                "보정 시공 점유율(%)": "1위 보정 점유율(%)",
                "단지수": "1위 단지수",
                "세대수": "1위 세대수",
                "동수": "1위 동수",
            }
        )
    )
    return by_company, leaders, all_by_company
