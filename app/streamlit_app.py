"""Minimal interactive frontend for the published country risk release."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from outage_prediction.visualization.interactive_map import build_interactive_map

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RELEASE_DIR = PROJECT_ROOT / "outputs" / "latest"

st.set_page_config(
    page_title="全球停电相对风险",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    .block-container {max-width: 1180px; padding-top: 2.2rem; padding-bottom: 3rem;}
    h1 {font-weight: 650; letter-spacing: -0.035em;}
    [data-testid="stMetric"] {background: #f7f9fb; border: 1px solid #e7ebf0;
        border-radius: 14px; padding: 14px 16px;}
    .source-note {color: #5d6878; font-size: 0.9rem; line-height: 1.65;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def load_release(release_version: int) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    del release_version  # Cache key changes whenever the manifest is rebuilt.
    required = [
        RELEASE_DIR / "country_risk.csv",
        RELEASE_DIR / "country_risk.geojson",
        RELEASE_DIR / "run_manifest.json",
    ]
    missing = [path.name for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "缺少前端发布文件：" + ", ".join(missing) + "。请先运行数据构建命令。"
        )
    data = pd.read_csv(required[0])
    geojson = json.loads(required[1].read_text(encoding="utf-8"))
    # A stable top-level feature ID is retained for downloads and future map renderers.
    for feature in geojson["features"]:
        feature["id"] = str(feature["properties"]["iso3"])
    manifest = json.loads(required[2].read_text(encoding="utf-8"))
    return data, geojson, manifest


def _event_iso(event: Any) -> str | None:
    if event is None:
        return None
    try:
        points = event.selection.points
    except (AttributeError, KeyError):
        try:
            points = event.get("selection", {}).get("points", [])
        except AttributeError:
            return None
    if not points:
        return None
    point = points[0]
    location = point.get("location") if hasattr(point, "get") else None
    if location:
        return str(location)
    custom = point.get("customdata") if hasattr(point, "get") else None
    if custom:
        return str(custom[0])
    return None


def _signed_description(value: float) -> str:
    if value > 0:
        return "增加风险"
    if value < 0:
        return "降低风险"
    return "无净影响"


try:
    manifest_path = RELEASE_DIR / "run_manifest.json"
    release_version = manifest_path.stat().st_mtime_ns if manifest_path.is_file() else 0
    risk_data, world_geojson, run_manifest = load_release(release_version)
except FileNotFoundError as error:
    st.error(str(error))
    st.code("uv run python -m outage_prediction build --config config/project.yaml")
    st.stop()

st.title("全球停电相对风险分布")
st.caption(
    "GIPT 2026 能源设施 · CMIP5 / RCP4.5 · 固定 2100 年 · "
    "风险得分并非停电发生概率"
)

map_event = st.plotly_chart(
    build_interactive_map(risk_data, world_geojson),
    width="stretch",
    on_select="rerun",
    selection_mode="points",
    key="risk_map",
    config={"scrollZoom": True, "displaylogo": False},
)
clicked_iso = _event_iso(map_event)

available = risk_data.sort_values(["country_name", "iso3"])[["iso3", "country_name"]]
options = available["iso3"].tolist()
labels = dict(zip(available["iso3"], available["country_name"], strict=True))
if "selected_iso" not in st.session_state:
    st.session_state.selected_iso = str(
        risk_data.loc[risk_data["risk_score"].idxmax(), "iso3"]
    )
if clicked_iso in options:
    st.session_state.selected_iso = clicked_iso

selected_iso = st.selectbox(
    "查看国家或地区（也可点击地图）",
    options,
    index=options.index(st.session_state.selected_iso),
    format_func=lambda iso: f"{labels[iso]} · {iso}",
    label_visibility="collapsed",
)
st.session_state.selected_iso = selected_iso
selected = risk_data.loc[risk_data["iso3"].eq(selected_iso)].iloc[0]

st.subheader(selected["country_name"])
if selected["data_quality"] != "complete" or pd.isna(selected["risk_score"]):
    st.info("该地区缺少完整的能源或气候输入，因此不计算风险，也不会按零风险展示。")
else:
    metric_1, metric_2, metric_3 = st.columns(3)
    metric_1.metric("停电相对风险得分", f"{selected['risk_score']:.4f}")
    metric_2.metric(
        "气候灾害直接贡献",
        f"{selected['climate_contribution']:+.4f}",
        _signed_description(float(selected["climate_contribution"])),
        delta_color="inverse",
    )
    metric_3.metric(
        "新能源交互贡献",
        f"{selected['renewable_interaction_contribution']:+.4f}",
        _signed_description(float(selected["renewable_interaction_contribution"])),
        delta_color="inverse",
    )

    detail, composition = st.columns([1, 1.4], gap="large")
    with detail:
        st.markdown("#### 风险输入")
        st.write(
            {
                "连续干日": f"{selected['dry']:.1f} 天",
                "制冷度日": f"{selected['cdd']:.1f} ℃·日",
                "采暖度日": f"{selected['hdd']:.1f} ℃·日",
                "光伏占追踪容量": f"{selected['pv_share']:.1%}",
                "风电占追踪容量": f"{selected['wind_share']:.1%}",
                "水电占追踪容量": f"{selected['hydro_share']:.1%}",
                "干旱": "是" if selected["drought"] == 1 else "否",
                "高温": "是" if selected["heat"] == 1 else "否",
                "低温": "是" if selected["cold"] == 1 else "否",
                "气候空间聚合": (
                    "最近网格回退（小区域）"
                    if bool(selected["climate_spatial_fallback"])
                    else "国家内网格面积加权"
                ),
            }
        )
    with composition:
        st.markdown("#### 风险构成（按绝对贡献）")
        composition_figure = go.Figure(
            go.Bar(
                x=[selected["climate_share_abs"], selected["renewable_share_abs"]],
                y=["气候灾害直接贡献", "新能源交互贡献"],
                orientation="h",
                text=[
                    f"{selected['climate_share_abs']:.1%}",
                    f"{selected['renewable_share_abs']:.1%}",
                ],
                textposition="inside",
                marker_color=["#4A7FA7", "#E6A15A"],
                hoverinfo="skip",
            )
        )
        composition_figure.update_layout(
            height=220,
            margin={"l": 0, "r": 12, "t": 4, "b": 20},
            xaxis={"tickformat": ".0%", "range": [0, 1], "title": None},
            yaxis={"title": None, "autorange": "reversed"},
            showlegend=False,
        )
        st.plotly_chart(composition_figure, width="stretch", config={"displayModeBar": False})
        st.caption("占比使用贡献绝对值计算；上方有符号数值表示提高或降低风险。")

with st.expander("数据来源与计算口径"):
    sources = run_manifest["sources"]
    st.markdown(
        f"""
        <div class="source-note">
        <b>能源结构：</b>{sources['energy']}<br>
        <b>气候指标：</b>{sources['climate']}，CMIP5 / RCP4.5，固定 2100 年。<br>
        <b>国家边界：</b>{sources['boundary']}<br>
        <b>阈值：</b>连续干日 &gt; 30 天；CDD &gt; 300 ℃·日；HDD &gt; 3000 ℃·日。<br>
        <b>能源口径：</b>仅统计 GIPT 中 operating 设施；
        占比以 GIPT 追踪的全部在运技术容量为分母。<br>
        <b>模型：</b>{run_manifest['risk_model']['name']} /
        {run_manifest['risk_model']['version']}。<br>
        该得分是固定回归公式的相对指标，不是 0–1 概率，也不构成实时停电预警。
        </div>
        """,
        unsafe_allow_html=True,
    )

image_path = RELEASE_DIR / "power_outage_risk.png"
if image_path.is_file():
    with st.expander("静态地图"):
        st.image(image_path, width="stretch")
        st.download_button(
            "下载 PNG",
            data=image_path.read_bytes(),
            file_name="power_outage_risk.png",
            mime="image/png",
        )
