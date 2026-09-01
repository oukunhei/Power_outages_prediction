"""Minimal interactive frontend for the published country risk release."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

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
def load_release() -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
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


def build_map(data: pd.DataFrame, geojson: dict[str, Any]) -> go.Figure:
    feature_rows = []
    for feature in geojson["features"]:
        properties = feature.get("properties", {})
        feature_rows.append(
            (
                properties.get("iso3"),
                properties.get("country_name") or properties.get("name") or "未知地区",
            )
        )
    boundaries = pd.DataFrame(feature_rows, columns=["iso3", "country_name"])
    scored = data.loc[data["risk_score"].notna()].copy()

    figure = go.Figure()
    figure.add_trace(
        go.Choropleth(
            geojson=geojson,
            featureidkey="properties.iso3",
            locations=boundaries["iso3"],
            z=np.zeros(len(boundaries)),
            customdata=boundaries[["iso3", "country_name"]],
            colorscale=[[0, "#D9DEE5"], [1, "#D9DEE5"]],
            showscale=False,
            marker_line_color="white",
            marker_line_width=0.35,
            hovertemplate="<b>%{customdata[1]}</b><br>数据不足<extra></extra>",
            name="数据不足",
        )
    )
    custom_columns = [
        "iso3",
        "country_name",
        "climate_share_abs",
        "renewable_share_abs",
        "climate_contribution",
        "renewable_interaction_contribution",
    ]
    figure.add_trace(
        go.Choropleth(
            geojson=geojson,
            featureidkey="properties.iso3",
            locations=scored["iso3"],
            z=scored["risk_score"],
            customdata=scored[custom_columns],
            colorscale=[
                [0.0, "#2878B5"],
                [0.45, "#F5F7F6"],
                [0.68, "#F9C66B"],
                [1.0, "#C83E3A"],
            ],
            zmid=0,
            marker_line_color="white",
            marker_line_width=0.35,
            colorbar={
                "title": {"text": "相对风险得分", "side": "right"},
                "thickness": 13,
                "len": 0.58,
                "outlinewidth": 0,
            },
            hovertemplate=(
                "<b>%{customdata[1]}</b><br>"
                "相对风险：%{z:.4f}<br>"
                "气候直接贡献占比：%{customdata[2]:.1%}<br>"
                "新能源交互贡献占比：%{customdata[3]:.1%}"
                "<extra></extra>"
            ),
            name="相对风险",
        )
    )
    figure.update_geos(
        fitbounds="locations",
        visible=False,
        projection_type="natural earth",
        bgcolor="rgba(0,0,0,0)",
    )
    figure.update_layout(
        height=590,
        margin={"l": 0, "r": 0, "t": 8, "b": 0},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        clickmode="event+select",
        dragmode="pan",
        showlegend=False,
    )
    return figure


def _signed_description(value: float) -> str:
    if value > 0:
        return "增加风险"
    if value < 0:
        return "降低风险"
    return "无净影响"


try:
    risk_data, world_geojson, run_manifest = load_release()
except FileNotFoundError as error:
    st.error(str(error))
    st.code("uv run outage-prediction build-legacy --config config/project.yaml")
    st.stop()

st.title("全球停电相对风险分布")
st.caption(
    "气候变化与能源结构交互视角 · CMIP5 / RCP4.5 · 固定 2100 年 · "
    "风险得分并非停电发生概率"
)

map_event = st.plotly_chart(
    build_map(risk_data, world_geojson),
    width="stretch",
    on_select="rerun",
    selection_mode="points",
    key="risk_map",
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
    st.info("该地区缺少完整的旧项目气候连续指标，因此不计算风险，也不会按零风险展示。")
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
                "干旱": "是" if selected["drought"] == 1 else "否",
                "高温": "是" if selected["heat"] == 1 else "否",
                "低温": "是" if selected["cold"] == 1 else "否",
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
