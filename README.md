# QuantStudy 事件驅動量化回測框架

一套機構級可擴展的 Python 事件驅動回測框架，支援均值回歸、動能輪動等多策略範式，精確模擬 T+1 交易邏輯、限價單撮合、除權息價格轉換、手續費與滑點。

## 🎯 核心特性

### 1. **事件驅動架構**
- 日迴圈共 4 大步驟：賣單執行 → 買單執行 → 盤中監控 → 訊號產生
- 完全物件導向設計，支援 YAML 配置驅動
- 無需修改主程式，即可抽換策略、保險絲、資金管理模組

### 2. **精確的交易邏輯**
- **T+1 執行**：當日訊號次日開盤成交（完美模擬台灣股市）
- **限價單撮合**：支援盤中觸及、開盤跳空邏輯，精確計算成交價
- **雙價格系統**：
  - `raw_price`：實際交易成交價
  - `adjusted_price`：指標計算價（已還原除權息）
  - 自動計算 `price_ratio = raw_close / adj_close` 進行轉換
- **部分平倉**：支援減碼交易（如動能輪動的增減倉位調整）

### 3. **多維度風控**
- **盤中出場**（Intraday Exit）
  - 固定百分比停損（FixedPercentStop）
  - ATR 追蹤停損（ATRTrailingStop）
  - 支援開盤跳空、盤中觸及兩種觸發方式
- **收盤出場**（EOD Exit）
  - N 根柱線時間出場（NBarExit）
  - 技術指標出場（IndicatorExit，如 CRSI 超買）
  - 策略主動訊號出場（signal=-1）
- **優先級管理**：盤中停損 > 收盤出場，同類型內先觸發優先

### 4. **靈活的資金管理**
- **固定風險資金管理**（FixedRiskSizer）
  - 基於風險金額計算股數：`shares = (equity × risk_pct) / (entry - stop)`
  - 支援無停損 fallback 路徑：`shares = (equity × max_pos_pct) / entry`
  - 適合均值回歸策略
- **等權重資金管理**（EqualWeightSizer）
  - 每檔標的分配等額資本：`per_stock = (equity × buffer) / max_positions`
  - 適合動能輪動策略

### 5. **完整的績效分析**
- 日報表（daily_log）：資產淨值、持倉數、現金、曝險度
- 交易報表（trade_log）：進場/出場價格、獲利、原因、最高價/最低價
- 績效指標：
  - 絕對回報：總報酬率、CAGR
  - 風險調整：Sharpe、Sortino、Calmar 比率
  - 交易統計：勝率、利潤因子、最大不利幅度/最大有利幅度（MAE/MFE）
  - 大盤比較：相對收益、超額報酬

## 📁 項目結構

```
QuantStudy-backtest-framework/
│
├── core/                      # 核心引擎
│   ├── engine.py             # 事件驅動引擎 (AdvancedEventEngine)
│   ├── sizer.py              # 資金管理模組 (FixedRiskSizer, EqualWeightSizer)
│   ├── exits.py              # 出場保險絲 (FixedPercentStop, ATR, NBar, etc.)
│   └── config_loader.py      # YAML 設定加載器
│
├── strategies/                # 策略庫
│   ├── base.py               # 基類 (BaseStrategy)
│   ├── crsi_reversion.py     # CRSI 均值回歸策略
│   └── BaseRotationStrategy.py # 動能輪動基類
│
├── utils/                     # 工具模組
│   ├── zoo.py                # 技術指標庫 (CRSI, RSI, ATR 等)
│   └── performance.py        # 績效分析器 (PerformanceAnalyzer)
│
├── config.yaml               # 全局配置檔（策略、保險絲、濾網）
├── test.ipynb                # 回測執行入口
└── README.md                 # 本文件
```

## 🚀 快速開始

### 安裝依賴

```bash
pip install pandas numpy duckdb pyyaml scipy statsmodels matplotlib seaborn
```

### 基本流程（test.ipynb）

```python
from core.engine import AdvancedEventEngine
from core.sizer import FixedRiskSizer
from core.exits import NBarExit, IndicatorExit
from strategies.crsi_reversion import CRSIStrategy
from utils.performance import PerformanceAnalyzer

# 1. 配置引擎
config = {
    'initial_capital': 1_000_000,
    'max_positions': 10,
    'rank_metric': 'crsi',
    'ascending': True,
    'commission_rate': 0.001425,
    'slippage_pct': 0.002,
    'risk_pct': 0.01,
}

# 2. 初始化組件
strategy = CRSIStrategy(config)
sizer = FixedRiskSizer(risk_pct=0.01, max_pos_pct=0.10)
exits = [NBarExit(n=10), IndicatorExit(indicator='crsi', threshold=70)]

# 3. 建立引擎並運行
engine = AdvancedEventEngine(config, data_feed=df)
engine.set_components(exits=exits, sizer=sizer, risk_stop_module=None)
daily_log, trade_log, _ = engine.run(strategy_instance=strategy)

# 4. 績效分析
analyzer = PerformanceAnalyzer(daily_log, trade_log)
analyzer.calculate()
analyzer.plot_tearsheet()
```

## ⚙️ 配置文件（config.yaml）

```yaml
# 系統層級參數
system:
  initial_capital: 1000000
  risk_free_rate: 0.02
  commission_rate: 0.001425
  slippage_pct: 0.002

# 引擎層級參數
engine:
  max_positions: 10        # 最大同時持倉數（0 = 無限制）
  rank_metric: "crsi"      # 候選股票排序指標
  ascending: true          # 排序方向（true = 低值優先）

# 策略配置
strategies:
  CRSIStrategy:
    enabled: true
    crsi_entry: 10         # 進場門檻（CRSI < 10）
    crsi_exit: 70          # 出場門檻（CRSI > 70）
    limit_pct: 0.02        # 限價單折扣（2%）

# 資金管理
sizers:
  FixedRiskSizer:
    enabled: true
    risk_pct: 0.01         # 每筆交易冒險 1% 資本

# 保險絲（出場模組）
exits:
  - name: FixedPercentStop
    enabled: false
    pct: 0.05

  - name: ATRTrailingStop
    enabled: false
    multiplier: 2.5
    window: 14

  - name: NBarExit
    enabled: true
    n: 10                  # 10 根柱線後強制出場

  - name: IndicatorExit
    enabled: false
    indicator: 'crsi'
    threshold: 70
    logic: '>'
```

## 🔍 核心邏輯流程

### 日迴圈執行順序

```
Day T：
  ├─ [Step 1-A] 執行前日的賣單（T+1 成交）
  ├─ [Step 1-B] 執行前日的買單（T+1 開盤成交）
  ├─ [Step 2]   盤中監控（停損、追蹤停損）
  │              └─ 更新最高價/最低價、指標
  ├─ [Step 3-A] 處理策略主動出場訊號 (signal = -1)
  ├─ [Step 3]   產生買單訊號 (signal = 1)
  │              └─ 根據 rank_metric 排序、max_positions 截斷
  ├─ [Step 3-B] 目標權重再平衡（動能輪動專用）
  └─ [Step 4]   結算日誌、更新資產淨值
```

### 價格轉換邏輯

```python
# 從指標價（adjusted）轉換到交易價（raw）
price_ratio = raw_close / adjusted_close

# 盤中監控時，將 ATR 指標還原到交易價
atr_raw = atr_adjusted * price_ratio

# 限價單計算
limit_price_adj = adjusted_close * (1 - limit_pct)  # 計算指標價
limit_price_raw = limit_price_adj * price_ratio      # 轉換到交易價
```

### 出場優先級

```
優先級 1（最優先）：盤中即時出場
  ├─ FixedPercentStop（硬停損）
  └─ ATRTrailingStop（追蹤停損）

優先級 2：收盤出場（按定義順序）
  ├─ NBarExit（時間出場）
  ├─ IndicatorExit（技術指標出場）
  └─ Strategy Signal=-1（策略主動訊號）

執行規則：
  - 盤中若觸發停損，當日不再檢查收盤出場
  - 收盤出場中，只執行「第一個」觸發的模組
  - 各模組通過 is_intraday 屬性判斷（False = 收盤）
```

## 🐛 框架修復歷程

本框架已完成 P0-P1 階段的關鍵修復（6 大 Bug），確保回測結果準確可靠：

| 修復階段 | 修復數量 | 重點改進 |
|---------|---------|---------|
| **P0** | 3 個 | max_positions、slippage、倉位大小 |
| **P1** | 3 個 | signal=-1 出場、出場類型判斷、優先級規則 |
| **P2** | 2 個 | YAML 配置加載器、孤兒參數清理 |

詳細的修復記錄、根本原因分析、驗證方法見 [CHANGELOG.md](CHANGELOG.md)。

## 📊 績效指標解釋

| 指標 | 含義 | 公式 |
|-----|-----|------|
| CAGR | 年化複合報酬率 | (末期 / 初期) ^ (1/年數) - 1 |
| Sharpe | 風險調整後報酬（標準差） | (年化超額報酬) / (年化波動率) |
| Sortino | 風險調整後報酬（只計下檔風險） | (CAGR - 無風險率) / 下檔波動率 |
| Calmar | 回報 vs 回撤 | CAGR / abs(MDD) |
| MDD | 最大回撤 | (當前高點 - 當前值) / 當前高點 |
| 勝率 | 獲利交易占比 | 獲利筆數 / 總筆數 |
| 利潤因子 | 總獲利 / 總虧損 | 值 > 1.5 較佳 |
| MAE | 最大不利幅度（進場後最大虧損幅度） | (最低價 - 進場價) / 進場價 |
| MFE | 最大有利幅度（進場後最大獲利幅度） | (最高價 - 進場價) / 進場價 |

## 🔧 擴展指南

### 添加新策略

```python
from strategies.base import BaseStrategy

class MyStrategy(BaseStrategy):
    def generate_raw_signals(self, df):
        out = df.copy()
        out['signal'] = 0

        # 計算你的指標
        out['my_indicator'] = compute_indicator(out)

        # 產生買賣訊號
        out.loc[out['my_indicator'] < threshold, 'signal'] = 1   # 買
        out.loc[out['my_indicator'] > threshold, 'signal'] = -1  # 賣

        return out
```

在 config.yaml 中啟用：
```yaml
strategies:
  MyStrategy:
    enabled: true
    threshold: 50
```

### 添加新出場模組

```python
from core.exits import ExitBase

class MyExit(ExitBase):
    is_intraday = False  # 設定是否盤中即時或收盤

    def __init__(self, param=value):
        self.param = param

    def check(self, bar, position):
        # bar: {'open', 'high', 'low', 'close', 'date', ...indicators}
        # position: {'entry_price', 'entry_date', 'shares', ...}

        if some_condition:
            return True, exit_price, "MyExit_Reason"
        return False, None, None
```

在 config.yaml 中啟用：
```yaml
exits:
  - name: MyExit
    enabled: true
    param: value
```

### 自定義資金管理

```python
class MySizer:
    def __init__(self, param=value):
        self.param = param

    def calculate_shares(self, equity, entry_price, stop_price):
        # 傳入：帳戶淨值、進場價、停損價
        # 返回：應買股數（整數）
        shares = int((equity * allocation) / entry_price)
        return shares
```

## ⚠️ 常見陷阱

### 1. 價格系統混淆
- ❌ **錯誤**：用 adjusted_price 進行實際交易計算
- ✅ **正確**：交易時用 raw_price，指標計算用 adjusted_price

### 2. T+1 邏輯
- ❌ **錯誤**：當日訊號當日成交
- ✅ **正確**：當日訊號次日開盤成交（engine 自動處理）

### 3. 持倉上限
```python
# 配置中要同時設定：
engine:
  max_positions: 10

# 引擎會在 Step 1-B 檢查，不會執行超量進場
```

### 4. 部分平倉
- 減碼交易時，舊部位會保留，新部位建立新紀錄
- 績效報表會分別計算（每筆單獨日誌）

### 5. 限價單
- 若限價單未成交，自動於次日繼續保留
- 跳空（開盤直接跳過限價）時，改用開盤價成交

## 📚 技術指標參考

### CRSI（Connors RSI）
三個 RSI 的加權組合，用於均值回歸：
```python
CRSI = (RSI_3day + RSI_StRSI + RSI_%Rank) / 3
```
- **RSI_3day**：3 日相對強度指數（敏感、快速反應）
- **RSI_StRSI**：連勝/連敗的 RSI（趨勢強度）
- **RSI_%Rank**：百分比排名的 RSI（相對強弱）

CRSI < 10 → 超賣（買入訊號）
CRSI > 70 → 賣出訊號

### ATR（Average True Range）
衡量波動率，用於動態停損：
```python
ATR = 14 期平均真實振幅
Stop_Price = Entry_Price - (ATR × Multiplier)
```

## 🔒 品質保證

框架已通過全面邏輯審查，確保：
- ✅ **日迴圈執行順序** 正確無誤（6 大步驟）
- ✅ **出場優先級** 清晰明確（盤中 > EOD，防重複）
- ✅ **價格系統** 一致（raw/adjusted 自動轉換）
- ✅ **資金管理** 完整（風險基礎 + fallback）
- ✅ **邊界情況** 妥善處理（跳空、無資料、部分平倉）

詳細的開發日誌和檢查清單見 [CHANGELOG.md](CHANGELOG.md)。

## 🤝 貢獻與反饋

有想法或發現問題？我們歡迎你的參與：

- **報告 Bug**：提交 [Issue](https://github.com/zhanyi789/QuantStudy-backtest-framework/issues) 並附上重現步驟
- **功能建議**：詳細說明使用場景和預期解決方案
- **提交貢獻**：遵循 [CONTRIBUTING.md](CONTRIBUTING.md) 指南提交 Pull Request
- **文檔改進**：英文文檔、API 參考待補充

詳見 [CONTRIBUTING.md](CONTRIBUTING.md) 了解開發流程、測試規範、代碼風格。

---

## 🚨 已知限制與未來改進

### 目前不支援
- [ ] 盤中委託單（市價單立即成交，未支援掛單等待）
- [ ] 複雜衍生品交易（期貨、選擇權）
- [ ] 融資融券
- [ ] 融券回補時的成本計算

### 計畫中的功能
- [ ] 多幣種支援（目前單幣）
- [ ] 即時數據饋送（目前僅支援歷史回測）
- [ ] 分散式並行計算（多策略並行回測）
- [ ] 敏感性分析自動化工具
- [ ] Web UI 儀表板

---

## 📖 文檔導航

| 文檔 | 用途 |
|------|------|
| [README.md](README.md) | 項目概述、快速開始、API 使用 |
| [CHANGELOG.md](CHANGELOG.md) | 版本歷史、修復日誌、技術細節 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 開發指南、測試規範、貢獻流程 |

---

**最後更新**：2026-03-13
**框架版本**：2.0（P0-P1 完全修復，P2 配置加載器已實裝）
**主要貢獻**：Ian Chang（量化策略開發）、Claude Code（架構審查與修復）
