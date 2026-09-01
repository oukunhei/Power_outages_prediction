# 全球停电风险预测与可视化平台：项目搭建计划

## 1. 项目目标

搭建一套可重复运行的数据处理流水线和简洁前端。第一版不在运行时下载外部数据，能源与气候数据均使用仓库 `data` 目录中的冻结本地快照，实现以下闭环：

```text
本地 GEM GIPT 能源快照 + 本地 CMIP5 气候快照
          ↓
版本记录与数据校验
          ↓
国家级能源结构与气候灾害指标
          ↓
可插拔风险引擎（默认固定回归公式）
          ↓
风险拆解、交互地图与静态图片
          ↓
简洁 Web 前端展示
```

最终用户只需要打开网页，即可查看全球国家/地区级停电风险分布，点击或悬停某个国家/地区时查看：

- 停电相对风险得分；
- 气候灾害直接贡献；
- 新能源相关贡献，即气候灾害与新能源结构的交互贡献；
- 两类贡献的构成占比；
- 数据完整性状态；
- 数据来源、快照版本和获取日期。

前端不提供日期选择、模型选择或参数编辑功能。气候情景、目标年份、能源项目状态范围和风险模型均在后端配置文件中固定，以保证页面简洁和不同用户看到的结果一致。第一版启用固定回归公式，同时预留机器学习风险模型接口。

## 2. 项目边界

### 2.1 第一版包含

- 读取 `data` 目录中已下载的 Global Energy Monitor（GEM）Global Integrated Power Tracker（GIPT）能源快照；
- 读取 `data/climate/raw` 中已复制的 CMIP5/RCP4.5 气候 NetCDF 快照；
- 自动完成缓存、清洗、字段标准化、国家代码统一、空间聚合和质量检查；
- 计算光伏、风电和水电占总装机容量的比例；
- 计算干旱、高温和低温灾害指标；
- 按现有固定回归公式计算国家级停电相对风险；
- 提供统一风险模型接口和模型工厂，为未来机器学习方法预留接入点；
- 将总风险拆分为气候灾害直接贡献和新能源交互贡献；
- 生成可交互世界地图和高分辨率 PNG 图片；
- 使用 Streamlit 构建简洁前端；
- 保存每次运行的数据版本、配置、日志和输出清单；
- 支持命令行校验本地快照，并一键完成离线重算。

### 2.2 第一版不包含

- 不重新估计回归系数；
- 不把相对风险得分描述为真实停电概率；
- 不提供日期选择器；
- 不提供用户自行调整回归系数、阈值或气候情景的控件；
- 不进行电网实时调度或实时停电告警；
- 不在第一版实现机器学习训练或机器学习预测结果，但必须实现可替换的模型接口；
- 不依赖 RStudio 或 QGIS 才能运行。
- 不通过 API 获取 GEM 数据，也不检查 GEM 新版本；
- 不通过 API 获取气候数据，也不检查 CDS 新版本；
- 不在前端启动或刷新时访问 GEM/CDS；
- 不建设后台数据更新服务。

### 2.3 第一版数据更新策略

第一版采用“人工获取、快照冻结、完全离线处理”的数据策略：

1. GEM 能源数据直接使用 `data` 目录中人工下载并冻结的 GIPT 文件；
2. 气候数据直接使用 `data/climate/raw` 中的三份 CMIP5/RCP4.5 NetCDF；
3. 每次构建先校验文件路径、大小、SHA-256、变量、时间和模型成员；
4. 快照不覆盖、不自动更新；
5. 后续运行只执行预处理、风险计算、图片生成和前端发布；
6. 如需新版数据，由项目负责人手动替换快照并更新配置与清单；
7. 前端只展示当前绑定快照的数据来源、情景和数据版本。

## 3. 关键口径与默认配置

所有会影响结果的口径必须写入 `config/project.yaml`，并记录在每次运行的 `run_manifest.json` 中。前端只展示口径摘要，不允许用户修改。

### 3.1 空间尺度

- 输出尺度：国家/地区级；
- 主连接键：ISO 3166-1 alpha-3；
- 特殊地区和非标准代码使用人工维护的映射表；
- 缺少气候或能源数据时保留为缺失值，不得自动替换为 0；
- 无数据国家在地图上显示为灰色，并标注“数据不足”。

### 3.2 能源数据口径

建议生产版本默认只统计 `operating` 项目，因为“装机容量”通常指已经投运的容量。为复现旧项目，保留一个仅供开发测试的 `legacy_compatible` 配置，纳入 announced、pre-construction、construction、permitted、pre-permit 和 operating 等状态。

生产页面只能绑定其中一种固定口径，不能向用户提供切换按钮。正式开发前由项目负责人确认采用：

- `operating`：科学含义更清晰，推荐；
- `legacy_compatible`：更接近旧项目结果。

国家 `c` 的能源比例定义为：

```text
PV_c    = 光伏容量_c / 全部发电技术容量_c
Wind_c  = 风电容量_c / 全部发电技术容量_c
Hydro_c = 水电容量_c / 全部发电技术容量_c
```

分子与分母必须采用相同的项目状态范围、容量单位和国家映射口径。所有容量统一为 MW。

### 3.3 气候数据口径

第一版固定为与旧回归公式一致的口径：

- 数据体系：CMIP5；
- 情景：RCP4.5；
- 数据时段：2006–2100；
- 风险输入年份：固定使用 2100 年；
- 多模式处理：对 28 个模型成员取中位数后进行国家级空间聚合；
- 页面不展示日期选择器，只在数据来源说明中展示 2100 年和 RCP4.5。

三个灾害指标：

1. 干旱 `D`：年度最长连续无有效降水日数超过 30 天时为 1，否则为 0。无有效降水定义为日降水量小于 1 mm。
2. 高温 `H`：年度制冷度日 CDD 超过 300 ℃·日时为 1，否则为 0。
3. 低温 `C`：年度采暖度日 HDD 超过 3000 ℃·日时为 1，否则为 0。该阈值已确认并固定。

### 3.4 固定回归公式

记：

- `D`：干旱虚拟变量；
- `H`：高温虚拟变量；
- `C`：低温虚拟变量；
- `PV`：光伏容量占比；
- `W`：风电容量占比；
- `HY`：水电容量占比。

旧项目 Excel 中的固定公式为：

```text
Risk = -0.0019D - 0.0057H + 0.0063C
       + 0.0413D×HY - 0.0030H×HY - 0.0116C×HY
       - 0.0196D×W  + 0.01801H×W + 0.0398C×W
       + 0.2084D×PV + 0.0764H×PV + 0.4810C×PV
```

该值称为“停电相对风险得分”，不是 0–1 概率。前端、图例和图片标题不得使用“发生概率”字样。

### 3.5 风险构成拆解

由于固定公式中没有新能源的独立主效应，页面中的“新能源贡献”必须准确解释为“气候灾害与新能源结构的交互贡献”。

气候灾害直接贡献：

```text
ClimateContribution = -0.0019D - 0.0057H + 0.0063C
```

新能源交互贡献：

```text
RenewableInteractionContribution =
    + 0.0413D×HY - 0.0030H×HY - 0.0116C×HY
    - 0.0196D×W  + 0.01801H×W + 0.0398C×W
    + 0.2084D×PV + 0.0764H×PV + 0.4810C×PV
```

并满足：

```text
Risk = ClimateContribution + RenewableInteractionContribution
```

部分系数为负，因此贡献可能降低总风险。前端需要同时展示：

- 有符号贡献值，用于说明该部分提高还是降低风险；
- 绝对贡献构成占比，用于回答“风险主要由哪一部分驱动”。

绝对贡献占比定义为：

```text
denominator = |ClimateContribution| + |RenewableInteractionContribution|

ClimateShare   = |ClimateContribution| / denominator
RenewableShare = |RenewableInteractionContribution| / denominator
```

当 `denominator = 0` 时，两项占比均为 0，并显示“无可分解贡献”。不能直接用某项贡献除以总风险，否则负贡献会产生负百分比或超过 100% 的结果。

### 3.6 风险模型切换口径

后端配置包含唯一的风险模型选择项，第一版固定为：

```yaml
risk_model:
  type: formula
  artifact_path: null
```

未来机器学习模型上线后可将 `type` 改为 `machine_learning` 并指定模型文件，但前端不提供模型切换控件。一次发布只能绑定一个风险模型，运行清单必须记录模型类型、模型版本和模型文件哈希。

## 4. 技术选型

| 环节 | 技术 | 用途 |
|---|---|---|
| Python 环境 | Python 3.11/3.12 + `uv` | 创建隔离环境并锁定依赖，避免当前 Anaconda 冲突 |
| 配置 | YAML + Pydantic Settings | 固定情景、阈值、状态范围和路径 |
| 表格处理 | pandas + pyarrow | 清洗数据并保存 Parquet |
| 气候数据 | xarray + netCDF4/dask | 读取并处理本地 NetCDF |
| 空间处理 | geopandas + shapely + regionmask/rioxarray | 国家级空间聚合 |
| 数据校验 | Pandera 或自定义校验器 | 字段、范围、唯一性和覆盖率检查 |
| 可视化 | Plotly + GeoJSON | 交互式国家级地图 |
| 静态图片 | Matplotlib + GeoPandas | 稳定生成 300 DPI PNG |
| 前端 | Streamlit | 构建单页简洁应用 |
| 测试 | pytest | 单元测试和端到端测试 |
| 日志 | Python logging / structlog | 记录流水线状态和错误 |
| 风险模型接口 | Python Protocol/ABC + 模型工厂 | 默认回归公式，预留机器学习适配器 |
| 执行入口 | PowerShell + Python CLI | 校验本地快照并执行可重复的离线构建 |

第一版不单独建设 FastAPI 服务。Streamlit 直接读取发布目录中的 Parquet、GeoJSON、PNG 和运行清单即可，减少部署组件和故障点。若未来需要移动端、外部 API 或多人并发，再拆分后端服务。

## 5. 建议目录结构

```text
Power_outages_prediction/
├─ PROJECT_PLAN.md
├─ README.md
├─ pyproject.toml
├─ uv.lock
├─ .env.example
├─ .gitignore
├─ config/
│  ├─ project.yaml
│  ├─ country_aliases.csv
│  └─ gem_schema_aliases.yaml
├─ src/
│  └─ outage_prediction/
│     ├─ __init__.py
│     ├─ cli.py
│     ├─ settings.py
│     ├─ logging_config.py
│     ├─ snapshots/
│     │  └─ validation.py
│     ├─ processing/
│     │  ├─ energy.py
│     │  ├─ climate.py
│     │  ├─ country_codes.py
│     │  └─ spatial.py
│     ├─ scoring/
│     │  ├─ base.py
│     │  ├─ formula.py
│     │  ├─ decomposition.py
│     │  ├─ ml_adapter.py
│     │  └─ registry.py
│     ├─ visualization/
│     │  ├─ interactive_map.py
│     │  └─ static_map.py
│     └─ pipeline.py
├─ app/
│  └─ streamlit_app.py
├─ data/
│  ├─ Global Integrated Power August 2026-v3.xlsx
│  ├─ climate/raw/
│  │  ├─ annual_consecutive_dry_days/
│  │  ├─ annual_cooling_degree_days/
│  │  └─ annual_heating_degree_days/
│  ├─ interim/
│  ├─ processed/
│  └─ reference/
├─ outputs/
│  ├─ latest/
│  │  ├─ country_risk.parquet
│  │  ├─ country_risk.csv
│  │  ├─ country_risk.geojson
│  │  ├─ power_outage_risk.png
│  │  └─ run_manifest.json
│  └─ archive/
├─ tests/
│  ├─ test_formula.py
│  ├─ test_energy_processing.py
│  ├─ test_climate_processing.py
│  ├─ test_country_mapping.py
│  └─ test_pipeline_smoke.py
└─ scripts/
   ├─ run_pipeline.ps1
   └─ run_app.ps1
```

`data` 中的原始快照不自动覆盖。`outputs/latest` 始终指向最近一次完整成功的结果；失败运行不得破坏上一版可用结果。大型 NetCDF 只保存在本地并由 `.gitignore` 排除。

## 6. 本地数据快照设计

### 6.1 本地 GEM Global Integrated Power Tracker 快照

第一版不实现 `GEMClient`，直接读取仓库 `data` 目录中的 GIPT Excel 快照。处理模块职责如下：

1. 发现并读取 `data/Global Integrated Power *.xlsx`；
2. 确认只存在一个被选中的生产快照；
3. 从文件名和工作簿元数据识别 release；
4. 计算 SHA-256；
5. 记录文件名、release、文件大小和校验值；
6. 验证文件格式、必需工作表和关键列；
7. 只有完整通过校验后才进入能源数据预处理。

GIPT 文件由项目负责人从 GEM 官方渠道一次性下载。代码不得抓取 GEM 网页，也不得在运行时访问 GEM 网络服务。

需要对 GIPT 的版本变化进行兼容：

- 使用字段别名配置处理 `Country`/`Country/Area` 等改名；
- 将状态值统一为内部枚举；
- 将 Solar、Wind、Hydropower 等技术名称映射为稳定内部名称；
- 将容量转换为数值型 MW；
- 对重复设施 ID、未知状态、负容量和缺失国家代码进行报告；
- 当关键字段消失时立即停止流水线，而不是生成错误结果。

### 6.2 本地 CMIP5/RCP4.5 气候快照

第一版不实现 `CDSClient`。气候处理模块直接读取以下本地快照：

1. `data/climate/raw/annual_consecutive_dry_days/cdd_CMIP5_rcp45_yr_2006-2100.nc`；
2. `data/climate/raw/annual_cooling_degree_days/cd_CMIP5_rcp45_yr_2006-2100.nc`；
3. `data/climate/raw/annual_heating_degree_days/hd_CMIP5_rcp45_yr_2006-2100.nc`。

三份文件均应满足：全球 2° 网格、95 个年度时间点、28 个模型成员，并分别包含 `cdd`、`cd`、`hd` 变量。处理前应校验：

- 文件与对应 `provenance.json` 存在；
- SHA-256 与快照清单一致；
- 时间覆盖 2006–2100；
- `member=28`、`lat=90`、`lon=180`；
- 指标单位分别为 days、degC day、degC day；
- 多个 `_FillValue` 统一解码为 `NaN`；
- 原始 NetCDF 不进入 Git；
- 前端只读取处理完成的发布数据，不直接打开 NetCDF。

## 7. 数据预处理设计

### 7.1 能源数据

处理流程：

1. 读取 GIPT 数据；
2. 校验 release 与关键字段；
3. 标准化国家名、ISO3、技术、状态和容量；
4. 根据后端固定状态范围筛选；
5. 按国家和技术聚合容量；
6. 计算国家全部技术总容量；
7. 计算 PV、Wind、Hydro 占比；
8. 检查三项比例均位于 `[0, 1]`；
9. 输出 `energy_features.parquet` 和质量报告。

不得把缺失容量直接解释为 0。只有确认“数据源覆盖该国家且该技术容量确实为零”时才能填 0；否则保留缺失并设置数据质量标记。

### 7.2 气候数据

处理流程：

1. 检查温度和降水单位并统一；
2. 从年度气候指标快照中固定提取 2100 年；
3. 校验每个模式在 2100 年均有有效数据；
4. 使用国家边界做面积加权聚合，纬度方向采用面积权重；
5. 对每个国家取多个气候模式的中位数；
6. 根据固定阈值生成 `D`、`H`、`C`；
7. 输出连续指标、二元指标、模式数量和不确定性摘要；
8. 对小岛国家使用明确记录的最近有效网格或面积交叠回退策略；
9. 输出 `climate_features.parquet` 和质量报告。

### 7.3 国家代码与合并

- 建立可版本控制的国家别名表；
- 自动处理常见 GEM 国家/地区命名差异；
- 特殊代码必须人工确认，不能模糊匹配后直接入库；
- 合并后报告能源覆盖率、气候覆盖率和最终可评分国家数量；
- 原项目中的 `ZAR` 等非当前标准代码需要显式修订；
- 未匹配记录单独输出，流水线按严重程度警告或失败。

## 8. 风险计算与输出字段

### 8.1 统一风险模型接口

流水线不得直接调用固定公式函数，而应依赖统一的 `RiskModel` 接口。建议契约如下：

```python
class RiskModel(Protocol):
    name: str
    version: str

    def predict(self, features: pd.DataFrame) -> pd.DataFrame:
        """返回 iso3、risk_score、model_name 和 model_version。"""

    def explain(
        self,
        features: pd.DataFrame,
        predictions: pd.DataFrame,
    ) -> pd.DataFrame | None:
        """返回可选的分组贡献；模型不支持解释时返回 None。"""
```

模型工厂 `scoring/registry.py` 根据配置创建实现：

- `FormulaRiskModel`：第一版正式实现，封装固定回归公式及风险拆解；
- `MachineLearningRiskModel`：第一版只保留接口适配器，不训练、不生成占位预测；未来负责加载已验证模型文件并执行推理；
- 未识别的模型类型、缺失模型文件或特征不兼容必须立即报错。

机器学习训练属于独立工作流，可另行定义 `TrainableRiskModel.fit(features, labels)`，不能强迫无需训练的公式模型实现空 `fit()`。未来机器学习模型至少应遵守：

- 输入使用版本化特征模式；
- 输出 `risk_score` 及其含义、取值范围；
- 保存模型版本、训练数据版本、验证指标和模型文件哈希；
- 如需在现有前端显示“气候/新能源贡献”，应通过 SHAP 等方法把特征贡献聚合为相同两组；
- 无可靠解释结果时，前端隐藏构成占比，不得伪造拆解。

### 8.2 固定公式实现

`scoring/formula.py` 实现 `FormulaRiskModel`，其公式计算保持为纯函数，不读取文件、不访问网络，便于测试。

### 8.3 标准输出字段

每个国家至少输出：

| 字段 | 含义 |
|---|---|
| `iso3` | 国家/地区 ISO3 |
| `country_name` | 展示名称 |
| `pv_share` | 光伏容量占比 |
| `wind_share` | 风电容量占比 |
| `hydro_share` | 水电容量占比 |
| `dry_days` | 连续干日连续指标 |
| `cooling_degree_days` | 制冷度日连续指标 |
| `heating_degree_days` | 采暖度日连续指标 |
| `drought` | 干旱虚拟变量 D |
| `heat` | 高温虚拟变量 H |
| `cold` | 低温虚拟变量 C |
| `climate_contribution` | 气候灾害直接贡献 |
| `renewable_interaction_contribution` | 新能源交互贡献 |
| `risk_score` | 固定公式总风险得分 |
| `model_name` | 风险模型实现名称 |
| `model_version` | 风险模型版本 |
| `climate_share_abs` | 气候绝对贡献占比 |
| `renewable_share_abs` | 新能源绝对贡献占比 |
| `data_quality` | complete / partial / unavailable |
| `energy_release` | GEM 数据版本 |
| `climate_scenario` | 固定气候情景 |

使用公式模型时，同时保留 12 个公式项的单项贡献，供测试和未来解释使用，但第一版前端无需全部展示。

风险计算后必须验证：

```text
abs(risk_score - climate_contribution
    - renewable_interaction_contribution) < 1e-12
```

公式模型不对负风险截断，不把得分强制压缩为 0–1。地图可以采用以 0 为解释基准的色标，同时将原始分数展示在悬停提示中。

## 9. 可视化与前端设计

### 9.1 页面布局

采用单页结构：

```text
┌──────────────────────────────────────────────┐
│ 全球停电相对风险分布                          │
│ 一句话说明 + 最近更新时间                     │
├──────────────────────────────────────────────┤
│                                              │
│              可交互全球地图                   │
│                                              │
├───────────────────────┬──────────────────────┤
│ 选中国家风险得分       │ 风险构成              │
│ 数据完整性             │ 气候 / 新能源占比图    │
│ 气候灾害状态           │ 两项有符号贡献值       │
├───────────────────────┴──────────────────────┤
│ 静态图片预览 / 下载                           │
├──────────────────────────────────────────────┤
│ 数据来源：GEM GIPT、Copernicus CDS            │
└──────────────────────────────────────────────┘
```

页面不设置侧边栏；不设置日期、情景、模型或阈值选择器；不展示复杂调试指标。

### 9.2 交互地图

- 国家级分级设色图；
- 高风险使用暖色，低值使用浅色或冷色，无数据使用灰色；
- 悬停显示国家名、风险得分、两类贡献占比和数据状态；
- 点击国家后更新下方详情卡；
- 默认视图展示全球；
- 支持缩放和平移；
- 色标标题使用“相对风险得分”，不能写“概率”；
- 地图边界使用仓库内边界文件或固定版本的公开 GeoJSON；
- 不通过网络临时加载第三方底图，保证演示稳定。

风险构成建议用两段水平条或简洁环形图表示：

- 气候灾害直接贡献占比；
- 新能源交互贡献占比。

旁边必须显示两项有符号数值，并用“增加风险/降低风险”说明方向，避免绝对贡献占比隐藏负系数的作用。

### 9.3 静态图片

每次成功运行自动生成：

- `power_outage_risk.png`：300 DPI 全球风险地图；
- 可选 `power_outage_risk.svg`：矢量版，用于 PPT；
- 图片包含标题、色标、固定情景和数据来源；
- 缺失数据使用灰色；
- 图片使用与交互地图一致的数据和色阶含义；
- 前端显示 PNG 预览并提供下载按钮。

## 10. 本地自动处理流水线

所有原始数据均已作为本地快照准备好，开发和演示统一运行：

```powershell
uv run python -m outage_prediction.cli build --config config/project.yaml
```

内部阶段：

```text
validate-gem-snapshot  # 校验 data 目录中的本地能源快照
validate-climate-snapshot  # 校验三份本地 NetCDF 及 provenance
validate-raw
build-energy-features
build-climate-features
merge-features
calculate-risk         # 通过 RiskModel 接口调用当前配置的实现
build-geojson
render-static-map
publish
```

要求：

- 每个本地处理阶段可独立重跑；
- 输入未变化时跳过昂贵计算；
- 流水线和前端不得发起任何数据下载网络请求；
- 中间失败时不覆盖 `outputs/latest`；
- 所有输出先写入临时运行目录，通过校验后再原子发布；
- `build` 命令必须完全离线运行，只使用配置中绑定的已验证快照；
- 前端必须标明快照的数据版本和获取日期，不能使用“实时”或“最新”字样；
- 每次运行生成 `run_manifest.json`。

`run_manifest.json` 至少记录：

- 运行 ID、开始/结束时间和状态；
- 代码版本；
- 配置文件哈希；
- GEM release、来源和文件哈希；
- 气候数据集、情景、成员数、时期和文件哈希；
- 最终国家数量、缺失数量和警告；
- 风险模型类型、版本和模型文件哈希（公式模型记录公式版本）；
- 生成文件清单和校验值。

## 11. 测试与质量保障

### 11.1 单元测试

- 固定公式逐项计算正确；
- 总风险等于两类贡献之和；
- 绝对贡献占比之和在有贡献时等于 1；
- 零贡献时占比处理正确；
- 干旱、高温和低温阈值边界正确；
- 温度、降水和容量单位转换正确；
- ISO3 映射不存在静默覆盖；
- 无数据不会被填成零风险。
- 所有风险模型实现都通过统一接口契约测试；
- 配置为 `formula` 时只能创建 `FormulaRiskModel`；
- 配置为机器学习且模型文件缺失时必须失败，不能回退或生成假结果。

### 11.2 数据契约测试

- GEM 必需字段存在；
- 容量非负且可解析；
- 国家—设施 ID 关系符合预期；
- 本地 NetCDF 时间、经纬度、成员数、变量和单位正确；
- 各气候模式覆盖目标时期；
- 国家聚合结果不存在异常无穷值；
- 最终可评分国家数量低于阈值时停止发布。

### 11.3 回归测试

- 使用现有 `parameters.xlsx` 的已知输入验证公式；
- 例如旧数据中的阿富汗输入应复现约 `0.6183841842` 的风险得分；
- 保存少量固定测试样本，不把整套大数据复制到测试目录；
- 可视化输出至少通过文件存在、尺寸、字段和无数据颜色检查。

### 11.4 前端验收

- 页面启动时不触发大型计算或远程下载；
- 无日期选择器；
- 地图可缩放、悬停和点击；
- 选中国家后能看到总风险及两类构成；
- 负贡献的方向表达正确；
- 无数据国家显示为灰色；
- 页面明确列出 GEM GIPT 和 Copernicus CDS；
- 页面展示当前后端绑定的模型名称和版本，但不提供模型切换控件；
- 页面能显示并下载自动生成的 PNG；
- 常规电脑上首次页面渲染目标小于 3 秒。

## 12. 开发阶段与里程碑

### 阶段 0：冻结旧基线

- 备份现有公式、输入样例和结果；
- 把 Excel 公式转写为纯 Python 函数；
- 建立回归测试；
- 将旧 Excel 结果作为公式回归测试基线，并将新计算的 HDD 阈值固定为 3000 ℃·日；
- 确认能源状态口径。

交付物：公式模块、已知样本测试、口径决策记录。

### 阶段 1：项目骨架与环境

- 创建 `pyproject.toml`、`uv.lock` 和配置系统；
- 建立目录、日志、命令行入口和测试框架；
- 初始化 Git，并配置大文件和密钥忽略规则；
- 完成最小 smoke test。

交付物：可安装、可测试、可运行的空流水线。

### 阶段 2：GEM 能源数据流水线

- 校验本地 GIPT Excel 快照及文件哈希；
- 完成 schema 映射、状态筛选和国家聚合；
- 计算 PV、Wind、Hydro 占比；
- 输出能源特征和质量报告。

交付物：`energy_features.parquet`。

### 阶段 3：本地气候数据流水线

- 校验三份本地 CMIP5/RCP4.5 NetCDF 和 provenance；
- 固定提取 2100 年的三类气候指标；
- 完成国家级面积加权和多模式中位数；
- 输出连续指标、虚拟变量和质量报告。

交付物：`climate_features.parquet`。

### 阶段 4：风险计算与发布数据

- 合并能源和气候特征；
- 实现 `RiskModel` 接口、模型工厂和 `FormulaRiskModel`；
- 预留 `MachineLearningRiskModel` 适配器，但不生成机器学习结果；
- 通过统一模型接口计算总风险、两类贡献及占比；
- 处理缺失和特殊国家代码；
- 生成 CSV、Parquet、GeoJSON 和运行清单。

交付物：`country_risk.*` 和 `run_manifest.json`。

### 阶段 5：地图、图片与前端

- 完成交互式世界地图；
- 完成国家详情和风险构成展示；
- 自动生成 PNG/SVG；
- 完成数据来源、更新时间和口径说明；
- 确认前端不存在日期选择器。

交付物：可演示 Streamlit 页面和静态图片。

### 阶段 6：离线构建与验收

- 增加可重复的本地 `build` 命令；
- 验证前端启动和本地重算不会产生任何远程数据请求；
- 测试快照缺失、哈希变化、模型配置错误和 schema 变化；
- 完成 README、部署说明和演示脚本；
- 冻结比赛演示版本。

交付物：本地快照校验、离线重算、一键启动、可复现的比赛版本。

## 13. 完成定义

项目同时满足以下条件才算完成：

1. 在全新隔离环境中按照 README 可以安装依赖；
2. 不配置任何外部 API 凭证也能校验本地能源和气候快照；
3. 原始数据、处理中间表和最终输出有清晰版本关系；
4. 第一版所有正式风险值都由 `FormulaRiskModel` 生成，不再依赖手工 Excel；
5. 气候贡献、新能源交互贡献和总风险严格可加和；
6. 缺失数据不被伪装成零风险；
7. 每次成功运行都生成 GeoJSON、CSV/Parquet、PNG 和运行清单；
8. 前端无日期选择器，页面布局简洁；
9. 地图可交互，并能展示区域风险构成；
10. 页面准确说明数据来源、版本、固定情景和更新时间；
11. 自动化、公式、阈值和前端均有测试；
12. 失败运行不会破坏上一版可展示结果。
13. 未来机器学习实现可以通过 `RiskModel` 接口接入，而无需修改数据流水线和前端主流程。

## 14. 实施前必须确认的决定

HDD 阈值已经确认为大于 3000 ℃·日。剩余一项会实质改变风险分布，必须由项目负责人确认并留下记录：

1. **能源项目状态范围**：仅 operating，还是使用旧项目的多状态兼容口径。

除这两项外，第一版按本文默认方案推进：CMIP5、RCP4.5、固定使用 2100 年、28 模型中位数、国家级输出、默认固定回归模型、预留机器学习接口、Streamlit 单页前端、无日期选择器。

## 15. 数据来源

- 能源设施与装机结构：Global Energy Monitor, Global Integrated Power Tracker；
- 气候预测：Copernicus Climate Change Service, Climate Data Store；
- 国家边界：项目现有世界行政边界文件，后续记录其许可证与版本。

正式发布时，应在 README、前端页脚、静态图片和运行清单中同时保留来源、版本、许可证要求与必要引用。
