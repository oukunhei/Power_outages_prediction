# Power Outages Prediction

基于气候变化与能源结构信息计算国家级停电相对风险，并通过 Streamlit 展示交互地图和风险构成。

当前版本完成两件事：

1. 使用 Python 逐行复现旧 `parameters.xlsx` 中的 199 条固定公式结果；
2. 使用已确认的 HDD > 3000 ℃·日阈值重新计算发布结果，并生成交互前端数据与静态地图。

旧 Excel 中保存的 `cold` 标记实际与 HDD > 300 的处理结果一致，因此“旧结果复现”和“按正确阈值发布”被明确分开。前端展示后者，回归测试保留前者。

## 运行

```powershell
# 1. 创建/同步隔离环境
.\scripts\setup_env.ps1

# 2. 复现旧结果并构建前端数据
.\scripts\run_pipeline.ps1

# 3. 启动前端
.\scripts\run_app.ps1
```

也可以直接运行：

```powershell
uv run outage-prediction build-legacy --config config/project.yaml
uv run streamlit run app/streamlit_app.py
```

前端默认地址为 `http://localhost:8501`，页面不提供日期、情景、阈值或模型选择器。

## 验证

```powershell
uv run pytest
uv run ruff check src app tests scripts
```

输出位于 `outputs/latest/`：

- `country_risk.csv` / `country_risk.parquet`
- `country_risk.geojson`
- `power_outage_risk.png`
- `legacy_formula_reproduction.csv`
- `run_manifest.json`

`risk_score` 是固定回归公式产生的相对风险得分，不是停电概率。
