## 免责声明

- **股市有风险，入市需谨慎。**
- 本仓库仅供学习与技术研究之用，**不构成任何投资建议**。
- 数据来源与接口可能随平台策略调整而变化，请合法合规使用。
- 致谢 [**@Zettaranc**](https://b23.tv/JxIOaNE) 在 Bilibili 的无私分享
- 致谢 [**@JeffreyZZ331**](https://b23.tv/Ysrdfas) 的开源项目 [StockTradebyZ](https://github.com/SebastienZh/StockTradebyZ)。

---

# Z哥战法的 Python 实现

> **更新时间：2026-06-17**
>
> - 选股策略统一由 `config/selector.config.json` 的 **`selectors`** 列表驱动（Z 战法 + B1/砖型图 + 量化因子 + K线图形评分，共 17 个）
> - `stock-select` 可选 **`--llm-analyze`**（DeepSeek 对全部初选并集复盘排序）
> - 每日 CI：`Selector → LLM 复盘 → 飞书`

## 目录

- [快速上手](#快速上手)
  - [环境与依赖](#环境与依赖)
  - [环境变量与飞书（推荐 setup 向导）](#环境变量与飞书推荐-setup-向导)
  - [LLM 可观测性（Langfuse）](#llm-可观测性langfuse)
- [核心功能](#核心功能)
  - [1. 获取股票列表](#1-获取股票列表)
  - [2. 下载历史 K 线（qfq，日线）](#2-下载历史-k-线qfq日线)
  - [3. 运行选股](#3-运行选股)
  - [4. 检查单只股票](#4-检查单只股票)
  - [5. 添加股票到优选列表](#5-添加股票到优选列表)
- [策略一览](#策略一览)
- [内置策略（Selector）](#内置策略selector)
  - [1. BBIKDJSelector（少妇战法）](#1-bbikdjselector少妇战法)
  - [2. SuperB1Selector（SuperB1战法）](#2-superb1selectorsuperb1战法)
  - [3. BBIShortLongSelector（补票战法）](#3-bbishortlongselector补票战法)
  - [4. PeakKDJSelector（填坑战法）](#4-peakkdjselector填坑战法)
  - [5. MA60CrossVolumeWaveSelector（上穿60放量战法）](#5-ma60crossvolumewaveselector上穿60放量战法)
  - [6. BigBullishVolumeSelector（暴力K战法）](#6-bigbullishvolumeselector暴力k战法)
- [项目结构](#项目结构)
- [选股机制](#选股机制)
- [Risk Selectors（风险检测）](#risk-selectors-风险检测)
- [常见问题](#常见问题)

---

## 快速上手

### 环境与依赖

本项目为 **uv 自洽应用布局**（`stock_trade_z/` 应用代码 + `config/` 策略配置 + `pyproject.toml` + `uv.lock`）。仅在本地 `.venv` 可编辑安装以注册 CLI 入口，不作为 PyPI 库发布。

```bash
cd /path/to/stock_trade_z
uv sync               # 创建 .venv、安装依赖并注册 CLI
uv sync --group dev   # 含 ruff（lint + format）
```

**代码检查与格式化（[Ruff](https://docs.astral.sh/ruff/)）：**

```bash
uv run ruff check .              # 静态检查
uv run ruff check --fix .        # 自动修复可修复项
uv run ruff format .             # 格式化
uv run ruff format --check .     # CI 用：仅检查格式是否一致
```

VS Code/Cursor：安装 [Ruff 扩展](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff)，本项目 `.vscode/settings.json` 已配置保存时格式化与 import 整理。

**Git pre-commit（提交前自动检查）：**

```bash
uv sync --group dev
uv run pre-commit install          # 安装 hooks 到 .git/hooks（每台机器执行一次）
uv run pre-commit run --all-files  # 手动全量跑一遍
```

每次 `git commit` 会自动执行：尾随空格/EOF、YAML 检查、Ruff lint（含 `--fix`）与 Ruff format。配置见 [`.pre-commit-config.yaml`](./.pre-commit-config.yaml)。

**CLI 入口（`uv run` 后可直接调用）：**

| 命令                     | 说明                                         |
| ------------------------ | -------------------------------------------- |
| `stock-fetch-list`       | 拉取全市场股票列表                           |
| `stock-fetch-kline`      | 下载日线 K 线 CSV（TickFlow）                |
| `stock-fetch-trend`      | 拉取智图强势股/涨停股池快照                  |
| `stock-fetch-pool-kline` | 下载股池标的 K 线（TickFlow → `data-pool/`） |
| `stock-select`           | 批量选股（正常战法）                         |
| `stock-select-pool`      | 股池选股（`pool_selector.config.json`）      |
| `stock-detect-risk`      | 批量风险检测                                 |
| `stock-check`            | 单只股票战法检查                             |

> 关键依赖：`pandas`, `tqdm`, `tushare`, `baostock`, `numpy`, `scipy`。

### 环境变量与飞书（推荐 setup 向导）

选股 / 风控 / 股池选股支持 `--send-lark`：在飞书云文档中生成 Markdown 报告，再由机器人发送文档链接。每日 GitHub Actions 工作流使用相同配置。需要准备：

| 变量                | 说明                                                                          |
| ------------------- | ----------------------------------------------------------------------------- |
| `TUSHARE_TOKEN`     | [TuShare](https://tushare.pro/user/token) 股票列表 Token                      |
| `ZHITU_TOKEN`       | [智图 API](https://www.zhituapi.com/get-free-cert.html) 股池快照（qsgc/ztgc） |
| `LARK_APP_ID`       | [飞书开放平台](https://open.feishu.cn/app) 应用 App ID                        |
| `LARK_SECRET`       | 飞书应用 App Secret                                                           |
| `LARK_FOLDER_TOKEN` | 云文档存放文件夹 token（见 [lark-doc.md](./lark-doc.md)）                     |
| `ME_UNION_ID`       | 接收人的 `union_id`（需 `im:message` + 文档读写权限）                         |
| `DEEPSEEK_API_KEY`  | 可选；`--llm-analyze` DeepSeek 排序复盘                                       |
| `LANGFUSE_PUBLIC_KEY` | 可选；[Langfuse](https://langfuse.com) LLM 观测公钥（见下文）                 |
| `LANGFUSE_SECRET_KEY` | 可选；Langfuse 私钥（与公钥成对配置才启用）                                   |
| `LANGFUSE_BASE_URL`   | 可选；Langfuse 区域，如 `https://jp.cloud.langfuse.com`                       |

#### 方式一：交互式配置向导（推荐）

在仓库根目录运行（需已安装 [GitHub CLI](https://cli.github.com) 并完成 `gh auth login`）：

```bash
uv run python setup.py
```

向导会：

1. 收集上述变量（密钥输入不回显）
2. 写入本地 `.env`（勿提交到 Git）
3. 通过 `gh secret set` 同步到 GitHub Actions Secrets
4. 可选：立即运行 `check_setup.py` 并发送一条 Lark 测试消息

#### 方式二：手动配置 `.env`

复制 [`.env.example`](./.env.example) 为 `.env` 并填入真实值：

```bash
cp .env.example .env
# 编辑 .env
```

#### 验证配置

本地检查 Tushare / TickFlow / 智图股池连通性，并发送 Lark 测试文档通知：

```bash
uv run python check_setup.py
```

GitHub 上：**Actions → ✅ Check Setup → Run workflow**（需先在仓库 Settings → Secrets 中配置同名 Secret）。

#### 临时环境变量（仅当前 shell）

```bash
# macOS / Linux
export TUSHARE_TOKEN=你的token
export LARK_APP_ID=...
export LARK_SECRET=...
export LARK_FOLDER_TOKEN=...
export ME_UNION_ID=...

# Windows (PowerShell)
$env:TUSHARE_TOKEN = "你的token"
```

### LLM 可观测性（Langfuse）

启用 `--llm-analyze` 后，选股复盘会调用 DeepSeek 对候选标的排序并生成 Markdown 点评。这类 LLM 调用很难只靠日志排查问题 — **[Langfuse](https://langfuse.com) 提供了很好的可观测性**：在 Web 控制台里能看到完整 trace、每轮 generation、token 用量和费用，方便对比模型表现、定位「只输出 reasoning 没有正文」等异常。

集成方式与 `ai-dispatch` 相同，**完全可选**：

- 同时设置 `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY` → 自动上报（标签 `stock-trade-z`）
- 任一未设置 → 零开销跳过，不影响选股与飞书推送

```bash
# .env 或 GitHub Actions Secrets
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://jp.cloud.langfuse.com   # 按你的 Langfuse 区域填写
```

`uv run python setup.py` 会询问是否写入上述变量；也可参考 [`.env.example`](./.env.example)。每日 CI workflow 已透传这些 Secret 到 LLM 步骤。

注册项目：[langfuse.com/cloud](https://langfuse.com/cloud) → **Settings → API Keys**。

#### 带 Lark 推送的运行示例

```bash
uv run stock-select --data-dir ./data --send-lark --llm-analyze
uv run stock-select-pool --data-dir ./data-pool --trend-dir ./trend --send-lark --llm-analyze
uv run stock-detect-risk --data-dir ./data --send-lark
```

## 核心功能

### 1. 获取股票列表

从 TuShare 获取所有 A 股股票列表，保存到 CSV 文件。建议定期更新，确保数据准确。

```bash
uv run stock-fetch-list
```

### 2. 下载历史 K 线（qfq，日线）

- **数据源**：TickFlow 日线，**前复权 qfq**（Tushare 仅用于股票列表）。
- **保存策略**：每只股票**全量覆盖写入** `./data/XXXXXX.csv`。
- **并发抓取**：默认 6 线程；支持封禁冷却（命中「访问频繁/429/403…」将睡眠约 600s 并重试，最多 3 次）。
- **频控处理**：低积分的 token 可能每分钟可调用的接口次数有限，提前对请求做了睡眠处理
- **stocklist.good.csv**：经过初步筛选的股票文件。如需全量的数据，请查看 [stocklist.total.csv](./stock_trade_z/stocklist.total.csv) 。

```bash
uv run stock-fetch-kline \
  --start 20240101 \
  --end today \
  --stocklist ./stocklist.good.csv \
  --exclude-boards gem star bj \
  --out ./data \
  --workers 6 \
  --chunk 48 \
  --chunk_sleep 65
```

**参数说明**

| 参数               | 默认值                  | 说明                                                                                               |
| ------------------ | ----------------------- | -------------------------------------------------------------------------------------------------- |
| `--start`          | `20250101`              | 起始日期，格式 `YYYYMMDD` 或 `today`                                                               |
| `--end`            | `today`                 | 结束日期，格式同上                                                                                 |
| `--stocklist`      | `./stocklist.good.csv`  | 股票清单 CSV 路径（含 `ts_code` 或 `symbol`）                                                      |
| `--exclude-boards` | `["gem", "star", "bj"]` | 排除板块，枚举：`gem`(创业板 300/301) / `star`(科创板 688) / `bj`(北交所 .BJ / 4/8 开头)。可多选。 |
| `--out`            | `./data`                | 输出目录（自动创建）                                                                               |
| `--workers`        | `6`                     | 并发线程数                                                                                         |
| `--chunk`          | `48`                    | 单次请求的任务数，多 chunk 有助于逃过请求频控                                                      |
| `--chunk_sleep`    | `65`                    | 每次请求之间的睡眠时间，用来逃过请求频控                                                           |

**输出 CSV 列**：`date, open, close, high, low, volume`（按日期升序）。

**抓取与重试**：每支股票最多 3 次尝试；疑似限流/封禁触发 **600s 冷却**；其它异常采用递进式短等候重试（15s×尝试次数）。

### 3. 运行选股

批量对股票池执行 `selector.config.json` 中配置的全部策略，输出符合条件的股票。

```bash
uv run stock-select --data-dir ./data --date 2025-09-10
```

生产 / CI 推荐（含飞书、LLM 复盘）：

```bash
uv run stock-select \
  --data-dir ./data \
  --send-lark \
  --llm-analyze
```

> `--date` 可省略，默认取数据中的最后交易日。

**参数说明**

| 参数            | 默认值         | 说明                                      |
| --------------- | -------------- | ----------------------------------------- |
| `--data-dir`    | 必填           | K 线行情目录                              |
| `--date`        | 数据最后交易日 | 选股交易日                                |
| `--send-lark`   | 关闭           | 生成飞书云文档并推送链接                  |
| `--llm-analyze` | 关闭           | DeepSeek 对初选结果排序复盘（需 API Key） |
| `--llm-max`     | `20`           | 送入 LLM 的最大标的数                     |

### 4. 检查单只股票

对指定股票代码进行检查，查看是否命中某一战法。

```bash
uv run stock-check \
  --data-dir ./data \
  --symbol 002594
```

**参数说明**

| 参数         | 默认值 | 说明                    |
| ------------ | ------ | ----------------------- |
| `--data-dir` | 必填   | K线行情目录             |
| `--symbol`   | 必填   | 需要检查的股票代码，6位 |

### 5. 添加股票到优选列表

将新的股票代码添加到 `stocklist.good.csv` 文件中。

```bash
uv run python stock_trade_z/update_to_goodlist.py \
  --stocklist ./stocklist.good.csv
```

**参数说明**

| 参数          | 默认值 | 说明                  |
| ------------- | ------ | --------------------- |
| `--stocklist` | 必填   | 股票列表 CSV 文件路径 |

---

## 策略一览

所有策略在 **`config/selector.config.json`** 的 `selectors` 数组中定义，**全部启用**（无 `activate` 开关）。默认实现模块为 `lib/selector.py`；跨模块策略通过 `"module"` 字段指定。

| 别名           | 类                               | 模块                 | 类别     |
| -------------- | -------------------------------- | -------------------- | -------- |
| 少妇战法       | `BBIKDJSelector`                 | `selector`           | Z 战法   |
| 黄金坑战法     | `GoldPitSelector`                | `selector`           | Z 战法   |
| 企稳战法       | `SupportLevelSelector`           | `selector`           | Z 战法   |
| SuperB1战法    | `SuperB1Selector`                | `selector`           | Z 战法   |
| 补票战法       | `BBIShortLongSelector`           | `selector`           | Z 战法   |
| 填坑战法       | `PeakKDJSelector`                | `selector`           | Z 战法   |
| 上穿60放量战法 | `MA60CrossVolumeWaveSelector`    | `selector`           | Z 战法   |
| 暴力K战法      | `BigBullishVolumeSelector`       | `selector`           | Z 战法   |
| 均值突破战法   | `MACrossSelector`                | `selector`           | Z 战法   |
| B1战法         | `B1Selector`                     | `pipeline_selectors` | 量化管线 |
| 砖型图战法     | `BrickChartSelector`             | `pipeline_selectors` | 量化管线 |
| 动量因子       | `MomentumSelector`               | `quant_selectors`    | 量化因子 |
| MACD金叉       | `MACDGoldenCrossSelector`        | `quant_selectors`    | 量化因子 |
| 布林均值回归   | `BollingerMeanReversionSelector` | `quant_selectors`    | 量化因子 |
| 唐奇安突破     | `DonchianBreakoutSelector`       | `quant_selectors`    | 量化因子 |
| 双均线金叉     | `DualMAGoldenCrossSelector`      | `quant_selectors`    | 量化因子 |
| K线图形评分    | `ChartScoreSelector`             | `chart_score`        | 量化因子 |

**B1战法**（`pipeline_selectors`）：KDJ 低位分位 + 知行线 + 周线多头排列 + 最大量日非阴线；需足够历史 K 线（`zx_m4=114` 时需 ≥114 根）。

**砖型图战法**（`pipeline_selectors`）：砖型图形态 + 知行线 + 周线多头；偏趋势启动捕捉。

**K线图形评分**（`chart_score`）：对全市场扫描，K 线四维度纯计算加权（趋势/位置/量价/异动），`total_score ≥ pass_threshold`（默认 3.7）即命中；与其他 selector 无特殊耦合。

新增策略：在 `selectors` 中追加条目，必要时指定 `"module"`，实现类需提供 `select(date, data) -> list[str]`。

---

## 内置策略（Selector）

> **提示**：文中“窗口”均指交易日数量。实际实现均已替换为最新代码逻辑。

### 1. BBIKDJSelector（少妇战法）

核心逻辑：

- **价格波动约束**：最近 `max_window` 根收盘价的波动（`high/low-1`）≤ `price_range_pct`；
- **BBI 上升**：`bbi_deriv_uptrend`，允许一阶差分在 `bbi_q_threshold` 分位内为负（容忍回撤）；
- **KDJ 低位**：当日 J 值 **< `j_threshold`** 或 **≤ 最近 `max_window` 的 `j_q_threshold` 分位**；
- **MACD**：`DIF > 0`；
- **MA60 条件**：当日 `close ≥ MA60` 且最近 `max_window` 内存在“**有效上穿 MA60**”；
- **知行当日约束**：**收盘 > 长期线** 且 **短期线 > 长期线**。

`selector.config.json` 预设（与示例一致）：

```json
{
  "class": "BBIKDJSelector",
  "alias": "少妇战法",
  "params": {
    "j_threshold": 15,
    "bbi_min_window": 20,
    "max_window": 120,
    "price_range_pct": 1,
    "bbi_q_threshold": 0.2,
    "j_q_threshold": 0.1
  }
}
```

### 2. SuperB1Selector（SuperB1战法）

核心逻辑：

1. 在 `lookback_n` 窗内，存在某日 `t_m` **满足 BBIKDJSelector**；
2. 区间 `[t_m, 当日前一日]` 收盘价波动率 ≤ `close_vol_pct`；
3. 当日相对前一日 **下跌 ≥ `price_drop_pct`**；
4. 当日 J **< `j_threshold`** 或 **≤ `j_q_threshold` 分位**；
5. **知行约束**：
   - 在 `t_m` 当日：**收盘 > 长期线** 且 **短期线 > 长期线**；
   - 在 **当日**：只需 **短期线 > 长期线**。

`selector.config.json` 预设：

```json
{
  "class": "SuperB1Selector",
  "alias": "SuperB1战法",
  "params": {
    "lookback_n": 10,
    "close_vol_pct": 0.02,
    "price_drop_pct": 0.02,
    "j_threshold": 10,
    "j_q_threshold": 0.1,
    "B1_params": {
      "j_threshold": 15,
      "bbi_min_window": 20,
      "max_window": 120,
      "price_range_pct": 1,
      "bbi_q_threshold": 0.3,
      "j_q_threshold": 0.1
    }
  }
}
```

### 3. BBIShortLongSelector（补票战法）

核心逻辑：

- **BBI 上升**（容忍回撤）；
- 最近 `m` 日内：
  - 长 RSV（`n_long`）**全 ≥ `upper_rsv_threshold`**；
  - 短 RSV（`n_short`）出现“**先 ≥ upper，再 < lower**”的序列结构；
  - 当日短 RSV **≥ upper**；

- **MACD**：`DIF > 0`；
- **知行当日约束**：**收盘 > 长期线** 且 **短期线 > 长期线**。

`selector.config.json` 预设：

```json
{
  "class": "BBIShortLongSelector",
  "alias": "补票战法",
  "params": {
    "n_short": 5,
    "n_long": 21,
    "m": 5,
    "bbi_min_window": 2,
    "max_window": 120,
    "bbi_q_threshold": 0.2,
    "upper_rsv_threshold": 75,
    "lower_rsv_threshold": 25
  }
}
```

### 4. PeakKDJSelector（填坑战法）

核心逻辑：

- 基于 `open/close` 的 `oc_max` 寻找峰值（`scipy.signal.find_peaks`）；
- 选择最新峰 `peak_t` 与其前方**有效参照峰** `peak_(t-n)`：要求 `oc_t > oc_(t-n)`，并确保区间内其它峰不“抬高门槛”；且 `oc_(t-n)` 必须 **高于区间最低收盘价 `gap_threshold`**；
- 当日收盘与 `peak_(t-n)` 的波动率 ≤ `fluc_threshold`；
- 当日 J **< `j_threshold`** 或 **≤ `j_q_threshold` 分位**；
- **知行当日约束**：**收盘 > 长期线** 且 **短期线 > 长期线**。

`selector.config.json` 预设：

```json
{
  "class": "PeakKDJSelector",
  "alias": "填坑战法",
  "params": {
    "j_threshold": 10,
    "max_window": 120,
    "fluc_threshold": 0.03,
    "j_q_threshold": 0.1,
    "gap_threshold": 0.2
  }
}
```

### 5. MA60CrossVolumeWaveSelector（上穿60放量战法）

核心逻辑：

1. 当日 J **< `j_threshold`** 或 **≤ `j_q_threshold` 分位**；
2. 最近 `lookback_n` 内存在**有效上穿 MA60**；
3. 以上穿日 `T` 到当日区间内 **High 最大日** 作为 `Tmax`，定义上涨波段 `[T, Tmax]`，其 **平均成交量 ≥ `vol_multiple` × 上穿前等长或截断窗口的平均量**；
4. `MA60` 的最近 `ma60_slope_days` 日 **回归斜率 > 0**；
5. **知行当日约束**：**收盘 > 长期线** 且 **短期线 > 长期线**。

`selector.config.json` 预设：

```json
{
  "class": "MA60CrossVolumeWaveSelector",
  "alias": "上穿60放量战法",
  "params": {
    "lookback_n": 25,
    "vol_multiple": 1.8,
    "j_threshold": 15,
    "j_q_threshold": 0.1,
    "ma60_slope_days": 5,
    "max_window": 120
  }
}
```

> **已移除**：`BreakoutVolumeKDJSelector（TePu 战法）`。

### 6. BigBullishVolumeSelector（暴力K战法）

核心逻辑：

1. **当日为长阳**：
   当日涨幅 `(close / prev_close - 1)` **大于 `up_pct_threshold`**；

2. **上影线短**：
   上影线比例
   \[
   \frac{High - \max(Open, Close)}{\max(Open, Close)}
   \]
   **小于 `upper_wick_pct_max`**，用于过滤冲高回落型假阳线；

3. **放量突破**：
   当日成交量
   \[
   Volume\_{today} \ge vol_multiple \times \text{前 } n \text{ 日均量}
   \]

4. **贴近知行短线（不过热）**：
   计算 `ZXDQ = EMA(EMA(C,10),10)`，要求
   \[
   Close < ZXDQ \times close_lt_zxdq_mult
   \]
   用于过滤已经明显脱离短线均值、过度加速的股票。

5. （可选）**收阳约束**：`close ≥ open`。

该策略意在捕捉：

> **“刚刚放量启动的强势阳线，但尚未远离短期均线、仍具延续空间的个股”。**

---

`selector.config.json` 预设：

```json
{
  "class": "BigBullishVolumeSelector",
  "alias": "暴力K战法",
  "params": {
    "up_pct_threshold": 0.06,
    "upper_wick_pct_max": 0.02,
    "require_bullish_close": true,
    "close_lt_zxdq_mult": 1.15,
    "vol_lookback_n": 20,
    "vol_multiple": 2.5
  }
}
```

---

## 项目结构

```bash
.
├── setup.py                          # 交互式配置向导（.env + GitHub Secrets）
├── check_setup.py                    # 验证环境变量 / Tushare / Lark 测试消息
├── .github/workflows/
│  ├── daily-stock-trade.yml          # 每日选股 + 风控（定时 + 手动触发）
│  └── check_setup.yml                # 配置检查（手动触发）
├── .vscode/                          # VS Code 配置
│  ├── tasks.json                     # 任务配置（快捷运行脚本）
│  ├── launch.json                    # 调试配置
│  └── settings.json                  # 编辑器设置
│
├── config/                           # 策略与风控配置（与代码分离）
│  ├── selector.config.json           # 选股策略（统一 selectors 列表）
│  ├── pool_selector.config.json      # 股池选股策略
│  └── risk.config.json               # 风险检测策略
│
├── stock_trade_z/                    # 应用代码（CLI 入口 + 内部模块）
│  ├── fetch_stocklist.py             # 获取所有股票列表
│  ├── fetch_kline.py                 # 下载历史 K 线数据（前复权）
│  ├── select_stock.py                # 批量选股主入口
│  ├── check_code.py                  # 检查单只股票是否命中战法
│  ├── update_to_goodlist.py          # 添加股票到优选列表
│  ├── sort_csv.py                    # 排序股票列表 CSV 文件
│  ├── try_play.py                    # 测试脚本
│  ├── add_xueqiu_urls.py             # 添加雪球链接
│  ├── stocklist.total.csv            # 全量股票池（5000+ 只）
│  └── lib/                           # 内部工具模块
│     ├── ts_pro_api.py               # Tushare API 封装
│     ├── selector.py                 # Z 哥战法选择器
│     ├── pipeline_selectors.py       # B1 / 砖型图（向量化 Pipeline）
│     ├── quant_selectors.py          # 主流量化因子选择器
│     ├── chart_score.py              # K 线四维度图形评分 selector
│     ├── risk_selectors.py           # 风险检测选择器
│     ├── registry.py                 # JSON 配置加载（支持 per-entry module）
│     ├── fetch_data.py               # 数据抓取工具
│     ├── load_selector.py            # 选择器加载工具
│     ├── load_stocklist.py           # 股票列表加载工具
│     ├── llm_analyze.py              # DeepSeek 复盘
│     ├── lark_report.py              # 选股报告 Markdown 拼装
│     ├── logger.py                   # 日志工具
│     ├── paths.py                    # 路径管理
│     ├── lark_doc.py                 # 飞书云文档创建与 Markdown 写入
│     ├── lark_notify.py              # 文档报告 + 机器人链接通知
│     └── ...
│
├── data/                             # K 线行情 CSV 输出目录
├── stocklist.good.csv                # 优选股票池（经过初步筛选）
├── .env.example                      # 环境变量示例（Tushare + Lark + DeepSeek + Langfuse）
├── pyproject.toml                    # 项目依赖与 CLI 入口
├── uv.lock                           # 锁定依赖版本
└── log/                              # 运行日志
```

---

## 选股机制

`stock-select` 流水线（`select_stock.py`）：

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

## Risk Selectors (风险检测)

风险检测由 **`risk.config.json`** 驱动（`load_risk_selectors`），实现位于 `lib/risk_selectors.py`：

- **ATR Volatility**：相对波动率过高
- **RSI Extremes**：超买/超卖极端
- **MA Decline**：均线空头排列且长期均线走弱
- **Volume Selloff**：放量下跌
- **Drawdown**：相对近期高点回撤过大
- **Gap Down**：跳空低开
- **MACD Bearish**：MACD 死叉或空头动能
- **Top Trap**：CCI 超买 + 顶部陷阱信号

```bash
uv run stock-detect-risk --data-dir ./data
```

输出按命中风险条数聚合排序。

---

## 常见问题

**Q0：飞书收不到消息？**

1. 运行 `uv run python check_setup.py`，确认环境变量与 Lark 测试文档通知均成功。
2. 确认应用已发布、已开通 `docx:document` / `docx:document:create` / 云文档权限相关 scope，机器人可发消息，且 `ME_UNION_ID` 为接收人 union_id（非 open_id）。
3. GitHub Actions 需在仓库 Secrets 中配置 `TUSHARE_TOKEN`、`ZHITU_TOKEN`、`DEEPSEEK_API_KEY`（若启用 LLM）、`LARK_APP_ID`、`LARK_SECRET`、`LARK_FOLDER_TOKEN`、`ME_UNION_ID`（可用 `setup.py` 一次性写入）。若启用 LLM 复盘并需要 trace，可额外配置 `LANGFUSE_PUBLIC_KEY`、`LANGFUSE_SECRET_KEY`、`LANGFUSE_BASE_URL`（见 [LLM 可观测性](#llm-可观测性langfuse)）。

**Q1：为什么抓取会“卡住很久”？**
可能命中 Tushare 频控或网络封禁。脚本检测到典型关键字（如“访问频繁/429/403”）时，会进入**长冷却（默认 600s）** 再重试。

**Q2：为什么不做增量合并？**
考虑采用增量更新会遇到前复权的问题，本版选择**每次全量覆盖写入**。

**Q3：创业板/科创板/北交所如何排除？**
运行时使用 `--exclude-boards gem star bj`，或按需选择其一/其二。

**Q4：B1 / 砖型图为什么经常 0 结果？**
条件较严，且 B1 的知行线 `zx_m4=114` 需要单股至少约 114 根 K 线；本地若只抓了较短区间会算出 NaN。CI 从 `20240101` 拉数一般足够。可与「少妇战法」等 Z 战法结果对照——后者条件略宽。
