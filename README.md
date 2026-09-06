# Power Outages Prediction

基于气候变化与固定能源结构计算国家级停电相对风险，并通过 Streamlit 展示可选择年份的交互地图和风险构成。

当前离线流水线：

1. 读取 GEM Global Integrated Power Tracker 2026 年 8 月 Excel，只统计在运设施并计算国家能源结构；
2. 读取三份 Copernicus CDS 的 CMIP5/RCP4.5 年度 NetCDF；
3. 对每个气候模式先按国家进行纬度面积加权，再对 28 个模式的国家结果取中位数；
4. 预计算 2030–2100 每一年的国家级气候指标和相对风险；
5. 统一使用连续干日 > 30 天、CDD > 300 ℃·日、HDD > 3000 ℃·日；
6. 生成可选择年份的前端数据，以及 2030、2050、2100 三张共用色标的 300 DPI 地图。

气候数据来自 Copernicus Climate Data Store；IRENA 是能源数据机构，不是这三份 NetCDF 的来源。当前能源结构在所有预测年份使用同一份 GIPT 在运设施快照，因此年份切换表示“固定能源结构下的气候情景压力测试”，不是逐年能源结构预测。

恢复过程、计算顺序及与2024年遗留表的数值对照记录在 [`CLIMATE_METHOD.md`](CLIMATE_METHOD.md)。

## 运行

```powershell
# 1. 创建/同步隔离环境
.\scripts\setup_env.ps1

# 2. 构建全部发布数据
.\scripts\run_pipeline.ps1

# 3. 启动前端
.\scripts\run_app.ps1
```

也可以直接运行：

```powershell
uv run --frozen python -m outage_prediction build --config config/project.yaml
uv run --frozen python -m streamlit run app/streamlit_app.py
```

前端默认地址为 `http://localhost:8501`。用户可选择 2030–2100 的任意整数年份，2030、2050、2100 静态图也会同时展示。

## 验证

```powershell
uv run --frozen python -m pytest
uv run --frozen python -m ruff check src app tests scripts
```

输出位于 `outputs/latest/`：

- `country_risk.csv` / `country_risk.parquet`：2030–2100 全部国家—年份结果；
- `country_risk.geojson`：前端使用的国家边界；
- `energy_features.parquet` / `climate_features.parquet`；
- `energy_quality_report.json` / `climate_quality_report.json`；
- `power_outage_risk_2030.png`；
- `power_outage_risk_2050.png`；
- `power_outage_risk_2100.png`；
- `run_manifest.json`。

`risk_score` 是固定回归公式产生的相对风险得分，不是停电概率。缺失数据不会被填成零风险，旧 Excel 中错误的 HDD > 300 标记也不再复现或发布。
