# 變更日誌（CHANGELOG）

## [2.0] - 2026-03-13

### 🔧 P0 階段：緊急修復（高優先 Bug）

#### P0-1：max_positions 完全失效
**問題**：test_ipynb 的 test_config 缺少 max_positions key，engine.py 讀到 0，導致持倉無上限

**根本原因**：
- config.yaml 中 max_positions 只在 `sizers.EqualWeightSizer` 子區段
- 引擎無法直接讀取
- 每日迴圈依賴實例屬性 `self.max_positions`，未正確初始化

**修復方案**：
1. config.yaml 新增頂層 `engine:` 區段，包含 `max_positions`、`rank_metric`、`ascending`
2. engine.py `__init__` 讀取 `engine_cfg = config.get('engine', {})` 存為實例屬性
3. 將所有 `self.config.get('max_positions', 0)` 替換為 `self.max_positions`
4. test_ipynb test_config 加入 `'max_positions': 10`

**驗證**：
```python
# 預期：daily_df['positions'].max() <= 10
# 實際：確認最大觀測值不超過設定值
```

**文件變更**：
- [config.yaml](config.yaml#L13-L16)：新增 engine: 區段
- [core/engine.py](core/engine.py#L29-L31)：讀取 engine_cfg 存為實例屬性
- [core/engine.py](core/engine.py#L238)：Step 1-B 使用 self.max_positions
- [core/engine.py](core/engine.py#L414-L425)：Step 3 排序和截斷使用 self.max_positions

---

#### P0-2：slippage_pct vs slippage_percent key 不一致
**問題**：config.yaml 和 test_config 寫 `slippage_pct`，但 engine.py 讀 `slippage_percent`

**根本原因**：
- 引擎舊代碼寫法與新配置不同步
- 靠預設值 0.002 湊巧相同，隱蔽性強

**修復方案**：
- [core/engine.py](core/engine.py#L25)：改為同時支援兩個 key
```python
self.impact_cost = config.get('slippage_pct', config.get('slippage_percent', 0.002))
```

**驗證**：
```python
# 預期：engine.impact_cost 讀到傳入值（如 0.001）
# 實際：確認數值一致
```

---

#### P0-3：無停損時 stop_price=0 倉位極小
**問題**：當無風險停損模組時，stop_price=0，FixedRiskSizer 只投入 1% 資本，遠低於預期 10%

**根本原因**：
- FixedRiskSizer 計算 `risk_per_share = entry_price - stop_price = entry_price - 0 = entry_price`
- `shares = (equity × 1%) / entry_price`，資金利用率極低
- 無 fallback 邏輯處理無停損情況

**修復方案**：
1. [core/sizer.py](core/sizer.py#L9-L11)：FixedRiskSizer 新增 `max_pos_pct=1.0` 參數
2. [core/sizer.py](core/sizer.py#L17-L21)：加入 stop_price ≤ 0 的 fallback 路徑
```python
if stop_price <= 0:
    target_capital = equity * self.max_pos_pct
    return int(target_capital / entry_price)
```
3. [test.ipynb](test.ipynb)：sizer 初始化傳入 `max_pos_pct=0.10`

**驗證**：
```python
# 預期：平均每筆投入 ≈ 100,000（10% × 1M）
# 實際：確認倉位在合理範圍（~70K-100K）
```

**文件變更**：
- [core/sizer.py](core/sizer.py#L7-L35)：完整改寫 FixedRiskSizer

---

### 🔧 P1 階段：架構改善（設計缺陷）

#### P1-1：signal=-1 出場訊號被完全忽略
**問題**：Engine Step 3 只讀 `signal==1`，完全忽視 `signal==-1`，導致策略無任何出場機制

**根本原因**：
- 原設計假設出場靠保險絲模組，但策略本身無出場訊號通道
- CRSI 策略（crsi > 70 時）產生 signal=-1，卻未被消費
- 結果：持倉永久持有（除非 NBarExit 時間出場）

**修復方案**：
- [core/engine.py](core/engine.py#L396-L405)：新增 Step 3-A
```python
# 處理策略主動出場訊號 (signal == -1)
if 'signal' in todays_data:
    signal_series = todays_data['signal']
    exit_signals = signal_series[signal_series == -1].index.tolist()
    for ticker in exit_signals:
        if ticker in self.positions:
            if not self.positions[ticker].get('exit_pending', False):
                self.positions[ticker]['exit_pending'] = True
                self.positions[ticker]['exit_reason'] = 'Strategy_Signal_Exit'
```

**驗證**：
```python
# 預期：trade_df 中出現 'Strategy_Signal_Exit' 原因的紀錄
strategy_exits = trade_df[trade_df['reason'] == 'Strategy_Signal_Exit']
# 實際：確認有出場紀錄
```

**文件變更**：
- [core/engine.py](core/engine.py#L396-L405)：插入 Step 3-A

---

#### P1-2：字串判斷出場類型脆弱
**問題**：engine.py 第 330 和 359 行用魔法字串 `"Stop" in mod_name or "Trailing" in mod_name` 判斷

**根本原因**：
- 硬編碼字串判斷，新模組若命名含這些字串就誤判
- 無明確介面定義，維護困難

**修復方案**：
1. [core/exits.py](core/exits.py#L11)：ExitBase 新增屬性
```python
class ExitBase(ABC):
    is_intraday: bool = False  # 是否為盤中即時出場
```

2. [core/exits.py](core/exits.py#L28)、[core/exits.py](core/exits.py#L54)：各模組覆寫
```python
class FixedPercentStop(ExitBase, RiskProvider):
    is_intraday = True

class ATRTrailingStop(ExitBase, RiskProvider):
    is_intraday = True

# NBarExit、IndicatorExit 不覆寫，預設 False（EOD）
```

3. [core/engine.py](core/engine.py#L337)、[core/engine.py](core/engine.py#L360)：改用屬性檢查
```python
is_intraday = getattr(exit_mod, 'is_intraday', False)
is_eod = not getattr(exit_mod, 'is_intraday', False)
```

**驗證**：
```python
# 預期：所有出場模組都有 is_intraday 屬性
for exit_mod in engine.exit_policies:
    assert hasattr(exit_mod, 'is_intraday')
```

**文件變更**：
- [core/exits.py](core/exits.py#L9-L11)：ExitBase 新增屬性
- [core/exits.py](core/exits.py#L28)、[core/exits.py](core/exits.py#L54)：各模組覆寫

---

#### P1-3：EOD 優先規則不明確
**問題**：同一天若多個 EOD 出場模組觸發，應只執行第一個，邏輯不直觀

**修復方案**：
- [core/engine.py](core/engine.py#L357-L367)：加入注釋和防衛性檢查
```python
# P1-3: 出場優先規則：盤中 > EOD，EOD 中先觸發優先
for exit_mod in self.exit_policies:
    is_eod = not getattr(exit_mod, 'is_intraday', False)
    if is_eod:
        is_hit, _, reason = exit_mod.check(eod_bar, pos)
        if is_hit:
            if not pos.get('exit_pending', False):  # 防重複
                pos['exit_pending'] = True
                pos['exit_reason'] = reason
            break  # 只執行第一個觸發的 EOD 模組
```

**文件變更**：
- [core/engine.py](core/engine.py#L357-L367)：加註釋和防衛檢查

---

### 🚀 P2 階段：功能擴充

#### P2-1：建立 YAML 設定加載器
**目標**：實現「純 YAML 驅動」，無須手寫 dict

**方案**：
- [core/config_loader.py](core/config_loader.py)：新建模組
```python
def load_config(yaml_path):
    """
    載入 YAML 設定檔並展平結構
    - 提升 system:、engine: 子區段至頂層
    - 讀取 enabled: true 的策略/sizer 參數
    - 返回 flat dict 給 engine
    """
```

**文件變更**：
- [core/config_loader.py](core/config_loader.py)：新建

---

#### P2-2：清理孤兒參數
**問題**：engine.py 第 190 行 `run(self, strategy_instance, max_positions=None)` 未使用

**修復方案**：
- [core/engine.py](core/engine.py#L190)：移除 `max_positions=None`

**文件變更**：
- [core/engine.py](core/engine.py#L190)：函數簽名

---

## 修復前後對比

| 指標 | 修復前 | 修復後 | 改善 |
|-----|-------|-------|------|
| 最大持倉數 | 無限 (max=0) | 10 受限 | ✅ 風控生效 |
| 平均倉位大小 | ~10,000 | ~100,000 | ✅ 資金充分利用 |
| 出場訊號處理 | 無 signal=-1 | 完整 Step 3-A | ✅ 策略出場有效 |
| 出場類型判斷 | 字串比對 (脆弱) | is_intraday 屬性 | ✅ 設計清晰 |
| 設定讀取方式 | flat dict (test.ipynb) | 嵌套 + flat (向後相容) | ✅ 更靈活 |

---

## 測試方法

P0 修復驗證（見 test.ipynb Cell lnuu0pagnsm）：

```python
# 1. max_positions 驗證
max_pos_observed = daily_df['positions'].max()
assert max_pos_observed <= 10

# 2. slippage 驗證
assert abs(engine.impact_cost - 0.001) < 1e-6

# 3. 倉位大小驗證
avg_entry = trade_df['entry_value'].mean()
assert avg_entry > expected_per_trade * 0.5  # 非 P0-3 前的 1% 水準

# 4. signal=-1 出場驗證
strategy_exits = trade_df[trade_df['reason'] == 'Strategy_Signal_Exit']
assert len(strategy_exits) > 0

# 5. is_intraday 屬性驗證
for exit_mod in engine.exit_policies:
    assert hasattr(exit_mod, 'is_intraday')
```

---

## 版本歷史

| 版本 | 日期 | 重點 |
|------|------|------|
| 2.0 | 2026-03-13 | P0-P1-P2 完整修復，架構穩定化 |
| 1.9 | 2026-03-10 | 初始重構版，發現 7 大 Bug |
| 1.0 | 2025-12 | 原始事件驅動引擎 |

---

**維護者**：Ian Chang（量化策略開發）、Claude Code（架構審查與修復）
