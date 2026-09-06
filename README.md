# Power Outages Prediction

基于气候变化与能源结构信息计算国家级停电相对风险，并通过 Streamlit 展示交互地图和风险构成。

当前版本已经完成从本地原始快照到前端的完整离线流水线：

1. 读取 GEM Global Integrated Power Tracker 2026 年 8 月 Excel，筛选在运设施并计算国家能源结构；
2. 读取三份 CMIP5/RCP4.5 NetCDF，固定提取 2100 年并按国家聚合 28 个模式成员；
3. 使用 HDD > 3000 ℃·日等固定阈值和回归公式计算风险及两类贡献；
4. 自动生成 CSV、Parquet、GeoJSON、质量报告、运行清单和 300 DPI 地图；
5. 使用 Streamlit 展示可交互地图、国家详情、风险构成和数据来源。

旧 Excel 中保存的 `cold` 标记实际与 HDD > 300 的处理结果一致，因此“旧结果复现”和“按正确阈值发布”被明确分开。前端展示后者，回归测试保留前者。

## 运行

```powershell
# 1. 创建/同步隔离环境
.\scripts\setup_env.ps1

# 2. 从本地原始快照构建全部发布数据（约 1 分钟）
.\scripts\run_pipeline.ps1

# 3. 启动前端
.\scripts\run_app.ps1
```

也可以直接运行：

```powershell
uv run --frozen python -m outage_prediction build --config config/project.yaml
uv run --frozen python -m streamlit run app/streamlit_app.py
```

前端默认地址为 `http://localhost:8501`，页面不提供日期、情景、阈值或模型选择器。

## 验证

```powershell
uv run --frozen python -m pytest
uv run --frozen python -m ruff check src app tests scripts
```

输出位于 `outputs/latest/`：

- `country_risk.csv` / `country_risk.parquet`
- `country_risk.geojson`
- `energy_features.parquet` / `climate_features.parquet`
- `energy_quality_report.json` / `climate_quality_report.json`
- `power_outage_risk.png`
- `legacy_formula_reproduction.csv`
- `run_manifest.json`

`risk_score` 是固定回归公式产生的相对风险得分，不是停电概率。

正式版本仅统计 GIPT 标记为 `operating` 的设施，能源占比的分母是 GIPT
所追踪的全部在运发电设施容量，并不等同于各国官方完整装机统计。气候数据固定为
CMIP5/RCP4.5 的 2100 年值，页面因此不提供日期选择器。旧 Excel 仅用于验证 Python
公式能逐行复现 199 条历史结果；它不再作为正式发布结果的数据源。
