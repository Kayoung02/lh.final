import html
import json
import re

import branca.colormap as cm
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

    legend_rows = "".join(
        f"<div><span style='display:inline-block;width:10px;height:10px;border-radius:50%;"
        f"background:{color};margin-right:6px;'></span>{developer_type}</div>"
        for developer_type, color in DEVELOPER_TYPE_COLORS.items()
    )
    supply_map.get_root().html.add_child(
        folium.Element(
            "<div style='position:fixed;bottom:24px;left:24px;z-index:1000;"
            "background:rgba(255,255,255,.94);border:1px solid #d8dde3;border-radius:6px;"
            "padding:9px 11px;font-size:12px;color:#263238;line-height:1.55;'>"
            "<strong>시행주체 구분</strong>"
            f"{legend_rows}</div>"
        )
    )

    folium.LayerControl(collapsed=True).add_to(supply_map)
    return supply_map


def _district_from_boundary_properties(properties: dict) -> str | None:
    """행정동 GeoJSON 속성에서 상위 자치구명을 안전하게 추출한다."""
    for value in properties.values():
        match = re.search(r"([가-힣]+구)", str(value))
        if match:
            return match.group(1)
    return None


def build_public_share_map(district_summary, ratio_column: str, public_mode: str):
    """자치구별 전체 아파트 대비 공공 시행 비율을 색으로 보여준다."""
    share_map = folium.Map(
        location=[SEOUL_CENTER["lat"], SEOUL_CENTER["lon"]],
        zoom_start=SEOUL_CENTER["zoom"],
        tiles=None,
        control_scale=True,
    )
    folium.TileLayer("CartoDB positron", name="기본 지도", control=False).add_to(share_map)
    Fullscreen(position="topright").add_to(share_map)

    summary_by_district = district_summary.set_index("시군구").to_dict("index")
    maximum = max(float(district_summary[ratio_column].max()), 1.0)
    colormap = cm.linear.YlOrRd_07.scale(0, maximum)
    colormap.caption = f"{public_mode} 비율 (%)"

    if SEOUL_ADM_DONG_GEOJSON_PATH.exists():
        with SEOUL_ADM_DONG_GEOJSON_PATH.open(encoding="utf-8") as file:
            boundaries = json.load(file)

        for feature in boundaries.get("features", []):
            properties = feature.setdefault("properties", {})
            district = _district_from_boundary_properties(properties)
            record = summary_by_district.get(district, {})
            properties["자치구"] = district or "미상"
            properties["공공비율"] = float(record.get(ratio_column, 0.0))
            properties["전체단지"] = int(record.get("전체_단지수", 0))
            properties["공공단지"] = int(record.get("공공_단지수", 0))
            properties["전체세대"] = int(record.get("전체_세대수", 0))
            properties["공공세대"] = int(record.get("공공_세대수", 0))

        folium.GeoJson(
            boundaries,
            name="자치구별 공공 시행 비율",
            style_function=lambda feature: {
                "fillColor": colormap(feature["properties"].get("공공비율", 0)),
                "color": "#6B7280",
                "weight": 0.55,
                "fillOpacity": 0.72,
            },
            highlight_function=lambda _: {"color": "#111827", "weight": 1.8, "fillOpacity": 0.85},
            tooltip=folium.GeoJsonTooltip(
                fields=["자치구", "공공비율", "전체단지", "공공단지", "전체세대", "공공세대"],
                aliases=["자치구", f"{public_mode} 비율(%)", "전체 단지", "공공 단지", "전체 세대수", "공공 세대수"],
                localize=True,
                sticky=False,
                labels=True,
            ),
        ).add_to(share_map)
        colormap.add_to(share_map)
    else:
        folium.Marker(
            location=[SEOUL_CENTER["lat"], SEOUL_CENTER["lon"]],
            tooltip="행정동 경계 GeoJSON 파일을 확인하세요.",
        ).add_to(share_map)

    share_map.fit_bounds([[37.41, 126.76], [37.71, 127.19]])

    return share_map
