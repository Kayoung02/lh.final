from pathlib import Path


DATA_PATH = Path(
    "data/서울시_공동주택_1차전처리.csv"
)

BOUNDARY_PATH = Path(
    "data/seoul_gu.geojson"
)

BOUNDARY_URL = (
    "https://raw.githubusercontent.com/"
    "southkorea/seoul-maps/master/kostat/2013/json/"
    "seoul_municipalities_geo_simple.json"
)

EXCLUDED_COMPANIES = [
    "기타",
    "미상",
]
