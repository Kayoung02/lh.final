"""Folium 지도 생성 함수."""

import json

import branca.colormap as cm
import folium
from folium.plugins import Fullscreen

from common.config import SEOUL_CENTER, SEOUL_GU_GEOJSON_PATH


GU_CODE_TO_NAME = {
    "11010": "종로구", "11020": "중구", "11030": "용산구", "11040": "성동구", "11050": "광진구",
    "11060": "동대문구", "11070": "중랑구", "11080": "성북구", "11090": "강북구", "11100": "도봉구",
    "11110": "노원구", "11120": "은평구", "11130": "서대문구", "11140": "마포구", "11150": "양천구",
    "11160": "강서구", "11170": "구로구", "11180": "금천구", "11190": "영등포구", "11200": "동작구",
    "11210": "관악구", "11220": "서초구", "11230": "강남구", "11240": "송파구", "11250": "강동구",
}


def _first_coordinate(coordinates):
    if isinstance(coordinates, (int, float)):
        return None
    if len(coordinates) >= 2 and isinstance(coordinates[0], (int, float)):
        return coordinates[0], coordinates[1]
    for item in coordinates:
        found = _first_coordinate(item)
        if found:
            return found
    return None


def _validate_wgs84(boundaries: dict) -> None:
    for feature in boundaries.get("features", []):
        coordinate = _first_coordinate(feature.get("geometry", {}).get("coordinates", []))
        if coordinate:
            longitude, latitude = coordinate
            if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
                raise ValueError(
                    "서울시자치구.geojson의 좌표가 경위도(EPSG:4326)가 아닙니다. "
                    "QGIS에서 '다른 이름으로 저장' 후 CRS를 EPSG:4326 - WGS 84로 지정해 다시 내보내세요."
                )
            return
    raise ValueError("서울시자치구.geojson에서 자치구 도형을 찾을 수 없습니다.")


def _district_name(properties: dict) -> str | None:
    for value in properties.values():
        text = str(value).strip()
        if text in GU_CODE_TO_NAME.values():
            return text
        digits = "".join(char for char in text if char.isdigit())
        if digits[:5] in GU_CODE_TO_NAME:
            return GU_CODE_TO_NAME[digits[:5]]
    return None


def build_supply_subject_choropleth(district_summary, subject: str):
    """자치구 경계에 선택 공급주체의 지역 내 보정 기여지수를 입힌다."""
    if not SEOUL_GU_GEOJSON_PATH.exists():
        raise FileNotFoundError(f"자치구 경계 파일을 찾을 수 없습니다: {SEOUL_GU_GEOJSON_PATH.name}")

    with SEOUL_GU_GEOJSON_PATH.open(encoding="utf-8") as file:
        boundaries = json.load(file)
    _validate_wgs84(boundaries)

    records = district_summary.set_index("시군구").to_dict("index")
    maximum = max(float(district_summary["보정 공급 기여지수(%)"].max()), 1.0)
    colors = cm.linear.YlGnBu_09.scale(0, maximum)
    colors.caption = f"{subject}의 자치구 내 보정 공급 기여지수(%)"

    for feature in boundaries.get("features", []):
        properties = feature.setdefault("properties", {})
        district = _district_name(properties)
        record = records.get(district, {})
        properties["자치구"] = district or "미상"
        properties["보정 기여지수"] = round(float(record.get("보정 공급 기여지수(%)", 0)), 1)
        properties["선택 단지수"] = int(record.get("선택_단지수", 0))
        properties["선택 세대수"] = int(record.get("선택_세대수", 0))
        properties["선택 동수"] = int(record.get("선택_동수", 0))
        properties["전체 세대수"] = int(record.get("전체_세대수", 0))

    supply_map = folium.Map(
        location=[SEOUL_CENTER["lat"], SEOUL_CENTER["lon"]],
        zoom_start=10.6,
        tiles=None,
        control_scale=True,
        prefer_canvas=True,
    )
    folium.TileLayer("CartoDB positron", name="기본 지도", control=False).add_to(supply_map)
    Fullscreen(position="topright").add_to(supply_map)
    folium.GeoJson(
        boundaries,
        name="자치구별 공급 기여도",
        style_function=lambda feature: {
            "fillColor": colors(feature["properties"].get("보정 기여지수", 0)),
            "color": "#4B5563",
            "weight": 1.1,
            "fillOpacity": 0.78,
        },
        highlight_function=lambda _: {"color": "#111827", "weight": 2.2, "fillOpacity": 0.9},
        tooltip=folium.GeoJsonTooltip(
            fields=["자치구", "보정 기여지수", "선택 단지수", "선택 세대수", "선택 동수", "전체 세대수"],
            aliases=[
                "자치구",
                "보정 공급 기여지수(%)",
                f"{subject} 단지수",
                f"{subject} 세대수",
                f"{subject} 동수",
                "전체 세대수",
            ],
            localize=True,
            sticky=False,
            labels=True,
        ),
    ).add_to(supply_map)
    colors.add_to(supply_map)
    supply_map.fit_bounds([[37.41, 126.76], [37.71, 127.19]])
    return supply_map
