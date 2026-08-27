"""OpenDART 공시에서 정비사업 시공사 선정 관련 검토 후보를 찾는 함수."""

import io
import html
import re
import zipfile
import xml.etree.ElementTree as etree
from datetime import date

import pandas as pd
import requests
import streamlit as st


DART_API = "https://opendart.fss.or.kr/api"
REPORT_KEYWORDS = ("단일판매", "공급계약", "공사수주", "도급계약", "재개발", "재건축", "정비사업", "시공사")
NAME_OVERRIDES = {
    "한화 건설부문": ("한화", "한화건설"),
    "DL이앤씨": ("DL이앤씨", "대림산업"),
    "포스코이앤씨": ("포스코이앤씨", "포스코건설"),
    "SK에코플랜트": ("SK에코플랜트", "SK건설"),
    "HDC현대산업개발": ("HDC현대산업개발", "현대산업개발"),
    "HJ중공업": ("HJ중공업", "한진중공업"),
    "BS한양": ("BS한양", "한양"),
}


def _compact(value) -> str:
    text = "" if pd.isna(value) else str(value)
    return "".join(char for char in text.upper() if char.isalnum())


def get_dart_api_key() -> str | None:
    try:
        value = str(st.secrets["DART_API_KEY"]).strip()
        return value or None
    except (KeyError, FileNotFoundError):
        return None


@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
def _corp_codes(api_key: str) -> pd.DataFrame:
    response = requests.get(f"{DART_API}/corpCode.xml", params={"crtfc_key": api_key}, timeout=30)
    response.raise_for_status()
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    xml_name = next(name for name in archive.namelist() if name.lower().endswith(".xml"))
    root = etree.fromstring(archive.read(xml_name))
    rows = []
    for item in root.findall("list"):
        rows.append(
            {
                "corp_code": item.findtext("corp_code", default=""),
                "corp_name": item.findtext("corp_name", default=""),
                "stock_code": item.findtext("stock_code", default=""),
            }
        )
    codes = pd.DataFrame(rows)
    codes["비교키"] = codes["corp_name"].map(_compact)
    return codes


def company_corp_codes(api_key: str, companies: list[str]) -> tuple[dict[str, str], list[str]]:
    codes = _corp_codes(api_key)
    lookup = codes.drop_duplicates("비교키").set_index("비교키")["corp_code"].to_dict()
    matched, unmatched = {}, []
    for company in companies:
        names = (company,) + NAME_OVERRIDES.get(company, ())
        code = next((lookup.get(_compact(name)) for name in names if lookup.get(_compact(name))), None)
        if code:
            matched[company] = code
        else:
            unmatched.append(company)
    return matched, unmatched


@st.cache_data(ttl=60 * 60, show_spinner=False)
def collect_dart_candidates(
    api_key: str,
    company_codes: dict[str, str],
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    rows = []
    for company, corp_code in company_codes.items():
        response = requests.get(
            f"{DART_API}/list.json",
            params={
                "crtfc_key": api_key,
                "corp_code": corp_code,
                "bgn_de": start_date.replace("-", ""),
                "end_de": end_date.replace("-", ""),
                "page_count": 100,
                "sort": "date",
                "sort_mth": "desc",
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") == "013":
            continue
        if payload.get("status") != "000":
            raise ValueError(f"{company}: DART 조회 오류 ({payload.get('message', '알 수 없음')})")
        for item in payload.get("list", []):
            report_name = item.get("report_nm", "")
            if not any(keyword in report_name for keyword in REPORT_KEYWORDS):
                continue
            receipt_no = item.get("rcept_no", "")
            rows.append(
                {
                    "공시일": item.get("rcept_dt", ""),
                    "시공사_표준화": company,
                    "DART_회사명": item.get("corp_name", ""),
                    "공시제목": report_name,
                    "공시유형": item.get("pblntf_ty", ""),
                    "DART_접수번호": receipt_no,
                    "원문URL": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt_no}",
                    "판정": "검토 후보",
                }
            )
    return pd.DataFrame(rows).sort_values(["공시일", "시공사_표준화"], ascending=[False, True]) if rows else pd.DataFrame(
        columns=["공시일", "시공사_표준화", "DART_회사명", "공시제목", "공시유형", "DART_접수번호", "원문URL", "판정"]
    )


def _document_text(content: bytes) -> str:
    archive = zipfile.ZipFile(io.BytesIO(content))
    xml_files = [name for name in archive.namelist() if name.lower().endswith((".xml", ".html", ".htm"))]
    pieces = []
    for name in xml_files:
        raw = archive.read(name)
        try:
            decoded = raw.decode("utf-8")
        except UnicodeDecodeError:
            decoded = raw.decode("cp949", errors="ignore")
        pieces.append(re.sub(r"<[^>]+>", " ", decoded))
    return re.sub(r"\s+", " ", html.unescape(" ".join(pieces))).strip()


@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
def disclosure_contract_details(api_key: str, receipt_no: str) -> dict[str, str]:
    response = requests.get(
        f"{DART_API}/document.xml",
        params={"crtfc_key": api_key, "rcept_no": receipt_no},
        timeout=45,
    )
    response.raise_for_status()
    text = _document_text(response.content)

    def field(label_pattern: str, stop_pattern: str) -> str:
        match = re.search(
            rf"(?:{label_pattern})\\s*[:：]?\\s*(.+?)(?=(?:{stop_pattern})|$)",
            text,
            flags=re.IGNORECASE,
        )
        return match.group(1).strip(" -") if match else ""

    return {
        "계약명": field(
            r"계약명",
            r"계약상대(?:방)?|계약금액|최근매출액|매출액|계약시작일|계약종료일|계약기간|계약조건|유보기한|공사개요",
        ),
        "계약상대방": field(
            r"계약상대(?:방)?",
            r"계약금액|최근매출액|매출액|계약시작일|계약종료일|계약기간|계약조건|유보기한|공사개요",
        ),
        "공급지역": field(
            r"판매[ㆍ·]?공급지역",
            r"계약기간|계약조건|공사[\s]*개요|유보기한|기타",
        ),
        "공사개요": field(
            r"공사[\s]*개요",
            r"상기|공사도급계약서|※|주[\s]*요",
        ),
    }


def enrich_dart_candidates(api_key: str, candidates: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty:
        return candidates.copy()
    enriched = candidates.copy()
    details = enriched["DART_접수번호"].map(
        lambda receipt_no: disclosure_contract_details(api_key, receipt_no)
    )
    for column in ("계약명", "계약상대방", "공급지역", "공사개요"):
        enriched[column] = details.map(lambda item: item.get(column, ""))
    return enriched
