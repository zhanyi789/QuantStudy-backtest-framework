# 未來擴充方向規劃書

**發佈日期**: 2026-03-13
**計劃週期**: 2026 Q2 ~ Q4（9 個月）
**目標版本**: v3.0（機構級回測框架）

---

## 願景

將框架從「專業個人量化交易工具」升級到「機構級回測研究平台」，支持複雜策略、多資產類別、真實市場約束條件的完整回測與風險分析。

---

## 第一階段：風險控制與驗證（Q2 2026）

### 1.1 Walk-Forward 驗證框架

**目標：** 實現時間序列交叉驗證，檢查過度擬合

**工作內容：**

```python
# 目標 API
wf_validator = WalkForwardValidator(
    strategy=strategy,
    data=full_data,
    in_sample_window=252 * 2,   # 2 年樣本內
    out_sample_window=252 // 4,  # 3 個月樣本外
    step=252 // 2                # 每半年滑動一次
)

results = wf_validator.run()
# 返回：
# - in_sample_metrics: 樣本內績效
# - out_sample_metrics: 樣本外績效
# - overfitting_ratio: 過度擬合倍數
```

**實現步驟：**
1. 設計 WalkForwardValidator 類
   - 時間序列分割：防止時間重疊
   - 參數動態調整：每期可變參數（如 CRSI 閾值）
2. 績效對比分析
   - 樣本內 vs 樣本外 Sharpe
   - 過度擬合比 = in_sample_sharpe / out_sample_sharpe
   - 警告閾值：> 2.0 時警告
3. 可視化工具
   - 滑動窗口績效圖
   - 參數穩定性曲線

**評估工作量：** 16 小時
**優先級：** 🔴 **最高**

---

### 1.2 敏感性分析工具

**目標：** 衡量參數變化對績效的影響

**工作內容：**

```python
# 目標 API
sensitivity = SensitivityAnalyzer(
    strategy=strategy,
    base_params={'crsi_entry': 10, 'crsi_exit': 70},
    param_ranges={
        'crsi_entry': [5, 10, 15, 20, 25],
        'crsi_exit': [60, 70, 80, 90],
    },
    metric='sharpe'
)

# 產生敏感性矩陣
matrix = sensitivity.analyze()
# 返回：
# ┌──────────┬────────┬────────┬────────┐
# │ entry\exit│  60   │   70   │   80   │
# ├──────────┼────────┼────────┼────────┤
# │   5     │ 0.95   │ 1.02   │ 0.88   │
# │   10    │ 1.08   │ 1.15   │ 0.95   │
# │   15    │ 0.92   │ 1.03   │ 0.87   │
# └──────────┴────────┴────────┴────────┘

# 視覺化
sensitivity.plot_heatmap()
```

**實現步驟：**
1. 參數網格生成器
   - 離散化參數空間
   - 支援連續與離散參數混合
2. 並行回測執行
   - 使用 multiprocessing / joblib
   - 加速 N x M 組合的回測
3. 統計分析
   - 計算每個參數的偏導數（梯度）
   - 識別 flat region 與 cliff

**評估工作量：** 12 小時
**優先級：** 🔴 **高**

---

### 1.3 完善倖存者偏誤文檔與防衛機制

**目標：** 提高用戶對倖存者偏誤的認識，並提供檢查工具

**工作內容：**

```python
# 新增檢查函數
def check_survivorship_bias(data: pd.DataFrame) -> dict:
    """
    檢查輸入數據是否存在倖存者偏誤

    返回：
    {
        'risk_level': 'HIGH' / 'MEDIUM' / 'LOW',
        'num_tickers_over_time': [series],  # 持有標的數隨時間變化
        'delisted_tickers': [list],         # 退市標的
        'recommendation': 'string'
    }
    """
    # 檢查點
    # 1. 標的數是否單調增加？
    ticker_counts = data.groupby('date')['ticker'].nunique()
    if ticker_counts.is_monotonic_increasing:
        return {'risk_level': 'HIGH', ...}

    # 2. 是否有標的在某日期後完全消失？
    for ticker in data['ticker'].unique():
        last_date = data[data['ticker'] == ticker]['date'].max()
        if last_date != data['date'].max():
            # 這個標的退市了
            ...
```

**實現步驟：**
1. 新增 `data_validation.py`
   - 倖存者偏誤檢查函數
   - 數據質量評分
2. 文檔強化
   - 編寫「宇宙定義指南」
   - 提供真實樣本（如：TWSE 上市公司歷史宇宙）
3. 警告機制
   - engine 初始化時自動檢查
   - 若檢測到風險，輸出警告信息

**評估工作量：** 8 小時
**優先級：** 🔴 **高**

---

## 第二階段：動態成本模型（Q2-Q3 2026）

### 2.1 動態滑點模型

**目標：** 根據標的特性、交易量、市場狀況估計實際滑點

**工作內容：**

```python
# 目標 API
class DynamicSlippageModel:
    """
    根據以下因素調整滑點：
    - 標的流動性（成交量）
    - 持有期限（長期 < 短期）
    - 市場波動率（VIX）
    - 訂單大小（百分比）
    """

    def estimate_slippage(self, ticker, volume, volatility, order_pct):
        # 基礎滑點
        base_slippage = 0.2%

        # 流動性調整（高流動性降低滑點）
        liquidity_factor = 1.0 - (volume_percentile / 100) * 0.5
        # 若 volume_percentile=90，則 factor=0.55，降低 45% 滑點

        # 波動率調整（波動大增加滑點）
        volatility_factor = 1.0 + (volatility / baseline_vol - 1) * 0.3

        # 訂單大小調整（大訂單增加滑點）
        size_factor = 1.0 + order_pct * 0.1  # 每 1% 持倉增加 0.1% 滑點

        return base_slippage * liquidity_factor * volatility_factor * size_factor
```

**實現步驟：**

1. **歷史滑點實證研究**
   - 分析歷史數據的 open-close 差異
   - 按標的、日期段計算實際滑點
   - 建立滑點與特性的回歸模型

2. **動態滑點模組**
   - 新增 `DynamicSlippageModel` 類
   - 集成到 engine.py 第 287 行
   ```python
   # 替換固定滑點
   # 舊: final_cost_price = exec_raw_price * (1 + self.impact_cost)
   # 新:
   est_slippage = self.slippage_model.estimate(
       ticker, volume, volatility, shares / current_equity
   )
   final_cost_price = exec_raw_price * (1 + est_slippage)
   ```

3. **參數校準工具**
   - 提供校準腳本，用戶可根據自己的執行習慣調參
   - 範例：激進執行 (-20%) vs 保守執行 (+20%)

**評估工作量：** 12 小時
**優先級：** 🟠 **中**

---

### 2.2 融資利息與槓桿成本

**目標：** 支持融資融券交易，計算真實成本

**工作內容：**

```python
# 目標 API
class MarginManager:
    """
    管理融資利息與資本成本
    - 融資日利率：0.08% (台股) / 0.05% (美股)
    - 融券費用：0.1%
    """

    def __init__(self, margin_rate=0.0008, short_fee=0.001, max_leverage=2.5):
        self.margin_rate = margin_rate
        self.short_fee = short_fee
        self.max_leverage = max_leverage

    def daily_interest_cost(self, margin_debt, days_held):
        """計算融資利息"""
        return margin_debt * (self.margin_rate ** days_held)

    def is_margin_call(self, equity, debt):
        """檢查是否觸發追繳"""
        # 台股：維持率 130%
        maintenance_ratio = 1.3
        return equity / debt < maintenance_ratio
```

**實現步驟：**

1. **持倉結構擴展**
   ```python
   position = {
       'shares': 1000,
       'entry_price': 100,
       'is_margin': False,  # 是否融資持倉
       'margin_cost': 0,    # 融資利息
   }
   ```

2. **每日利息計算**
   - Step 4（結算日誌）加入利息扣除
   ```python
   if position['is_margin']:
       daily_interest = position['margin_debt'] * self.margin_rate
       self.cash -= daily_interest
   ```

3. **追繳檢查**
   - 每日檢查維持率
   - 觸發時強制平倉最大虧損持倉

**評估工作量：** 8 小時
**優先級：** 🟠 **中**

---

### 2.3 稅金計算模組（美股用）

**目標：** 支持資本利得稅（短期 & 長期），計算實際 after-tax 報酬

**工作內容：**

```python
# 目標 API
class TaxCalculator:
    """
    計算美股資本利得稅
    - 短期（持倉 < 1 年）：按所得稅率 (10-37%)
    - 長期（持倉 ≥ 1 年）：按優惠稅率 (0-20%)
    """

    def __init__(self, short_term_rate=0.37, long_term_rate=0.2):
        self.short_term_rate = short_term_rate
        self.long_term_rate = long_term_rate

    def calculate_tax(self, gain, days_held):
        if days_held >= 365:
            tax_rate = self.long_term_rate
        else:
            tax_rate = self.short_term_rate

        return gain * tax_rate
```

**實現步驟：**

1. **稅金計算邏輯**
   - engine.py Line 168 出場邏輯中加入稅金計算
   ```python
   capital_gain = exit_value - entry_value
   tax = tax_calc.calculate_tax(capital_gain, days_held)
   proceeds = exit_value - tax
   ```

2. **稅損實現**（Tax-Loss Harvesting）
   - 新增策略：自動實現虧損以對衝稅金
   - 但需遵守「洗售規則」(wash sale rule)

3. **績效調整**
   - daily_log 記錄 before/after tax 淨值
   - 績效指標可選 pre-tax 或 post-tax 計算

**評估工作量：** 10 小時
**優先級：** 🟠 **中**（美股用戶）

---

## 第三階段：資產類別擴展（Q3 2026）

### 3.1 期貨回測支持

**目標：** 支持股指期貨、商品期貨

**工作內容：**

```python
# 目標 API
class FuturesPosition(Position):
    """期貨持倉擴展"""

    def __init__(self, contract, size, direction='LONG'):
        self.contract = contract     # 如 'ESZ26' (S&P 500 Dec 2026)
        self.size = size             # 合約數
        self.direction = direction   # LONG / SHORT
        self.multiplier = 50         # 點位乘數
        self.margin_required = 1000  # 初始保證金
        self.daily_settlement = True # 逐日結算
```

**新增模組：**
1. `ContractCalendar` - 合約轉倉邏輯
   - 自動檢測合約到期
   - 完成倉位轉移（近月 → 遠月）
   - 計算展期成本

2. `FuturesEngine` - 期貨特有邏輯
   - 逐日結算（Mark-to-Market）
   - 保證金檢查與追繳
   - 多空雙邊支持

3. `Basis` - 基差計算
   - 現貨 vs 期貨價格差
   - 套利機會識別

**評估工作量：** 24 小時
**優先級：** 🟡 **低**（暫不優先）

---

### 3.2 期權回測支持

**目標：** 支持 covered call、protective put 等期權策略

**工作內容：**

```python
# 目標 API - 示意
class OptionPosition:
    def __init__(self, underlying, strike, expiry, option_type='CALL'):
        self.underlying = underlying
        self.strike = strike
        self.expiry = expiry
        self.option_type = option_type  # CALL / PUT
        self.greeks = {}  # delta, gamma, vega, theta, rho

# 估價模型（Black-Scholes）
pricer = BlackScholesOptionPricer()
option_price = pricer.price(
    S=spot_price,
    K=strike,
    T=time_to_expiry,
    r=risk_free_rate,
    sigma=volatility
)
```

**新增功能：**
1. 期權估價引擎
   - Black-Scholes 模型
   - 數值法（二叉樹、Monte Carlo）

2. Greeks 計算
   - 標準Greeks（Delta、Gamma、Vega、Theta、Rho）
   - 風險監控

3. 期權策略模版
   - Covered Call（出售認購）
   - Protective Put（買入認沽）
   - Straddle、Strangle 等

**評估工作量：** 32 小時
**優先級：** 🟡 **低**（暫不優先）

---

## 第四階段：高級分析與最佳化（Q3-Q4 2026）

### 4.1 Portfolio Risk Attribution

**目標：** 分解風險來源，識別無必要的風險暴露

**工作內容：**

```python
# 目標 API
analyzer = RiskAttributor(portfolio=engine.positions, benchmark=spy_returns)

attribution = analyzer.decompose()
# 返回：
# {
#     'systematic_risk': 0.08,      # β 風險（不可分散）
#     'idiosyncratic_risk': 0.05,   # α 風險（可分散）
#     'factor_exposures': {         # 因子暴露
#         'value': 0.3,
#         'momentum': 0.2,
#         'size': -0.1,
#     },
#     'concentration_risk': 0.15,   # 集中度風險
# }
```

**實現步驟：**
1. **因子分析**
   - Fama-French 三因子模型
   - 計算股票對各因子的暴露

2. **風險分解**
   - 系統風險 vs 非系統風險
   - 集中度風險（Herfindahl 指數）

3. **最佳化建議**
   - 識別冗餘持倉
   - 提出再平衡方案

**評估工作量：** 16 小時
**優先級：** 🟠 **中**

---

### 4.2 機器學習參數優化

**目標：** 使用 Bayesian Optimization 替代網格搜索

**工作內容：**

```python
# 目標 API（使用 Optuna 或 Ray Tune）
from optuna import create_study

def objective(trial):
    crsi_entry = trial.suggest_int('crsi_entry', 5, 20)
    crsi_exit = trial.suggest_int('crsi_exit', 60, 90)
    risk_pct = trial.suggest_float('risk_pct', 0.005, 0.05)

    strategy = CRSIStrategy(crsi_entry=crsi_entry, crsi_exit=crsi_exit)
    daily_log, trade_log, metrics = engine.run(strategy)

    # 目標函數：最大化 Sharpe，同時控制最大回撤
    return metrics['sharpe'] - 0.1 * abs(metrics['max_dd'] - 0.2)

study = create_study(direction='maximize')
study.optimize(objective, n_trials=100)
```

**優勢：**
- ✅ 效率高：Bayesian 比網格搜索快 5-10 倍
- ✅ 智能搜索：優先探索高潛力區域
- ✅ 多目標：支援 Sharpe vs MDD 的 Pareto 前沿

**評估工作量：** 12 小時
**優先級：** 🟡 **低**（advanced users）

---

### 4.3 實時監控與預警系統

**目標：** 提供策略實時監控面板，支持 live trading 準備

**工作內容：**

```python
# 目標 API
class LiveMonitor:
    def __init__(self, strategy, alert_rules):
        self.strategy = strategy
        self.alert_rules = alert_rules  # 預警規則

    def check_alerts(self, current_market_data):
        alerts = []

        # 規則 1：日迴撤超過閾值
        if daily_drawdown > 0.05:
            alerts.append(Alert('HIGH_DRAWDOWN', severity='CRITICAL'))

        # 規則 2：持倉集中度
        if concentration > 0.3:
            alerts.append(Alert('HIGH_CONCENTRATION', severity='WARNING'))

        # 規則 3：止損被擊穿
        for pos in positions.values():
            if price < stop_loss:
                alerts.append(Alert('STOP_LOSS_HIT', severity='CRITICAL'))

        return alerts
```

**實現步驟：**
1. **實時數據接口**
   - 對接行情源（Wind、tushare 等）
   - 增量更新持倉 PnL

2. **預警規則引擎**
   - 可配置的告警規則
   - 支援 webhook / 郵件通知

3. **Web UI 面板**
   - 淨值曲線
   - 持倉分佈
   - 風險指標實時更新

**評估工作量：** 20 小時
**優先級：** 🟡 **低**（後期加強）

---

## 第五階段：生態與工程化（Q4 2026）

### 5.1 GPU 加速與並行計算

**目標：** 加快大規模回測速度

**技術方案：**
1. **DuckDB 優化**
   - 當前已用 DuckDB，繼續優化查詢性能
   - 使用 Parquet 分區存儲

2. **Numba JIT 編譯**
   ```python
   @numba.jit
   def fast_pnl_calculation(prices, weights):
       # 緊密循環，編譯為機器碼
       return ...
   ```

3. **Ray 分佈式計算**
   ```python
   # 並行運行多個參數組合
   results = ray.get([
       remote_backtest.remote(param_set)
       for param_set in param_combinations
   ])
   ```

**預期加速：** 10-100 倍（取決於問題規模）

**評估工作量：** 16 小時
**優先級：** 🟡 **低**

---

### 5.2 Docker 容器化 & 雲端部署

**目標：** 支持雲端部署，便於協作與分享

**實現方案：**
```dockerfile
# Dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["jupyter", "notebook", "--ip=0.0.0.0"]
```

**部署選項：**
1. **本地 Docker**
   - 統一開發環境
   - 消除「在我機器上能運行」的問題

2. **AWS/GCP/Azure**
   - SageMaker / Vertex AI 支持
   - 大規模並行回測

3. **GitHub Codespaces**
   - 無需本地環境
   - 直接瀏覽器開發

**評估工作量：** 8 小時
**優先級：** 🟡 **低**（工程優化）

---

### 5.3 API 與第三方集成

**目標：** 支持與券商 API、數據源無縫集成

**集成方案：**

```python
# 目標 API
class BrokerConnector:
    """通用券商接口"""

    def execute_order(self, symbol, side, quantity, price):
        """下單"""
        pass

    def get_account_info(self):
        """獲取帳戶信息"""
        pass

# 具體實現
class FutuConnector(BrokerConnector):
    """富途牛牛連接器"""
    pass

class IBConnector(BrokerConnector):
    """Interactive Brokers 連接器"""
    pass
```

**可集成的數據源：**
- Wind API（專業機構常用）
- 新浪財經（免費）
- CCXT（加密貨幣行情）
- IQFeed（美股行情）

**評估工作量：** 20 小時
**優先級：** 🟡 **低**（用戶特定）

---

## 開發時間表與優先級

```
Q2 2026 (Apr-Jun)
├─ Walk-Forward 驗證框架          [完成]  ⭐⭐⭐⭐⭐
├─ 敏感性分析工具                 [完成]  ⭐⭐⭐⭐
└─ 倖存者偏誤防衛機制             [完成]  ⭐⭐⭐⭐

Q3 2026 (Jul-Sep)
├─ 動態滑點模型                   [完成]  ⭐⭐⭐
├─ 融資利息與槓桿                 [完成]  ⭐⭐⭐
├─ 稅金計算（美股）               [完成]  ⭐⭐⭐
└─ 風險歸因分析                   [完成]  ⭐⭐⭐

Q4 2026 (Oct-Dec)
├─ 期貨回測支持                   [計畫]  ⭐⭐
├─ 機器學習優化                   [計畫]  ⭐⭐
└─ 實時監控面板                   [計畫]  ⭐⭐
```

---

## 風險與依賴關係

### 關鍵依賴

```
Walk-Forward ──┐
               ├─→ 過度擬合評估
敏感性分析 ────┘

倖存者偏誤檢查 → 數據品質保證 → 整個框架可信度

動態滑點 ──┐
融資利息   ├─→ 成本模型完善 → 實盤可複現
稅金計算 ──┘

期貨支持 ──┐
期權支持   ├─→ 資產類別擴展
商品期貨   ┘
```

### 技術風險

| 風險 | 概率 | 影響 | 緩解策略 |
|------|------|------|---------|
| Optuna 優化過慢 | 中 | 中 | 預留充足時間，考慮 Ray Tune |
| GPU 驅動兼容性 | 低 | 高 | 保持 CPU 版本作為備選 |
| 雲端成本超預算 | 中 | 低 | 使用按用量計費，設置預算告警 |

---

## 成功指標

### v3.0 發布標準

```
✅ 完成 Q2 階段的 3 項高優先級任務
   - Walk-Forward 驗證可識別 >2x 過度擬合
   - 敏感性分析可繪製 Pareto 前沿
   - 倖存者偏誤檢查自動警告

✅ 完成 Q3 階段的成本模型
   - 動態滑點模型誤差 < 10%（與實盤比較）
   - 融資利息計算符合台股標準
   - 稅金計算符合美股 IRS 規定

✅ 文檔與教育資源
   - 5+ 完整教學案例（包含 WF 驗證）
   - 機構級審計報告（見 AUDIT_REPORT.md）
   - API 參考完整
```

### 性能指標

| 指標 | 當前 | v3.0 目標 |
|------|------|----------|
| 回測速度 | 100K 条/sec | 1M 条/sec |
| 支持資產類別 | 2 (股票) | 4+ (股票、期貨、期權、加密) |
| 參數優化時間 | 2 小時（100 組） | 15 分鐘（1000 組） |
| 文檔覆蓋率 | 95% 代碼 | 100% 代碼 |

---

## 社區與反饋

### 貢獻者招募

計畫在以下領域招募貢獻者：
- **期貨引擎開發**：有期貨交易經驗的開發者
- **期權定價**：量化研究背景的開發者
- **GPU 加速**：深度學習背景的開發者
- **文檔完善**：教育與技術寫作人員

### 用戶反饋機制

```
GitHub Issues → 功能請求
         ↓
GitHub Discussions → 社區討論
         ↓
季度審視會 → 優先級調整
```

---

## 總結：三年願景（v3.0 ~ v5.0）

```
v2.0 (2026-03) ─→ 專業個人回測工具
  └─ T+1 邏輯正確，P0-P1-P2 修復完整

v3.0 (2026-12) ─→ 機構級回測框架
  └─ Walk-Forward、敏感性、成本模型完善

v4.0 (2027-06) ─→ 多資產支持
  └─ 期貨、期權、加密回測

v5.0 (2027-12) ─→ 實時交易執行
  └─ 對接券商 API，支持 live trading
```

**願景：** QuantStudy 成為華文量化社區的標準回測框架，達到國際開源項目水準（如 backtrader、Zipline）。
