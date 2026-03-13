# 完整使用說明書

本指南涵蓋 QuantStudy 事件驅動回測框架的所有實操步驟，從安裝、配置、策略開發到績效分析。

---

## 目錄

1. [快速開始](#快速開始)
2. [配置參數詳解](#配置參數詳解)
3. [策略開發教程](#策略開發教程)
4. [出場模組組合](#出場模組組合)
5. [績效分析與診斷](#績效分析與診斷)
6. [常見問題排查](#常見問題排查)

---

## 快速開始

### 安裝與環境設置

#### 1. 克隆專案

```bash
git clone https://github.com/zhanyi789/QuantStudy-backtest-framework.git
cd QuantStudy-backtest-framework
```

#### 2. 建立虛擬環境

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python -m venv venv
source venv/bin/activate
```

#### 3. 安裝依賴

```bash
pip install -r requirements.txt
```

依賴清單：
- `pandas` ≥ 2.0：數據處理
- `numpy` ≥ 1.20：數值計算
- `pyyaml` ≥ 6.0：設定檔讀取
- `matplotlib` ≥ 3.5：繪圖（績效分析）
- `jupyter` ≥ 1.0：互動式開發環境

#### 4. 驗證安裝

```bash
python -c "from core.engine import AdvancedEventEngine; print('✅ Setup OK')"
```

若無錯誤，環境準備完成。

---

### 執行第一個回測

#### 步驟 1：準備數據

需要一份 CSV 或 DataFrame，包含以下欄位：

```python
import pandas as pd

# 示範數據結構
data = pd.DataFrame({
    'date': ['2024-01-02', '2024-01-03', ...],
    'ticker': ['STOCK_A', 'STOCK_A', ...],

    # 原始價格（交易用）
    'open': [100.0, 101.0, ...],
    'high': [102.0, 103.0, ...],
    'low': [99.0, 100.0, ...],
    'close': [101.0, 102.0, ...],  # 必須有 'close'
    'volume': [1000000, 1100000, ...],

    # 調整價格（指標計算用）
    'adj_close': [101.0, 102.0, ...],  # 若無除權，與 close 相同

    # 指標（由策略計算）
    'crsi': [35.0, 28.0, ...],  # CRSI 值（用於均值回歸）
})

# 設為索引，便於查詢
data = data.set_index(['date', 'ticker']).sort_index()
```

#### 步驟 2：配置設定檔

編輯 `config.yaml`：

```yaml
# config.yaml

system:
  initial_capital: 1000000      # 初始資本 100 萬
  risk_free_rate: 0.02          # 無風險利率 2%
  commission_rate: 0.001425     # 手續費 0.1425%
  slippage_pct: 0.002           # 滑點 0.2%

engine:
  max_positions: 10             # 最多同時持倉 10 檔
  rank_metric: "crsi"           # 排序指標為 CRSI
  ascending: true               # CRSI 低值優先

strategies:
  CRSIStrategy:
    enabled: true
    crsi_entry: 10              # 買進訊號：CRSI < 10
    crsi_exit: 70               # 賣出訊號：CRSI > 70

sizers:
  FixedRiskSizer:
    enabled: true
    risk_pct: 0.01              # 單筆風險 1%
    max_pos_pct: 0.10           # 單筆最大投入 10%

exits:
  - name: "FixedPercentStop"
    enabled: true
    stop_pct: 0.02              # 2% 止損

  - name: "NBarExit"
    enabled: true
    max_bars: 10                # 最多持倉 10 個交易日
```

#### 步驟 3：運行回測

在 Jupyter Notebook 中執行：

```python
from core.engine import AdvancedEventEngine
from strategies.crsi_strategy import CRSIStrategy
from core.config_loader import load_config
import pandas as pd

# 1. 載入配置
config = load_config('config.yaml')

# 2. 計算策略指標
strategy = CRSIStrategy(crsi_entry=config['crsi_entry'], crsi_exit=config['crsi_exit'])
data = strategy.add_indicators(data)

# 3. 執行回測
engine = AdvancedEventEngine(config=config, data_feed=data)
daily_log, trade_log, metrics = engine.run(strategy_instance=strategy)

# 4. 查看結果
print(f"累計報酬: {metrics['total_return']:.2%}")
print(f"Sharpe 比率: {metrics['sharpe']:.2f}")
print(f"最大回撤: {metrics['max_dd']:.2%}")
print(f"總交易數: {len(trade_log)}")
```

#### 步驟 4：分析績效

```python
from core.analyzer import PerformanceAnalyzer

analyzer = PerformanceAnalyzer(daily_log=daily_log, trade_log=trade_log)
analyzer.calculate()
analyzer.plot()  # 繪製績效圖表
```

---

## 配置參數詳解

### 系統參數（system:）

| 參數 | 類型 | 範例 | 說明 |
|------|------|------|------|
| `initial_capital` | int | 1000000 | 初始資本（元） |
| `risk_free_rate` | float | 0.02 | 年化無風險利率（用於 Sharpe 計算） |
| `commission_rate` | float | 0.001425 | 單向手續費（台股默認 0.1425%） |
| `slippage_pct` | float | 0.002 | 滑點成本（假設每筆交易） |

**調整建議：**
- 手續費：台股 0.1425%，美股 0.01%，期貨視經紀商
- 滑點：流動性好的標的 0.1%，小盤股 0.5%
- 無風險率：跟隨央行升息決策

### 引擎參數（engine:）

| 參數 | 類型 | 範例 | 說明 |
|------|------|------|------|
| `max_positions` | int | 10 | 最多同時持倉檔數（0=無限制） |
| `rank_metric` | str | "crsi" | 每日候選篩選的排序指標欄位名 |
| `ascending` | bool | true | 排序方向（true=升序，false=降序） |

**常見組合：**

| 策略類型 | rank_metric | ascending | 說明 |
|---------|------------|-----------|------|
| 均值回歸 | crsi / rsi | true | 低值優先進場 |
| 動能追蹤 | momentum | false | 高值優先進場 |
| 多因子 | score | false | 綜合評分高優先 |

**max_positions 影響：**

```python
# max_positions = 10 時
daily_signal_cnt = 15  # 今天有 15 個訊號
actually_enter = min(daily_signal_cnt, 10)  # 只進 10 檔

# max_positions = 0 時
actually_enter = daily_signal_cnt  # 全部進（無限制）
```

### 策略參數（strategies:）

#### CRSIStrategy 參數

```yaml
strategies:
  CRSIStrategy:
    enabled: true
    crsi_entry: 10        # 買進訊號閾值
    crsi_exit: 70         # 賣出訊號閾值
```

**調整指南：**

| 參數 | 保守 | 標準 | 激進 |
|------|------|------|------|
| `crsi_entry` | 5 | 10 | 20 |
| `crsi_exit` | 80 | 70 | 60 |

- **保守**：等待極端超賣才進場，中線持倉
- **標準**：平衡進場頻率與獲利幅度（推薦新手）
- **激進**：頻繁進出，追求高換手率

**理論基礎：**
- CRSI < 10：股價深度超賣，平均回歸概率高
- CRSI > 70：股價高度超買，反彈概率高

### 資金管理參數（sizers:）

#### FixedRiskSizer

```yaml
sizers:
  FixedRiskSizer:
    enabled: true
    risk_pct: 0.01        # 單筆風險佔資本百分比
    max_pos_pct: 0.10     # 單筆最大投入資本百分比
```

**計算邏輯：**

```python
# 假設 equity=100 萬, entry_price=100, stop_price=90

# 風險基礎倉位
risk_per_share = 100 - 90 = 10 元
allowed_risk = 100 萬 × 0.01 = 1 萬
shares_by_risk = 1 萬 / 10 = 1,000 股

# 資本上限倉位
max_capital = 100 萬 × 0.10 = 10 萬
shares_by_capital = 10 萬 / 100 = 1,000 股

# 取小值
actual_shares = min(1000, 1000) = 1,000 股
```

**調整建議：**

| 風險偏好 | risk_pct | max_pos_pct | 平均每筆 |
|---------|---------|-------------|---------|
| 極保守 | 0.005 | 0.05 | ~3-5% 資本 |
| 保守 | 0.01 | 0.10 | ~5-10% 資本 |
| 標準 | 0.02 | 0.15 | ~10-15% 資本 |
| 激進 | 0.03 | 0.20 | ~15-20% 資本 |

#### EqualWeightSizer

```yaml
sizers:
  EqualWeightSizer:
    enabled: true
    max_positions: 10    # 預期最大持倉數
    buffer: 0.95         # 預留現金比例
```

**計算邏輯：**

```python
# 每檔投入金額 = (資本 × buffer) / max_positions
# = (100 萬 × 0.95) / 10 = 9.5 萬

# 不考慮停損，固定金額制
shares = 9.5 萬 / 100 = 950 股
```

**適用場景：**
- 多因子組合（每個因子等權重）
- 無明確停損點的策略
- 輪動策略（定期調整）

### 出場模組參數（exits:）

#### FixedPercentStop（固定百分比停損）

```yaml
exits:
  - name: "FixedPercentStop"
    enabled: true
    stop_pct: 0.02       # 2% 止損
```

**計算：**
```python
stop_price = entry_price × (1 - stop_pct)
# entry_price=100, stop_pct=0.02 → stop_price=98
```

#### ATRTrailingStop（ATR 追蹤停損）

```yaml
exits:
  - name: "ATRTrailingStop"
    enabled: true
    atr_multiplier: 2.0  # 停損線 = 進場價 - (ATR × 倍數)
    atr_period: 14       # ATR 計算周期
```

#### NBarExit（N 日持倉期限）

```yaml
exits:
  - name: "NBarExit"
    enabled: true
    max_bars: 10         # 最多持倉 10 個交易日
```

#### IndicatorExit（指標收盤出場）

```yaml
exits:
  - name: "IndicatorExit"
    enabled: true
    # 配合策略的 signal=-1 使用
```

---

## 策略開發教程

### 策略架構

所有策略繼承 `BaseStrategy` 基類：

```python
from strategies.base import BaseStrategy
import pandas as pd
import numpy as np

class MyStrategy(BaseStrategy):
    """自訂策略模板"""

    def __init__(self, param1=10, param2=20):
        """
        初始化策略參數

        參數：
            param1, param2：可由 config.yaml 傳入
        """
        self.param1 = param1
        self.param2 = param2

    def add_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        計算指標

        輸入：data (DataFrame)
            columns: ['open', 'high', 'low', 'close', 'adj_close', 'volume', ...]
            index: [date, ticker]

        輸出：data 加入指標欄位
            'indicator1', 'indicator2', ...
        """
        # 分組計算：每個 ticker 單獨計算
        data = data.groupby(level='ticker').apply(self._compute_indicators)
        return data

    def _compute_indicators(self, ticker_data):
        """單個標的的指標計算"""
        # 示範：簡單移動平均
        ticker_data['sma_short'] = ticker_data['adj_close'].rolling(10).mean()
        ticker_data['sma_long'] = ticker_data['adj_close'].rolling(20).mean()
        return ticker_data

    def generate_signals(self, today_data: pd.DataFrame) -> pd.Series:
        """
        產生交易訊號

        輸入：today_data (DataFrame)
            當日所有標的的指標數據
            columns: ['open', 'close', 'sma_short', 'sma_long', ...]
            index: [ticker]

        輸出：signal (Series)
            index: [ticker]
            value: 1 (買進), -1 (賣出), 0 (無動作)
        """
        signal = pd.Series(index=today_data.index, dtype=int)
        signal[:] = 0  # 默認無訊號

        # 買進條件：短期 MA > 長期 MA
        buy_mask = (today_data['sma_short'] > today_data['sma_long'])
        signal[buy_mask] = 1

        # 賣出條件：短期 MA < 長期 MA
        sell_mask = (today_data['sma_short'] < today_data['sma_long'])
        signal[sell_mask] = -1

        return signal
```

### 常見指標實現

#### CRSI（Connors RSI）

```python
def compute_crsi(data, rsi_period=3, atr_period=20):
    """
    CRSI = (RSI + RSI_of_ROC + Percentile_Rank) / 3
    用於極端超賣超買判斷
    """
    # 1. 計算 RSI
    delta = data['adj_close'].diff()
    gain = delta.clip(lower=0).rolling(rsi_period).mean()
    loss = -delta.clip(upper=0).rolling(rsi_period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    # 2. 計算 ROC（Price Change Rate）
    roc = (data['adj_close'] - data['adj_close'].shift(rsi_period)) / data['adj_close'].shift(rsi_period)
    roc_rsi = rsi.copy()
    # (同樣計算 RSI，但基於 ROC)

    # 3. 計算百分位排名（簡化版）
    percentile = rsi.rolling(atr_period).apply(
        lambda x: (x[-1] > x[:-1]).sum() / len(x[:-1]) * 100
    )

    # 3. 合成 CRSI（平均）
    crsi = (rsi + percentile) / 2  # 簡化版本
    return crsi
```

#### RSI（相對強度指數）

```python
def compute_rsi(close, period=14):
    """相對強度指數：衡量超買超賣"""
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi
```

#### ATR（平均真實波動幅度）

```python
def compute_atr(high, low, close, period=14):
    """用於動態停損"""
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    return atr
```

#### Momentum（動量指標）

```python
def compute_momentum(close, period=10):
    """價格變化率，用於動能策略"""
    momentum = (close - close.shift(period)) / close.shift(period)
    return momentum
```

### 完整策略示例：動能追蹤

```python
class MomentumStrategy(BaseStrategy):
    """動能追蹤策略：買進上漲標的，賣出下跌標的"""

    def __init__(self, lookback=10):
        self.lookback = lookback  # 計算動量的回望期間

    def add_indicators(self, data):
        data = data.groupby(level='ticker').apply(self._add_indicators)
        return data

    def _add_indicators(self, ticker_data):
        # 計算日報酬率
        ticker_data['daily_return'] = ticker_data['adj_close'].pct_change()

        # 計算累積動量（過去 lookback 天的累積報酬）
        ticker_data['momentum'] = (
            (1 + ticker_data['daily_return']).rolling(self.lookback).prod() - 1
        )

        return ticker_data

    def generate_signals(self, today_data):
        signal = pd.Series(index=today_data.index, dtype=int)
        signal[:] = 0

        # 買進：過去 10 天累積報酬 > 0（上漲）
        buy_mask = today_data['momentum'] > 0
        signal[buy_mask] = 1

        # 賣出：過去 10 天累積報酬 < 0（下跌）
        sell_mask = today_data['momentum'] < 0
        signal[sell_mask] = -1

        return signal
```

### 如何整合自訂策略

#### 1. 新增策略文件

```bash
strategies/
├── base.py              # 基類
├── crsi_strategy.py     # 已有
└── my_strategy.py       # 新策略
```

#### 2. 編寫策略類

見上述示例

#### 3. 在 config.yaml 中啟用

```yaml
strategies:
  MyStrategy:
    enabled: true
    lookback: 10

  CRSIStrategy:
    enabled: false       # 停用舊策略
```

#### 4. 在回測腳本中導入

```python
from strategies.my_strategy import MyStrategy

strategy = MyStrategy(lookback=config.get('lookback', 10))
data = strategy.add_indicators(data)
engine.run(strategy_instance=strategy)
```

---

## 出場模組組合

### 典型組合方案

#### 方案 1：保守風控（推薦新手）

```yaml
exits:
  - name: "FixedPercentStop"
    enabled: true
    stop_pct: 0.02       # 2% 立即止損（盤中）

  - name: "NBarExit"
    enabled: true
    max_bars: 5          # 5 日後強制出場（收盤）
```

**特點：**
- 優先級：2% 止損 > 5 日期限
- 若触發止損立即出場，否則 5 日後全部出場
- 最大虧損可控，持倉時間短

#### 方案 2：策略驅動出場

```yaml
exits:
  - name: "FixedPercentStop"
    enabled: true
    stop_pct: 0.03       # 3% 止損

  - name: "IndicatorExit"
    enabled: true        # 由策略訊號驅動
```

**特點：**
- 優先級：3% 止損 > 策略訊號出場
- 策略自己決定何時賣出（如 CRSI > 70）
- 靈活性高，適合均值回歸策略

#### 方案 3：ATR 動態停損

```yaml
exits:
  - name: "ATRTrailingStop"
    enabled: true
    atr_multiplier: 2.0
    atr_period: 14       # 14 期 ATR

  - name: "NBarExit"
    enabled: true
    max_bars: 20         # 備選：20 日強制出場
```

**特點：**
- 利用波動率自動調整停損線
- 波動大時停損線寬鬆，波動小時停損線嚴格
- 適合動能策略

#### 方案 4：多層防線

```yaml
exits:
  - name: "FixedPercentStop"
    enabled: true
    stop_pct: 0.05       # 5% 損切

  - name: "ATRTrailingStop"
    enabled: true
    atr_multiplier: 1.5
    atr_period: 14       # 追蹤獲利

  - name: "NBarExit"
    enabled: true
    max_bars: 10         # 持倉期限

  - name: "IndicatorExit"
    enabled: true        # 策略訊號
```

**執行優先級：**
1. 若 5% 止損觸發 → 當日標記，次日開盤出場
2. 若未觸發 5%，檢查 ATR 追蹤 → 同上
3. 若未觸發 ATR，檢查策略訊號 → 同上
4. 若未觸發策略訊號，檢查 10 日期限 → 同上

---

## 績效分析與診斷

### 讀懂 daily_log

```python
daily_log = [
    {
        'date': '2024-01-02',
        'equity': 1010000,           # 帳戶淨值（現金 + 持倉市值）
        'positions': 2,              # 當前持倉檔數
        'cash': 890000,              # 現金
        'exposure': 0.12,            # 全部持倉市值占淨值比例
    },
    {
        'date': '2024-01-03',
        'equity': 1015000,
        'positions': 3,
        'cash': 850000,
        'exposure': 0.16,
    },
    # ...
]

# 轉為 DataFrame
daily_df = pd.DataFrame(daily_log)

# 常見查詢
daily_df['daily_return'] = daily_df['equity'].pct_change()
daily_df['equity_high'] = daily_df['equity'].expanding().max()
daily_df['drawdown'] = daily_df['equity'] / daily_df['equity_high'] - 1

# 視覺化
import matplotlib.pyplot as plt
plt.figure(figsize=(12, 6))
plt.plot(daily_df['date'], daily_df['equity'], label='Equity')
plt.axhline(y=1000000, color='r', linestyle='--', label='Initial Capital')
plt.legend()
plt.show()
```

### 讀懂 trade_log

```python
trade_log = [
    {
        'ticker': 'STOCK_A',
        'entry_date': '2024-01-05',
        'entry_price': 100.0,
        'entry_value': 100000,      # entry_price × shares

        'exit_date': '2024-01-10',
        'exit_price': 105.0,
        'exit_value': 105000,       # exit_price × shares

        'pnl': 5000,                # 未含手續費淨利潤
        'pnl_pct': 0.05,            # 報酬率 5%
        'days_held': 5,             # 持倉天數
        'reason': 'NBarExit',        # 出場原因

        'max_price': 108.0,         # 持倉期間最高價（MFE 計算）
        'min_price': 98.0,          # 持倉期間最低價（MAE 計算）
    },
    # ...
]

# 轉為 DataFrame
trade_df = pd.DataFrame(trade_log)

# 績效統計
win_rate = (trade_df['pnl'] > 0).sum() / len(trade_df)  # 勝率
avg_win = trade_df[trade_df['pnl'] > 0]['pnl'].mean()   # 平均獲利
avg_loss = trade_df[trade_df['pnl'] < 0]['pnl'].mean()  # 平均虧損
profit_factor = abs(avg_win * (trade_df['pnl'] > 0).sum()) / abs(avg_loss * (trade_df['pnl'] < 0).sum())

print(f"勝率: {win_rate:.1%}")
print(f"平均獲利: {avg_win:,.0f}")
print(f"平均虧損: {avg_loss:,.0f}")
print(f"利潤因子: {profit_factor:.2f}")
```

### 關鍵績效指標解釋

#### 絕對回報類

| 指標 | 公式 | 解釋 | 目標 |
|------|------|------|------|
| **Total Return** | (末期 - 初期) / 初期 | 總報酬率 | > 0% |
| **CAGR** | (末期 / 初期) ^ (1/年數) - 1 | 年化複合報酬率 | 越高越好 |
| **Max Drawdown (MDD)** | (高點 - 低點) / 高點 | 最大虧損幅度 | 越小越好 |

**計算範例：**
```python
# 初期 100 萬，末期 150 萬，歷時 2 年
total_return = (150 - 100) / 100 = 50%
cagr = (150 / 100) ^ (1/2) - 1 = 22.5%

# MDD 計算
equity_series = daily_df['equity']
running_max = equity_series.expanding().max()
drawdown = (equity_series - running_max) / running_max
mdd = drawdown.min()  # 最小值（最大虧損）
```

#### 風險調整類

| 指標 | 公式 | 解釋 | 目標 |
|------|------|------|------|
| **Sharpe Ratio** | (年化超額報酬) / (年化波動率) | 風險調整後單位風險報酬 | > 1.0 |
| **Sortino Ratio** | (CAGR - Rf) / 下檔波動率 | 只計下檔風險的 Sharpe | > 1.0 |
| **Calmar Ratio** | CAGR / MDD | 報酬 vs 回撤 | > 0.5 |

**計算範例：**
```python
# Sharpe 計算
daily_returns = daily_df['daily_return']
annual_return = daily_returns.mean() * 252
annual_vol = daily_returns.std() * np.sqrt(252)
risk_free_rate = 0.02

sharpe = (annual_return - risk_free_rate) / annual_vol
# 若 annual_return=0.20, annual_vol=0.15, rf=0.02
# sharpe = (0.20 - 0.02) / 0.15 = 1.20

# Sortino 計算：只計算負報酬的波動
negative_returns = daily_returns[daily_returns < 0]
downside_vol = negative_returns.std() * np.sqrt(252)
sortino = (annual_return - risk_free_rate) / downside_vol
```

#### 交易統計類

| 指標 | 公式 | 解釋 | 目標 |
|------|------|------|------|
| **Win Rate** | 獲利筆數 / 總筆數 | 勝率 | > 40% |
| **Profit Factor** | 總獲利 / 總虧損 | 利潤倍數 | > 1.5 |
| **Avg Trade** | 平均獲利額 | 每筆交易平均 | > 0 |
| **MAE** | (最低價 - 進場價) / 進場價 | 持倉期間最大虧損幅度 | 診斷用 |
| **MFE** | (最高價 - 進場價) / 進場價 | 持倉期間最大獲利幅度 | 診斷用 |

**計算範例：**
```python
# Win Rate
trades_df = pd.DataFrame(trade_log)
win_rate = (trades_df['pnl'] > 0).sum() / len(trades_df)
# 若 100 筆交易中 58 筆獲利 → 58% 勝率

# Profit Factor
total_profit = trades_df[trades_df['pnl'] > 0]['pnl'].sum()
total_loss = trades_df[trades_df['pnl'] < 0]['pnl'].sum()
profit_factor = total_profit / abs(total_loss)
# 若 總獲利 60 萬，總虧損 40 萬 → 1.5

# MAE / MFE 診斷
trades_df['mae'] = (trades_df['min_price'] - trades_df['entry_price']) / trades_df['entry_price']
trades_df['mfe'] = (trades_df['max_price'] - trades_df['entry_price']) / trades_df['entry_price']

# 若 MAE 平均 -2%，MFE 平均 +5%
# 說明：策略能把握 5% 獲利空間，但止損設定較寬鬆
```

### 常見績效分析場景

#### 場景 1：Sharpe 比率很低（< 0.5）

**症狀：**
```
年化報酬: 15%
年化波動率: 30%
Sharpe = (0.15 - 0.02) / 0.30 = 0.43
```

**原因診斷：**
1. 波動率太高：檢查策略是否過於激進
2. 報酬太低：檢查是否策略有效性下降
3. 極端波動：檢查是否有黑天鵝事件

**改善方案：**
```yaml
# 降低風險參數
sizers:
  FixedRiskSizer:
    risk_pct: 0.01        # 從 0.02 改為 0.01
    max_pos_pct: 0.05     # 從 0.10 改為 0.05

# 加強風控
exits:
  - name: "FixedPercentStop"
    stop_pct: 0.01        # 從 0.02 改為 0.01（更嚴格）
```

#### 場景 2：最大回撤太深（> 30%）

**症狀：**
```
初期: 100 萬
低點: 70 萬
MDD = (70 - 100) / 100 = -30%
```

**原因診斷：**
1. 連續虧損：檢查是否策略參數不適應市場
2. 單筆損失過大：檢查止損設定
3. 持倉過多：檢查 max_positions 是否太大

**改善方案：**
```yaml
# 增強單筆風控
exits:
  - name: "FixedPercentStop"
    enabled: true
    stop_pct: 0.015       # 更嚴格的止損

# 減少同時持倉
engine:
  max_positions: 5        # 從 10 改為 5

# 調整進場閾值
strategies:
  CRSIStrategy:
    crsi_entry: 5         # 從 10 改為 5（更極端才進場）
```

#### 場景 3：勝率很高但利潤因子低（< 1.0）

**症狀：**
```
勝率: 70%
平均獲利: 500 元
平均虧損: 3000 元
利潤因子 = (500 × 0.7 × 100) / (3000 × 0.3 × 100) = 0.39
```

**問題：**
- 雖然獲利次數多，但大虧損抵消利潤
- 典型的「小贏大虧」

**改善方案：**
```yaml
# 提升止損位置（防大虧損）
exits:
  - name: "FixedPercentStop"
    stop_pct: 0.01        # 更快止損

# 或降低進場頻率（提升質量）
strategies:
  CRSIStrategy:
    crsi_entry: 5         # 只在極端超賣時進場
```

### 生成績效報告

```python
from core.analyzer import PerformanceAnalyzer

analyzer = PerformanceAnalyzer(daily_log, trade_log)
metrics = analyzer.calculate()

# 印出所有指標
print(f"""
=== 績效總結 ===
總報酬: {metrics['total_return']:.2%}
CAGR: {metrics['cagr']:.2%}
最大回撤: {metrics['max_dd']:.2%}

=== 風險調整 ===
Sharpe: {metrics['sharpe']:.2f}
Sortino: {metrics['sortino']:.2f}
Calmar: {metrics['calmar']:.2f}

=== 交易統計 ===
總交易: {metrics['total_trades']}
勝率: {metrics['win_rate']:.1%}
平均獲利: {metrics['avg_win']:,.0f}
平均虧損: {metrics['avg_loss']:,.0f}
利潤因子: {metrics['profit_factor']:.2f}
""")

# 繪製圖表
analyzer.plot()  # 淨值曲線、回撤曲線、月度收益等
```

---

## 常見問題排查

### Q1：執行回測時出現 `KeyError: 'signal'`

**原因：** 策略未產生 `signal` 欄位

**解決：**
```python
# 檢查 strategy.add_indicators() 是否被正確執行
data = strategy.add_indicators(data)

# 驗證 signal 欄位存在
assert 'signal' in data.columns, "Missing 'signal' column"

# 若仍無，檢查 generate_signals() 返回值
signals = strategy.generate_signals(today_data)
assert len(signals) > 0, "Signal generation failed"
```

### Q2：交易數為 0（沒有進場）

**原因分析：**
```
1. 買訊號從未產生 → 檢查進場條件
2. 買訊號產生但被 max_positions 截斷 → 檢查候選池大小
3. 進場但未成交 → 檢查價格邏輯
```

**診斷腳本：**
```python
# 檢查 signal=-1 的生成
signal_dist = data['signal'].value_counts()
print(f"signal=1 筆數: {signal_dist.get(1, 0)}")
print(f"signal=-1 筆數: {signal_dist.get(-1, 0)}")
print(f"signal=0 筆數: {signal_dist.get(0, 0)}")

# 若 signal=1 為 0，策略有問題
# 若 signal=1 > 0 但成交為 0，檢查引擎邏輯

# 檢查排序邏輯
today = data.xs('2024-01-05')  # 特定日期的數據
candidates = today[today['signal'] == 1]
print(f"候選數: {len(candidates)}")
print(f"max_positions: {config['max_positions']}")
print(f"實際進場數: {min(len(candidates), config['max_positions'])}")
```

### Q3：成本（手續費、滑點）計算異常

**檢查邏輯：**
```python
# 印出引擎初始化的成本參數
print(f"Commission: {engine.commission}")
print(f"Impact Cost (Slippage): {engine.impact_cost}")

# 驗證單筆成交的成本
trade = trade_log[0]
expected_cost = trade['entry_value'] * (engine.commission + engine.impact_cost)
print(f"預期成本: {expected_cost:,.0f}")

# 檢查日誌是否記錄成本
if 'cost' in trade:
    print(f"實際成本: {trade['cost']:,.0f}")
```

### Q4：績效指標異常（如 Sharpe 極高）

**檢查數據質量：**
```python
# 1. 檢查是否有異常波動
daily_returns = daily_df['daily_return']
outliers = daily_returns[abs(daily_returns) > 0.2]
print(f"異常報酬日期: {outliers.index.tolist()}")

# 2. 檢查是否有跳空
daily_df['gap'] = daily_df['equity'].diff()
big_gaps = daily_df[abs(daily_df['gap']) > daily_df['equity'] * 0.1]
print(f"大幅跳動: {big_gaps}")

# 3. 檢查數據缺失
missing_dates = pd.date_range(daily_df['date'].min(), daily_df['date'].max()).difference(daily_df['date'])
if len(missing_dates) > 0:
    print(f"缺失交易日: {missing_dates.tolist()}")
```

### Q5：出場邏輯失效（預期出場未出現）

**診斷步驟：**
```python
# 1. 檢查出場模組是否啟用
print(f"出場模組: {config['exits']}")

# 2. 檢查持倉記錄
holdings_on_date = [t for t in trade_log if t['exit_date'] is None]
print(f"截至最後一日的持倉: {len(holdings_on_date)}")

# 3. 檢查特定標的的出場原因分佈
exit_reasons = trade_df['reason'].value_counts()
print(exit_reasons)

# 若 'NBarExit' 筆數為 0 但 max_bars 設定有效，檢查日期計算邏輯
```

### Q6：回測結果無法複現（每次運行結果不同）

**常見原因：**
1. 數據排序不一致
2. 隨機參數（如採樣）
3. 浮點運算精度

**解決方案：**
```python
# 1. 設定固定 seed
import numpy as np
import random
np.random.seed(42)
random.seed(42)

# 2. 確保數據排序一致
data = data.sort_index()

# 3. 檢查是否有日期去重
assert not data.index.duplicated().any(), "Duplicate dates found"

# 4. 確認引擎參數固定
print(config)  # 確認配置未改變
```

---

## 附錄：完整回測流程檢查清單

```python
# ✅ 數據準備
assert 'close' in data.columns, "Missing 'close' column"
assert 'open' in data.columns, "Missing 'open' column"
assert data.index.name in [('date', 'ticker'), None], "Wrong index structure"

# ✅ 策略初始化
strategy = CRSIStrategy(crsi_entry=10, crsi_exit=70)
assert hasattr(strategy, 'add_indicators'), "Missing add_indicators method"
assert hasattr(strategy, 'generate_signals'), "Missing generate_signals method"

# ✅ 指標計算
data = strategy.add_indicators(data)
assert 'signal' in data.columns, "Signal not added"

# ✅ 配置驗證
config = load_config('config.yaml')
assert 'initial_capital' in config, "Missing initial_capital"
assert 'max_positions' in config, "Missing max_positions"

# ✅ 引擎執行
engine = AdvancedEventEngine(config=config, data_feed=data)
daily_log, trade_log, metrics = engine.run(strategy_instance=strategy)

# ✅ 結果驗證
assert len(daily_log) > 0, "No daily log generated"
assert metrics['total_return'] is not None, "Metrics calculation failed"

print("✅ 回測完成，所有驗證通過")
```

---

**本指南涵蓋了框架的所有實操應用。如有問題，請參考 [CONTRIBUTING.md](CONTRIBUTING.md) 中的常見問題解答。**
