from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
PROCESSED_DIR = DATA_DIR / "processed"
REFERENCE_DIR = DATA_DIR / "reference"
SPATIAL_DIR = DATA_DIR / "spatial"
ASSETS_DIR = PROJECT_ROOT / "assets"

# 파일명은 전처리 산출물의 실제 이름을 그대로 사용한다.
APARTMENT_DATA_PATH = PROCESSED_DIR / "서울시_공동주택_2차전처리_엑셀좌표반영본.csv"
RANKING_DATA_PATH = PROCESSED_DIR / "시공능력평가_분석용_연도별_전체업종_최종.xlsx"
COMPANY_ALIAS_MAP_PATH = REFERENCE_DIR / "company_alias_map.csv"
# 1번 탭은 자치구 경계를 사용한다. 파일명은 GitHub에 올린 이름과 일치해야 한다.
SEOUL_GU_GEOJSON_PATH = SPATIAL_DIR / "시군구경계.geojson"
SEOUL_ADM_DONG_GEOJSON_PATH = SPATIAL_DIR / "서울시행정동.geojson"

SEOUL_CENTER = {"lat": 37.5665, "lon": 126.9780, "zoom": 11}
SEOUL_BOUNDS = {"min_lon": 126.60, "max_lon": 127.30, "min_lat": 37.30, "max_lat": 38.00}

PUBLIC_DEVELOPER_TYPES = ("공공", "기타공공", "공공·조합 공동", "공공·민간 공동")
