# Stock Radar 📡

**A 股全市场选股雷达** — 配置驱动的多策略选股 + 风险检测 + LLM 复盘 + 飞书日报。

> - **25 个选股策略**统一由 `config/selector.config.json` 的 `selectors` 列表驱动（K 线形态战法 + 量化管线 + 量化因子 + 图形评分）
> - **6 个股池策略**（涨停池 / 强势池）由 `config/pool_selector.config.json` 驱动
> - **8 项风险检测**由 `config/risk.config.json` 驱动
> - 可选 **DeepSeek LLM 复盘**（`--llm-analyze`）：对全部初选并集排序点评，Langfuse 可观测
> - 每日 **CI 定时任务**：`选股 → LLM 复盘 → 飞书推送`

## 免责声明

- **股市有风险，入市需谨慎。**
- 本仓库仅供学习与技术研究之用，**不构成任何投资建议**。
- 数据来源与接口可能随平台策略调整而变化，请合法合规使用。

---

## 目录

- [快速开始](#快速开始)
- [环境变量与配置](#环境变量与配置)
  - [环境变量一览](#环境变量一览)
  - [交互式配置向导（推荐）](#交互式配置向导推荐)
  - [LLM 可观测性（Langfuse）](#llm-可观测性langfuse)
- [核心功能](#核心功能)
  - [1. 拉取股票列表](#1-拉取股票列表)
  - [2. 下载历史 K 线](#2-下载历史-k-线)
  - [3. 批量选股](#3-批量选股)
  - [4. 股池选股](#4-股池选股)
  - [5. 风险检测](#5-风险检测)
  - [6. 单只股票检查](#6-单只股票检查)
  - [7. 维护优选列表](#7-维护优选列表)
- [策略体系](#策略体系)
  - [全量策略一览](#全量策略一览)
  - [K 线形态战法](#k-线形态战法)
  - [量化管线 / 因子](#量化管线--因子)
  - [股池策略](#股池策略)
  - [风险检测](#风险检测)
- [选股机制](#选股机制)
- [项目结构](#项目结构)
- [CI / CD](#ci--cd)
- [常见问题](#常见问题)

---

## 快速开始

项目采用 **uv 自洽应用布局**（`stock_radar/` 应用代码 + `config/` 策略配置 + `pyproject.toml` + `uv.lock`），仅在本地 `.venv` 可编辑安装以注册 CLI 入口，不作为 PyPI 库发布。

```bash
cd stock-radar
bash scripts/sync.sh          # uv sync + 应用 patches/（等同 npm patch-package）
bash scripts/sync.sh --group dev   # 含 ruff、pre-commit、patch-package-py
```

**代码检查与格式化（Ruff）：**

```bash
uv run ruff check .              # 静态检查
uv run ruff check --fix .        # 自动修复可修复项
uv run ruff format .             # 格式化
uv run ruff format --check .     # CI 用：仅检查格式是否一致
```

**Git pre-commit（提交前自动检查）：**

```bash
bash scripts/sync.sh --group dev
uv run pre-commit install          # 安装 hooks 到 .git/hooks（每台机器执行一次）
uv run pre-commit run --all-files  # 手动全量跑一遍
```

**CLI 入口（`uv run` 后可直接调用）：**

| 命令                   | 说明                                       |
| ---------------------- | ------------------------------------------ |
| `stock-fetch-list`     | 拉取全市场股票列表                         |
| `stock-fetch-kline`    | 下载日线 K 线 CSV（TickFlow）              |
| `stock-fetch-trend`    | 拉取智图强势股/涨停股池快照                |
| `stock-fetch-pool-kline` | 下载股池标的 K 线（TickFlow → `data-pool/`） |
| `stock-is-trade-date`  | 判断指定日期是否为交易日                   |
| `stock-select`         | 批量选股（全市场）                         |
| `stock-select-pool`    | 股池选股（`pool_selector.config.json`）    |
| `stock-detect-risk`    | 批量风险检测                               |
| `stock-check`          | 单只股票战法检查                           |

> 关键依赖：`pandas`、`tqdm`、`tushare`、`baostock`、`tickflow`、`numpy`、`scipy`、`numba`、`openai`、`lark-oapi`、`langfuse`。

---

## 环境变量与配置

### 环境变量一览

| 变量                  | 说明                                                                            |
| --------------------- | ------------------------------------------------------------------------------- |
| `TUSHARE_TOKEN`       | [TuShare](https://tushare.pro/user/token) 股票列表 Token                        |
| `ZHITU_TOKEN`         | [智图 API](https://www.zhituapi.com/get-free-cert.html) 股池快照（qsgc/ztgc）    |
| `LARK_APP_ID`         | [飞书开放平台](https://open.feishu.cn/app) 应用 App ID                           |
| `LARK_SECRET`         | 飞书应用 App Secret                                                             |
| `LARK_FOLDER_TOKEN`   | 云文档存放文件夹 token                                                          |
| `ME_UNION_ID`         | 接收人的 `union_id`（需 `im:message` + 文档读写权限）                            |
| `DEEPSEEK_API_KEY`    | 可选；`--llm-analyze` DeepSeek 排序复盘                                         |
| `LANGFUSE_PUBLIC_KEY` | 可选；[Langfuse](https://langfuse.com) LLM 观测公钥（见下文）                   |
| `LANGFUSE_SECRET_KEY` | 可选；Langfuse 私钥（与公钥成对配置才启用）                                     |
| `LANGFUSE_BASE_URL`   | 可选；Langfuse 区域，如 `https://jp.cloud.langfuse.com`                         |

### 交互式配置向导（推荐）

在仓库根目录运行（需已安装 [GitHub CLI](https://cli.github.com) 并完成 `gh auth login`）：

```bash
uv run python setup.py
```

向导会：

1. 收集上述变量（密钥输入不回显）
2. 写入本地 `.env`（勿提交到 Git）
3. 通过 `gh secret set` 同步到 GitHub Actions Secrets
4. 可选：立即运行 `check_setup.py` 并发送一条 Lark 测试消息

**手动配置**：复制 [`.env.example`](./.env.example) 为 `.env` 并填入真实值。

**验证配置**：

```bash
uv run python check_setup.py   # 检查 Tushare / TickFlow / 智图连通性 + Lark 测试文档
```

GitHub 上：**Actions → ✅ Check Setup → Run workflow**（需先在仓库 Settings → Secrets 配置同名 Secret）。

### LLM 可观测性（Langfuse）

启用 `--llm-analyze` 后，选股复盘会调用 DeepSeek 对候选标的排序并生成 Markdown 点评。这类 LLM 调用很难只靠日志排查问题 — [Langfuse](https://langfuse.com) 提供了很好的可观测性：Web 控制台里能看到完整 trace、每轮 generation、token 用量和费用，方便对比模型表现、定位「只输出 reasoning 没有正文」等异常。

Trace 层级：`analyze-picks` → `deepseek-complete` → `deepseek-round-N-{initial|reasoning|truncation}` → `deepseek-generation-N-*`。默认 `reasoning_effort=low`，减少 thinking token 占用。

**完全可选**：

- 同时设置 `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY` → 自动上报（标签 `stock-radar`）
- 任一未设置 → 零开销跳过，不影响选股与飞书推送

```bash
# .env 或 GitHub Actions Secrets
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://jp.cloud.langfuse.com   # 按你的 Langfuse 区域填写
```

注册项目：[langfuse.com/cloud](https://langfuse.com/cloud) → **Settings → API Keys**。`uv run python setup.py` 会询问是否写入上述变量。

---

## 核心功能

### 1. 拉取股票列表

从 TuShare 获取所有 A 股股票列表，保存到 CSV 文件。建议定期更新，确保数据准确。

```bash
uv run stock-fetch-list
```

### 2. 下载历史 K 线

- **数据源**：TickFlow 日线，**前复权 qfq**（Tushare 仅用于股票列表）。
- **保存策略**：每只股票**全量覆盖写入** `./data/XXXXXX.csv`。
- **频控处理**：命中「访问频繁/429/403…」将睡眠约 600s 并重试，最多 3 次。
- **股票清单**：默认 `stocklist.good.csv`（优选池）；全量数据见 `stock_radar/stocklist.total.csv`。

```bash
uv run stock-fetch-kline \
  --start 20240101 \
  --end today \
  --stocklist ./stocklist.good.csv \
  --exclude-boards gem star bj \
  --out ./data
```

**参数说明**

| 参数               | 默认值                  | 说明                                                                          |
| ------------------ | ----------------------- | ----------------------------------------------------------------------------- |
| `--start`          | `20250101`              | 起始日期，格式 `YYYYMMDD` 或 `today`                                          |
| `--end`            | `today`                 | 结束日期，格式同上                                                            |
| `--stocklist`      | `./stocklist.good.csv`  | 股票清单 CSV 路径（含 `ts_code` 或 `symbol`）                                 |
| `--exclude-boards` | `["gem", "star", "bj"]` | 排除板块：`gem`(创业板) / `star`(科创板) / `bj`(北交所)，可多选               |
| `--out`            | `./data`                | 输出目录（自动创建）                                                          |

**输出 CSV 列**：`date, open, close, high, low, volume`（按日期升序）。

### 3. 批量选股

批量对股票池执行 `selector.config.json` 中配置的全部策略，输出符合条件的股票。

```bash
# 基础用法
uv run stock-select --data-dir ./data --date 2025-09-10

# 生产 / CI 推荐（含飞书、LLM 复盘）
uv run stock-select --data-dir ./data --send-lark --llm-analyze
```

> `--date` 可省略，默认取数据中的最后交易日。

**参数说明**

| 参数            | 默认值         | 说明                                        |
| --------------- | -------------- | ------------------------------------------- |
| `--data-dir`    | 必填           | K 线行情目录                                |
| `--date`        | 数据最后交易日 | 选股交易日                                  |
| `--send-lark`   | 关闭           | 生成飞书云文档并推送链接                    |
| `--llm-analyze` | 关闭           | DeepSeek 对初选结果排序复盘（需 API Key）   |
| `--llm-max`     | `20`           | 送入 LLM 的最大标的数                       |

### 4. 股池选股

基于智图强势股池（qsgc）/ 涨停股池（ztgc）快照 + 股池 K 线，执行 `pool_selector.config.json` 中的 6 个策略。

```bash
# 先抓快照与 K 线
uv run stock-fetch-trend --date today --out ./trend
uv run stock-fetch-pool-kline --trend-dir ./trend --out ./data-pool

# 再选股
uv run stock-select-pool \
  --data-dir ./data-pool --trend-dir ./trend \
  --send-lark --llm-analyze
```

### 5. 风险检测

对持仓或候选池批量跑 `risk.config.json` 中的 8 项风险信号，输出按命中风险条数聚合排序：

```bash
uv run stock-detect-risk --data-dir ./data --send-lark
```

### 6. 单只股票检查

对指定股票代码检查是否命中某一战法：

```bash
uv run stock-check --data-dir ./data --symbol 002594
```

**参数说明**

| 参数         | 默认值 | 说明                    |
| ------------ | ------ | ----------------------- |
| `--data-dir` | 必填   | K 线行情目录            |
| `--symbol`   | 必填   | 需要检查的股票代码，6位 |

### 7. 维护优选列表

将新股票代码添加到 `stocklist.good.csv`：

```bash
uv run python stock_radar/update_to_goodlist.py --stocklist ./stocklist.good.csv
```

---

## 策略体系

### 全量策略一览

所有选股策略在 **`config/selector.config.json`** 的 `selectors` 数组中定义，**全部启用**（无 `activate` 开关）。默认实现位于 `stock_radar/strategy/` 下与类同名模块；跨模块策略通过 `"module"` 字段指定。

| 类别         | 别名             | 类                              | 实现模块            |
| ------------ | ---------------- | ------------------------------- | ------------------- |
| K 线形态战法 | 少妇战法         | `BBIKDJSelector`                | `strategy.bbi_kdj`  |
| K 线形态战法 | 黄金坑战法       | `GoldPitSelector`               | `strategy.gold_pit` |
| K 线形态战法 | 企稳战法         | `SupportLevelSelector`          | `strategy.support_level` |
| K 线形态战法 | SuperB1战法      | `SuperB1Selector`               | `strategy.super_b1` |
| K 线形态战法 | 补票战法         | `BBIShortLongSelector`          | `strategy.bbi_short_long` |
| K 线形态战法 | 填坑战法         | `PeakKDJSelector`               | `strategy.peak_kdj` |
| K 线形态战法 | 上穿60放量战法   | `MA60CrossVolumeWaveSelector`   | `strategy.ma60_cross_volume` |
| K 线形态战法 | 暴力K战法        | `BigBullishVolumeSelector`      | `strategy.big_bullish_volume` |
| K 线形态战法 | 均值突破战法     | `MACrossSelector`               | `strategy.ma_cross` |
| K 线形态战法 | 震荡上攻战法     | `OscillationGrowthSelector`     | `strategy.oscillation_growth` |
| K 线形态战法 | 均线放量战法     | `MaVolumeSelector`              | `strategy.ma_volume` |
| K 线形态战法 | RPS动量突破      | `RpsBreakoutSelector`           | `strategy.rps_breakout` |
| K 线形态战法 | 海龟突破战法     | `TurtleTradeSelector`           | `strategy.turtle_trade` |
| K 线形态战法 | 高旗形整理       | `HighTightFlagSelector`         | `strategy.high_tight_flag` |
| K 线形态战法 | 涨停洗盘战法     | `LimitUpShakeoutSelector`       | `strategy.limit_up_shakeout` |
| K 线形态战法 | 趋势跌停错杀     | `UptrendLimitDownSelector`      | `strategy.uptrend_limit_down` |
| K 线形态战法 | 定增公告监控     | `PrivatePlacementSelector`      | `strategy.private_placement` |
| 量化管线     | B1战法           | `B1Selector`                    | `strategy.pipeline` |
| 量化管线     | 砖型图战法       | `BrickChartSelector`            | `strategy.pipeline` |
| 量化因子     | 动量因子         | `MomentumSelector`              | `strategy.quant`    |
| 量化因子     | MACD金叉         | `MACDGoldenCrossSelector`       | `strategy.quant`    |
| 量化因子     | 布林均值回归     | `BollingerMeanReversionSelector`| `strategy.quant`    |
| 量化因子     | 唐奇安突破       | `DonchianBreakoutSelector`      | `strategy.quant`    |
| 量化因子     | 双均线金叉       | `DualMAGoldenCrossSelector`     | `strategy.quant`    |
| 图形评分     | K线图形评分      | `ChartScoreSelector`            | `strategy.chart_score` |

**新增策略**：在 `selectors` 中追加条目，必要时指定 `"module"`，实现类需提供 `select(date, data) -> list[str]`。

### K 线形态战法

> 文中「窗口」均指交易日数量。此类策略共用「知行线」约束：**收盘 > 长期线 且 短期线 > 长期线**（部分策略当日只要求短期线 > 长期线）。

**少妇战法（BBIKDJ）**：价格波动受约束（`high/low-1 ≤ price_range_pct`）+ BBI 上升（容忍分位内回撤）+ KDJ 低位（J < 阈值 或 ≤ 分位）+ `DIF > 0` + 有效上穿 MA60 + 知行约束。核心参数：`j_threshold=15`、`max_window=120`、`price_range_pct=1`、`j_q_threshold=0.1`。

**黄金坑战法（GoldPit）**：识别 CCI 深度超卖形成的「黄金坑」形态，捕捉坑底反转。

**企稳战法（SupportLevel）**：基于支撑位企稳形态，寻找回调后获得支撑的标的。

**SuperB1战法**：`lookback_n` 窗内某日 `t_m` 满足少妇战法 → 区间波动率受限 → 当日下跌 ≥ `price_drop_pct` → 当日 J 低位 → 知行约束（`t_m` 当日收盘 > 长期线；当日仅需短期线 > 长期线）。核心参数：`lookback_n=10`、`close_vol_pct=0.02`、`price_drop_pct=0.02`。

**补票战法（BBIShortLong）**：BBI 上升 + 最近 `m` 日内长 RSV 全 ≥ 上阈值、短 RSV 出现「先 ≥ upper 再 < lower」结构、当日短 RSV ≥ upper + `DIF > 0` + 知行约束。核心参数：`n_short=5`、`n_long=21`、`upper_rsv_threshold=75`、`lower_rsv_threshold=25`。

**填坑战法（PeakKDJ）**：基于 `open/close` 峰值（`scipy.signal.find_peaks`）选最新峰与前方有效参照峰（`oc_t > oc_(t-n)` 且参照峰高于区间最低收盘），当日收盘与参照峰波动率受限 + J 低位 + 知行约束。核心参数：`j_threshold=10`、`fluc_threshold=0.03`、`gap_threshold=0.2`。

**上穿60放量战法（MA60CrossVolumeWave）**：J 低位 + 近窗内有效上穿 MA60 + 上穿日到区间内 High 最大日组成的上涨波段平均量 ≥ `vol_multiple` × 上穿前窗口均量 + MA60 近期回归斜率 > 0 + 知行约束。核心参数：`lookback_n=25`、`vol_multiple=1.8`、`ma60_slope_days=5`。

**暴力K战法（BigBullishVolume）**：当日长阳（涨幅 > `up_pct_threshold`）+ 上影线短（过滤冲高回落假阳线）+ 放量突破（当日量 ≥ `vol_multiple` × 前 n 日均量）+ 贴近知行短线不过热（`Close < ZXDQ × close_lt_zxdq_mult`）+ 可选收阳约束。核心参数：`up_pct_threshold=0.06`、`upper_wick_pct_max=0.02`、`vol_multiple=2.5`、`vol_lookback_n=20`。意在捕捉「刚刚放量启动的强势阳线，但尚未远离短期均线、仍具延续空间的个股」。

**其余战法**：均值突破（MA 均线突破）、震荡上攻（区间震荡后上攻）、均线放量、RPS 动量突破、海龟突破、高旗形整理（杯柄/旗形整理形态）、涨停洗盘、趋势跌停错杀、定增公告监控。逻辑详见对应 `strategy/*.py`。

### 量化管线 / 因子

**B1战法**：KDJ 低位分位 + 知行线 + 周线多头排列 + 最大量日非阴线；需足够历史 K 线（`zx_m4=114` 时需 ≥114 根）。

**砖型图战法**：砖型图形态 + 知行线 + 周线多头；偏趋势启动捕捉。

**量化因子**（`strategy/quant.py`）：动量因子、MACD 金叉、布林均值回归、唐奇安突破、双均线金叉 — 主流量化信号，参数见 config。

**K线图形评分**（`strategy/chart_score.py`）：对全市场扫描，K 线四维度纯计算加权（趋势/位置/量价/异动），`total_score ≥ pass_threshold`（默认 3.7）即命中；与其他 selector 无特殊耦合。

### 股池策略

由 `config/pool_selector.config.json` 驱动（`stock_radar/strategy/pool.py`），基于智图股池快照：

| 别名     | 类                          | 股池 | 逻辑要点                 |
| -------- | --------------------------- | ---- | ------------------------ |
| 早盘封板 | `EarlySealSelector`         | ztgc | 首封时间早 + 炸板少     |
| 连板延续 | `ContinuationBoardSelector` | ztgc | 连板数 ≥ 2、炸板 ≤ 1    |
| 首板龙头 | `FirstBoardLeaderSelector`  | ztgc | 首板封板早 + 换手适中   |
| 新高强势 | `NewHighMomentumSelector`   | qsgc | 涨速/量比强势           |
| 贴近涨停 | `NearLimitMomentumSelector` | qsgc | 距涨停近 + 振幅放大     |
| 强势放量 | `VolumeBreakoutSelector`    | qsgc | 换手充足放量             |

### 风险检测

由 `config/risk.config.json` 驱动，实现位于 `stock_radar/strategy/risk.py`：

| 信号                  | 说明                             |
| --------------------- | -------------------------------- |
| ATR Volatility        | 相对波动率过高                   |
| RSI Extremes          | 超买/超卖极端                    |
| MA Decline            | 均线空头排列且长期均线走弱       |
| Volume Selloff        | 放量下跌                         |
| Drawdown              | 相对近期高点回撤过大             |
| Gap Down              | 跳空低开                         |
| MACD Bearish          | MACD 死叉或空头动能              |
| Top Trap              | CCI 超买 + 顶部陷阱信号          |

---

## 选股机制

`stock-select` 流水线（`stock_radar/select_stock.py`）：

```
load_data_folder → load_selectors → 各 Selector.select()（含 K线图形评分等）
       ↓
  [--llm-analyze] DeepSeek 对全部初选并集排序复盘
       ↓
  [--send-lark] 飞书云文档 + 机器人通知
```

1. **`load_data_folder`**：从 `--data-dir` 读取 CSV，归一化 `date`，确定交易日。
2. **`load_selectors`**：读取 `selector.config.json` 的 `selectors`，按 `class`（及可选 `module`）实例化，**全部运行**。
3. **并行扫描**：各 Selector 对全市场（或自身逻辑范围）调用 `select(date, data)`，汇总为 `all_results`。
4. **LLM 复盘**（`--llm-analyze`）：对全部 selector 初选并集（受 `--llm-max` 限制）调用 DeepSeek 排序与 keep/flag/veto 点评。
5. **飞书报告**（`--send-lark`）：各策略命中列表 + LLM 段落，创建云文档并推送链接。

---

## 项目结构

```bash
.
├── pyproject.toml / uv.lock          # 项目依赖与 CLI 入口
├── setup.py                          # 交互式配置向导（.env + GitHub Secrets）
├── check_setup.py                    # 验证环境变量 / 数据源 / Lark 测试消息
├── stock_radar/                      # 应用代码包
│   ├── fetch_stocklist.py            # 全市场股票列表
│   ├── fetch_kline.py                # K 线下载（TickFlow，前复权）
│   ├── fetch_trend_pools.py          # 智图股池快照（qsgc/ztgc）
│   ├── fetch_pool_kline.py           # 股池标的 K 线下载
│   ├── select_stock.py               # 全市场选股主入口
│   ├── select_pool.py                # 股池选股主入口
│   ├── detect_risk.py                # 风险检测主入口
│   ├── check_code.py                 # 单只股票战法检查
│   ├── is_trade_date.py              # 交易日判断
│   ├── core/                         # 基础工具（registry / logger / paths / compute…）
│   ├── market/                       # 数据源适配（TickFlow / Tushare / baostock / 智图 / 雪球）
│   ├── strategy/                     # 策略实现（25 selector + risk + pool + loader）
│   ├── llm/                          # DeepSeek 复盘 + Langfuse 追踪
│   └── notify/                       # 飞书云文档 / 机器人通知 / Markdown 报告
├── config/                           # 策略配置（与代码分离）
│   ├── selector.config.json          # 选股策略（统一 selectors 列表，25 个）
│   ├── pool_selector.config.json     # 股池选股策略（6 个）
│   └── risk.config.json              # 风险检测策略（8 项）
├── scripts/smoke_test.py             # 包冒烟测试
├── .github/workflows/                # CI / CD
│   ├── daily-stock-trade.yml         # 每日选股 + 风控（定时 + 手动触发）
│   ├── lint.yml                      # Ruff lint + format + 冒烟测试
│   └── check_setup.yml               # 配置检查（手动触发）
├── .pre-commit-config.yaml           # 提交前自动检查
├── data/                             # K 线行情 CSV 输出目录（gitignore）
├── stocklist.good.csv                # 优选股票池（默认选股清单）
└── stock_radar/stocklist.total.csv   # 全量股票池（5000+ 只）
```

---

## CI / CD

- **`daily-stock-trade.yml`**：工作日 07:00（UTC+8）定时触发，也可手动。流程：交易日判断 → 拉全市场 K 线 → 拉智图股池快照与 K 线 → 全市场选股（LLM 复盘 + 飞书）→ 股池选股（LLM 复盘 + 飞书）。
- **`lint.yml`**：push/PR 时运行 Ruff lint + format 检查 + 冒烟测试。
- **`check_setup.yml`**：手动触发，验证 Secrets 与数据源连通性。

Secrets 通过 `uv run python setup.py` 一次性写入（`gh secret set`），或手动在仓库 **Settings → Secrets and variables → Actions** 配置。

---

## 常见问题

**Q0：飞书收不到消息？**

1. 运行 `uv run python check_setup.py`，确认环境变量与 Lark 测试文档通知均成功。
2. 确认应用已发布、已开通 `docx:document` / `docx:document:create` / 云文档权限相关 scope，机器人可发消息，且 `ME_UNION_ID` 为接收人 union_id（非 open_id）。
3. GitHub Actions 需在仓库 Secrets 中配置 `TUSHARE_TOKEN`、`ZHITU_TOKEN`、`DEEPSEEK_API_KEY`（若启用 LLM）、`LARK_APP_ID`、`LARK_SECRET`、`LARK_FOLDER_TOKEN`、`ME_UNION_ID`（可用 `setup.py` 一次性写入）。若启用 LLM 复盘并需要 trace，可额外配置 `LANGFUSE_PUBLIC_KEY`、`LANGFUSE_SECRET_KEY`、`LANGFUSE_BASE_URL`（见 [LLM 可观测性](#llm-可观测性langfuse)）。

**Q1：为什么抓取会「卡住很久」？**

可能命中 Tushare 频控或网络封禁。脚本检测到典型关键字（如「访问频繁/429/403」）时，会进入**长冷却（默认 600s）** 再重试。

**Q2：为什么不做增量合并？**

考虑采用增量更新会遇到前复权的问题，本版选择**每次全量覆盖写入**。

**Q3：创业板/科创板/北交所如何排除？**

运行时使用 `--exclude-boards gem star bj`，或按需选择其一/其二。

**Q4：B1 / 砖型图为什么经常 0 结果？**

条件较严，且 B1 的知行线 `zx_m4=114` 需要单股至少约 114 根 K 线；本地若只抓了较短区间会算出 NaN。CI 从 `20240101` 拉数一般足够。可与「少妇战法」等结果对照——后者条件略宽。
