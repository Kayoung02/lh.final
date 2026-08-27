import html
import json

import folium
from folium.plugins import Fullscreen, MarkerCluster

from common.config import SEOUL_ADM_DONG_GEOJSON_PATH, SEOUL_CENTER


DEVELOPER_TYPE_COLORS = {
    "공공": "#1769AA",
    "기타공공": "#5C6BC0",
    "공공·조합 공동": "#00897B",
    "공공·민간 공동": "#43A047",
    "조합": "#EF6C00",
    "민간": "#607D8B",
    "미상": "#9E9E9E",
    "확인필요": "#9E9E9E",
}


def _popup_html(row) -> str:
    def value(column: str) -> str:
        return html.escape(str(row.get(column, "미상")))

    return f"""
    <div style='font-family:Arial, sans-serif; min-width:220px;'>
      <strong>{value('k-아파트명')}</strong><br>
      <span>{value('주소(시군구)')} {value('주소(읍면동)')}</span><hr style='margin:6px 0;'>
      시행사: {value('시행사_표시')}<br>
      시행주체: {value('시행주체 구분')}<br>
      세대수: {value('세대수')}세대 / 동수: {value('동수')}개동<br>
      사용승인: {value('사용승인연도')}년
    </div>
    """


def build_public_supply_map(apartment):
    supply_map = folium.Map(
        location=[SEOUL_CENTER["lat"], SEOUL_CENTER["lon"]],
        zoom_start=SEOUL_CENTER["zoom"],
        tiles=None,
        control_scale=True,
    )
    folium.TileLayer("CartoDB positron", name="화이트 베이스맵", control=False).add_to(supply_map)
    Fullscreen(position="topright").add_to(supply_map)

    # 서울 행정동 경량 GeoJSON이 있을 때만 경계를 올린다.
    # 원본 전국 shp는 앱에서 직접 읽지 않는다.
    if SEOUL_ADM_DONG_GEOJSON_PATH.exists():
        with SEOUL_ADM_DONG_GEOJSON_PATH.open(encoding="utf-8") as file:
            dong_boundaries = json.load(file)
        folium.GeoJson(
            dong_boundaries,
            name="행정동 경계",
            style_function=lambda _: {"fillOpacity": 0.02, "color": "#8a8f98", "weight": 0.65},
            tooltip=folium.GeoJsonTooltip(fields=["ADM_NM"], aliases=["행정동"], sticky=False),
        ).add_to(supply_map)

    markers = MarkerCluster(name="아파트 단지", disableClusteringAtZoom=15).add_to(supply_map)

    for _, row in apartment.loc[apartment["좌표유효"]].iterrows():
        color = DEVELOPER_TYPE_COLORS.get(row["시행주체 구분"], "#9E9E9E")
        folium.CircleMarker(
            location=[row["위도"], row["경도"]],
            radius=6,
            color=color,
            weight=1,
            fill=True,
            fill_color=color,
            fill_opacity=0.78,
            tooltip=f"{row['k-아파트명']} · {row['세대수']:,}세대",
            popup=folium.Popup(_popup_html(row), max_width=320),
        ).add_to(markers)

    folium.LayerControl(collapsed=True).add_to(supply_map)
    return supply_map
