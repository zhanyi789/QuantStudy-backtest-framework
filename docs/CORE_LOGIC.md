# 核心邏輯說明書

本文件深入解釋 QuantStudy 事件驅動回測框架的內部運作原理，幫助開發者理解系統的設計決策和執行流程。

---

## 1. 日迴圈執行流程（Daily Loop Architecture）

框架每個交易日按照嚴格的 6 步驟順序執行，確保邏輯的一致性和可重現性。

### 1.1 整體流程圖

```
T 日
├─ Step 1-A: 執行前一日(T-1)的賣單
│            ↓
│            T日開盤成交（剩餘現金 + 平倉所得）
│
├─ Step 1-B: 執行前一日(T-1)的買單
│            ↓
│            從候選池中篩選受信號(signal=1)約束的標的
│            按排序指標(rank_metric)排序後截斷至max_positions
│            T日開盤成交（T+1次日開盤）
│
├─ Step 2: 盤中監控（Intraday Monitoring）
│          ↓
│          對持倉標的逐筆檢查停損模組(is_intraday=True)
│          任何停損觸發立即執行出場
│          設定 exit_pending=True，次日開盤執行
│
├─ Step 3-A: 策略訊號出場
│            ↓
│            讀取策略產生的 signal=-1
│            對持倉標的設定 exit_pending=True
│            出場原因記為 'Strategy_Signal_Exit'
│
├─ Step 3: 產生買單訊號（Strategy Signal Generation）
│          ↓
│          策略執行 generate_signals()，產生 signal=1 或 signal=-1
│          signal=1 的標的加入待買清單
│          signal=-1 的標的在 Step 3-A 處理
│
└─ Step 4: 結算日誌（Logging & Accounting）
           ↓
           更新 daily_log（淨值、持倉數、現金、曝險度）
           記錄所有成交的 trade_log
           計算績效指標（MDD、Sharpe、Sortino 等）
```

### 1.2 關鍵時間邏輯

#### T+1 交易執行語意

訊號在 **T 日結束時產生**，於 **T+1 日開盤成交**：

```python
# T 日結束
signal_t = strategy.generate_signals(data_t)  # signal=1 for 標的A, B, C

# T+1 日開盤（Step 1-B）
for ticker in signal_t[signal_t == 1]:
    entry_price = data_t1.loc[ticker, 'open']  # T+1 日開盤價
    # 成交
```

**好處：**
- 避免 lookahead bias（不用未來資料決定當日交易）
- 模擬真實情況（當日下單→次日開盤成交）
- 確保回測結果可在實盤複現

#### 出場亦遵循 T+1

無論何種出場機制，均在次日開盤執行：

```
T 日監控 → 觸發停損 → T+1 日開盤出場
```

### 1.3 Step 1-B 的候選篩選邏輯

Step 1-B 是決定每日具體持倉的關鍵步驟：

```python
# 1. 篩選 signal=1 的標的
signal_series = today_data['signal']
candidates = signal_series[signal_series == 1].index.tolist()

# 2. 按 rank_metric 排序（通常是 CRSI、RSI、動量等）
candidates_sorted = sorted(
    candidates,
    key=lambda x: today_data.loc[x, 'rank_metric'],
    reverse=not config['ascending']  # ascending=true → 升序（低值優先）
)

# 3. 截斷至 max_positions
to_enter = candidates_sorted[:config['max_positions']]

# 4. 計算倉位大小
for ticker in to_enter:
    entry_price = today_data.loc[ticker, 'open']
    shares = sizer.calculate_shares(
        equity=current_equity,
        entry_price=entry_price,
        stop_price=stop_price  # 來自風險管理模組
    )
    # 成交記錄...
```

**關鍵點：**
- `max_positions=10` 意味著每日最多建立 10 個新倉位
- 排序方向由 `ascending` 控制：
  - `true`：低值優先（CRSI < 30 的標的優先，均值回歸策略常用）
  - `false`：高值優先（動能策略常用）
- 若當日候選數 < max_positions，則全部進場

### 1.4 Step 2 與 Step 3-A 的執行順序

最多三層出場檢查，執行順序不可逆：

```python
# Step 2：盤中監控（優先級最高）
for exit_mod in self.exit_policies:
    if getattr(exit_mod, 'is_intraday', False):  # 盤中模組
        is_hit, _, reason = exit_mod.check(intraday_bar, position)
        if is_hit and not position.get('exit_pending', False):
            position['exit_pending'] = True
            position['exit_reason'] = reason
            break  # ❌ 一旦觸發盤中停損，當日不再檢查後續

# Step 3-A：策略訊號出場（次優先級）
# 僅當 Step 2 未觸發時執行
if not position.get('exit_pending', False):
    if signal == -1:
        position['exit_pending'] = True
        position['exit_reason'] = 'Strategy_Signal_Exit'

# Step 3 的 EOD 出場（最低優先級）
for exit_mod in self.exit_policies:
    if not getattr(exit_mod, 'is_intraday', False):  # EOD 模組
        is_hit, _, reason = exit_mod.check(eod_bar, position)
        if is_hit and not position.get('exit_pending', False):
            position['exit_pending'] = True
            position['exit_reason'] = reason
            break  # 只執行第一個觸發的 EOD 模組
```

**執行規則：**
| 優先級 | 層次 | 觸發時機 | 特性 |
|------|------|---------|------|
| 1 | 盤中停損 | Step 2 | 當日即時檢查，立即標記出場 |
| 2 | 策略訊號 | Step 3-A | 當日檢查，次日開盤執行 |
| 3 | 收盤出場 | Step 3 EOD | 收盤時檢查，最多一個觸發 |

---

## 2. 出場優先級規則（Exit Priority System）

完善的出場優先級確保策略邏輯清晰且無衝突。

### 2.1 四層出場機制

框架支援 4 種出場方式，優先級遞減：

#### 第 1 層：盤中即時停損（Intraday Stops）

**特性：**
- `is_intraday = True`
- 檢查：每日 Step 2 盤中監控
- 執行：當日觸發當日標記，T+1 日開盤執行
- 代表：`FixedPercentStop`（固定百分比停損）、`ATRTrailingStop`（ATR 追蹤停損）

**優勢：**
最快反應風險，防止大虧損擴大。

**邏輯：**
```python
class FixedPercentStop(ExitBase):
    is_intraday = True  # 盤中監控

    def __init__(self, stop_pct=0.02):  # 預設 2% 止損
        self.stop_pct = stop_pct

    def check(self, bar, position):
        """檢查當前 bar 是否觸及停損線"""
        entry_price = position['entry_price']
        stop_price = entry_price * (1 - self.stop_pct)

        # 若當日最低價 <= 停損價，觸發
        if bar['low'] <= stop_price:
            return True, stop_price, "FixedPercentStop"
        return False, None, None
```

#### 第 2 層：策略訊號出場（Strategy Signal Exit）

**特性：**
- 檢查：Step 3-A（在 EOD 出場前）
- 執行：當日標記，T+1 日開盤執行
- 代表：策略產生 `signal=-1`

**優勢：**
遵循策略邏輯，如 CRSI 均值回歸的賣出訊號。

**邏輯：**
```python
# Step 3-A: 策略訊號出場
if 'signal' in todays_data:
    signal_series = todays_data['signal']
    for ticker in signal_series[signal_series == -1].index:
        if ticker in self.positions:
            pos = self.positions[ticker]
            if not pos.get('exit_pending', False):
                pos['exit_pending'] = True
                pos['exit_reason'] = 'Strategy_Signal_Exit'
```

#### 第 3 層：收盤出場模組（End-of-Day Exits）

**特性：**
- `is_intraday = False`
- 檢查：Step 3 最後
- 執行：T+1 日開盤
- 代表：`NBarExit`（N 日持倉期限）、`IndicatorExit`（指標收盤檢查）

**優勢：**
基於完整日線資料的出場決策，無須盤中即時計算。

**邏輯：**
```python
class NBarExit(ExitBase):
    is_intraday = False  # 收盤檢查

    def __init__(self, max_bars=5):  # 最多持倉 5 天
        self.max_bars = max_bars

    def check(self, bar, position):
        bars_held = bar['date'] - position['entry_date']
        if bars_held >= self.max_bars:
            return True, bar['close'], "NBarExit"
        return False, None, None
```

#### 第 4 層：主動平倉（Manual Exit）

當天數到期或其他硬性條件觸發，由系統自動清倉。

### 2.2 多模組觸發時的優先順序

同一天若多個模組皆觸發，執行規則：

```python
# ✅ 正確做法：優先級遞減，只執行一個
position = self.positions['STOCK_A']

# 第一步：檢查盤中停損（優先級最高）
for intraday_mod in [FixedPercentStop(), ATRTrailingStop()]:
    if intraday_mod.check(...)[0]:  # 若触發
        position['exit_pending'] = True
        break  # 停止檢查，不再看後續模組

# 如果盤中未觸發，檢查策略訊號
if not position.get('exit_pending'):
    if signal_of_A == -1:
        position['exit_pending'] = True
        break

# 最後檢查 EOD 模組
if not position.get('exit_pending'):
    for eod_mod in [NBarExit(), IndicatorExit()]:
        if eod_mod.check(...)[0]:
            position['exit_pending'] = True
            break  # 只執行第一個觸發的 EOD 模組

# ❌ 錯誤做法：多個模組都執行
# 會導致出場重複記錄、績效計算紊亂
```

### 2.3 出場日誌（exit_reason 欄位）

`trade_log` 的 `reason` 欄位記錄出場原因，用於事後分析：

```python
trade_log = [
    {
        'ticker': 'STOCK_A',
        'entry_date': '2024-01-05',
        'exit_date': '2024-01-08',
        'reason': 'FixedPercentStop',      # 盤中停損
        'entry_price': 100.0,
        'exit_price': 97.5,
        'pnl': -2.5,
    },
    {
        'ticker': 'STOCK_B',
        'entry_date': '2024-01-05',
        'exit_date': '2024-01-10',
        'reason': 'Strategy_Signal_Exit',  # 策略訊號
        'entry_price': 50.0,
        'exit_price': 52.5,
        'pnl': 2.5,
    },
    {
        'ticker': 'STOCK_C',
        'entry_date': '2024-01-05',
        'exit_date': '2024-01-09',
        'reason': 'NBarExit',              # N 日期限
        'entry_price': 75.0,
        'exit_price': 75.5,
        'pnl': 0.5,
    },
]
```

---

## 3. 資金管理與倉位計算（Position Sizing Logic）

科學的倉位管理是風控的核心，框架提供兩種方式，並在無停損時自動 fallback。

### 3.1 FixedRiskSizer（風險基礎倉位管理）

基於每筆風險金額計算倉位。

#### 正常路徑（有停損）

```python
class FixedRiskSizer:
    def __init__(self, risk_pct=0.01, max_pos_pct=0.1):
        self.risk_pct = risk_pct          # 單筆風險佔資本 1%
        self.max_pos_pct = max_pos_pct    # 單筆最大投入資本 10%

    def calculate_shares(self, equity, entry_price, stop_price):
        """
        計算購買股數

        參數：
            equity: 帳戶淨值（如 100 萬）
            entry_price: 進場價格（如 100 元）
            stop_price: 停損價格（如 90 元）

        返回：購買股數（整數）
        """

        if entry_price <= 0:
            return 0

        # 路徑1：有停損時的正常邏輯
        if stop_price > 0:
            # 計算風險金額
            risk_per_share = entry_price - stop_price       # 100 - 90 = 10 元/股
            total_risk_allowed = equity * self.risk_pct     # 100 萬 × 1% = 10,000 元
            shares_by_risk = int(total_risk_allowed / risk_per_share)  # 10,000 / 10 = 1,000 股

            # 計算資本上限
            max_capital = equity * self.max_pos_pct         # 100 萬 × 10% = 10 萬
            shares_by_capital = int(max_capital / entry_price)  # 10 萬 / 100 = 1,000 股

            # 取較小值
            return min(shares_by_risk, shares_by_capital)   # min(1000, 1000) = 1,000 股

        # 路徑2：無停損時的 Fallback（P0-3 修復）
        else:
            target_capital = equity * self.max_pos_pct      # 100 萬 × 10% = 10 萬
            return int(target_capital / entry_price)        # 10 萬 / 100 = 1,000 股
```

#### 計算範例

| 場景 | 資本 | 進場 | 停損 | 風險 | 投入金額 | 股數 |
|-----|------|------|------|------|----------|------|
| 有停損 | 100 萬 | 100 | 90 | 10% | min(1 萬, 10 萬) = 1 萬 | 1,000 |
| 有停損 | 100 萬 | 50 | 45 | 10% | min(1 萬, 10 萬) = 1 萬 | 200 |
| **無停損** | 100 萬 | 100 | 0 | 不適用 | 10% × 100 萬 = 10 萬 | **1,000** |
| **無停損（舊）** | 100 萬 | 100 | 0 | 1% | 1% × 100 萬 ÷ 100 = 1 萬 | **100**（錯） |

**P0-3 Bug 說明：**
舊邏輯在無停損時 `risk_per_share = 100 - 0 = 100`，導致投入金額極小。修復後判斷 `stop_price <= 0` 直接用 `max_pos_pct` 計算，確保資金充分利用。

### 3.2 EqualWeightSizer（等權重倉位管理）

所有持倉標的分擔相同的資本。

```python
class EqualWeightSizer:
    def __init__(self, max_positions=10, buffer=0.95):
        self.max_positions = max_positions  # 預期最大持倉數
        self.buffer = buffer               # 緩衝比例（預留現金）

    def calculate_shares(self, equity, entry_price, stop_price):
        """
        等權重分配：
        - 每檔標的分配 = (資本 × 緩衝比) / 最大持倉數
        - 停損價格不影響倉位大小（固定金額制）
        """
        if entry_price <= 0:
            return 0

        target_capital_per_stock = (equity * self.buffer) / self.max_positions
        # 100 萬 × 95% / 10 = 9.5 萬 每股

        shares = int(target_capital_per_stock / entry_price)
        # 9.5 萬 / 100 = 950 股

        return shares
```

**適用場景：**
- 未知風險時的平衡策略
- 多因子模型的均衡組合
- 動能輪動策略

### 3.3 max_positions 與倉位計算的互動

`max_positions` 是全局限制，與倉位計算相交互：

```python
# config.yaml
engine:
  max_positions: 10  # 最多同時持倉 10 檔

# test.py
sizer = FixedRiskSizer(risk_pct=0.01, max_pos_pct=0.1)

# engine 每日執行
daily_candidates = 15  # 當日有 15 個買訊號
to_enter = min(daily_candidates, max_positions)  # min(15, 10) = 10
# 只買進前 10 檔最低 CRSI 的標的

# 每筆倉位大小
for ticker in to_enter:
    shares = sizer.calculate_shares(
        equity=990_000,  # 已持倉者的權益
        entry_price=100,
        stop_price=90
    )
    # 約 1,000 股（因為 equity × max_pos_pct = 99 萬 × 10% = 9.9 萬）
    # 但如果 max_pos_pct * equity × 10 = 99 萬（用滿現金），會達到頂峰
```

### 3.4 關鍵設定參數的選擇

| 參數 | 保守 | 標準 | 激進 |
|------|------|------|------|
| `risk_pct` | 0.005 | 0.01 | 0.02 |
| `max_pos_pct`（FixedRiskSizer） | 0.05 | 0.10 | 0.20 |
| `max_positions` | 5 | 10 | 20 |
| `buffer`（EqualWeightSizer） | 0.90 | 0.95 | 1.0 |

**建議：**
- 新策略：保守 → 標準 → 激進（逐步驗證）
- 波動大標的：降低 `risk_pct`、`max_pos_pct`
- 高勝率策略：可提升 `max_positions`、`risk_pct`

---

## 4. 補充：價格系統與轉換

### 4.1 雙價格欄位

框架維護兩套價格：

| 價格類型 | 來源 | 用途 | 例子 |
|---------|------|------|------|
| `raw_price` | 實際成交價 | 進出場成交、手續費計算 | open, high, low, close, volume |
| `adjusted_price` | 除權調整後 | 指標計算（CRSI、RSI 等） | crsi, rsi, momentum 等 |

### 4.2 轉換邏輯

```python
# 若需要將指標值（adjusted_price 基礎）轉換回 raw_price 基礎
adjustment_ratio = raw_close / adjusted_close

# 例：
# raw_close = 100, adjusted_close = 95 (除權)
# adjustment_ratio = 100 / 95 ≈ 1.053

# 若指標基於 adjusted_close = 95 計算停損線 = 90（adjusted）
# 對應 raw 價格 = 90 × 1.053 ≈ 94.77（raw）
raw_stop_price = adjusted_stop_price * adjustment_ratio
```

---

## 總結

核心邏輯的三大支柱：

1. **日迴圈執行流程**：嚴格 6 步驟順序，確保 T+1 邏輯一致
2. **出場優先級規則**：4 層優先級（盤中 > 訊號 > EOD > 主動），防止衝突
3. **資金管理**：FixedRiskSizer 正常路徑 + fallback，EqualWeightSizer 等權重，全局 max_positions 限制

理解這三點，便掌握了框架的核心運作機制。
