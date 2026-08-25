import io

import pandas as pd
import streamlit as st

from .config import DATA_PATH


@st.cache_data(show_spinner=False)
def load_apartment_data() -> pd.DataFrame:
    """
    data 폴더의 아파트 CSV를 읽습니다.
    UTF-8과 CP949 인코딩을 모두 확인합니다.
    """

    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"데이터 파일을 찾을 수 없습니다: {DATA_PATH}"
        )

    file_bytes = DATA_PATH.read_bytes()

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
