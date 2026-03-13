# 貢獻指南（CONTRIBUTING）

感謝對本專案的興趣！本指南說明如何參與開發、報告 Bug、提交功能建議。

## 📋 目錄

1. [行為守則](#行為守則)
2. [報告 Bug](#報告-bug)
3. [提交功能建議](#提交功能建議)
4. [開發環境設置](#開發環境設置)
5. [提交 Pull Request](#提交-pull-request)
6. [程式碼風格](#程式碼風格)
7. [測試規範](#測試規範)

---

## 行為守則

本專案遵循開源社群共同的行為規範。參與者應：
- 尊重所有貢獻者和用戶
- 包容不同的觀點和經驗
- 接受建設性批評
- 專注於社群最佳利益

任何騷擾、仇恨言論或其他不當行為會被拒絕。

---

## 報告 Bug

發現問題時，請提交 Issue 並包含：

### 必填信息
1. **簡潔標題**：「max_positions 在某情況下失效」
2. **重現步驟**：
   ```
   1. 設定 max_positions = 5
   2. 執行包含 10+ 買訊號的策略
   3. 觀察結果
   ```
3. **預期行為**：最多持倉 5 檔
4. **實際行為**：持倉超過 5 檔
5. **環境信息**：
   ```
   - Python 版本：3.9+
   - pandas 版本：2.0.3
   - 操作系統：Windows 11 / macOS / Linux
   - 資料集：S&P 500 2020-2023
   ```

### 可選但重要
- **錯誤日誌或追蹤**：粘貼完整錯誤堆棧
- **最小重現案例 (MRC)**：最簡單的能重現 Bug 的腳本
- **截圖或圖表**：如果涉及績效分析結果

### Bug 標籤
- `bug`：確認的問題
- `critical`：導致回測結果失真（如 P0 級）
- `regression`：新引入的問題
- `documentation`：文檔相關 Bug

---

## 提交功能建議

有新想法？請提交 Feature Request：

### 標準模板
```
## 功能描述
簡述你想要的功能（1-2 句）

## 痛點
目前框架的哪方面不足？

## 建議的解決方案
詳細說明實現方式

## 替代方案
有其他可能的實現方式嗎？

## 附加資訊
截圖、範例程式碼、論文引用等
```

### 好功能建議的特徵
- ✅ 解決真實使用場景
- ✅ 與框架設計哲學一致（YAML 驅動、模組化）
- ✅ 有明確的驗收標準
- ✅ 不破壞既有 API

### 標籤
- `enhancement`：新功能
- `optimization`：性能改進
- `usability`：用戶體驗改善

---

## 開發環境設置

### 前置要求
- Python 3.9+
- Git
- pip 或 conda

### 步驟

1. **Fork 專案**
   ```bash
   git clone https://github.com/YOUR_USERNAME/QuantStudy-backtest-framework.git
   cd QuantStudy-backtest-framework
   ```

2. **建立虛擬環境**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

3. **安裝開發依賴**
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt  # 測試工具、Linter 等
   ```

4. **建立開發分支**
   ```bash
   git checkout -b feature/your-feature-name
   # 或 bugfix/issue-description
   ```

5. **驗證環境**
   ```python
   python -c "from core.engine import AdvancedEventEngine; print('✅ Setup OK')"
   ```

---

## 提交 Pull Request

### 前置檢查
- [ ] 代碼通過 Linter（`flake8`、`black`）
- [ ] 新增單元測試覆蓋
- [ ] 更新文檔和註釋
- [ ] 提交信息清晰有意義

### PR 模板
```markdown
## 關聯 Issue
Fixes #123

## 變更描述
詳細說明做了什麼以及為什麼

## 變更類型
- [ ] Bug 修復
- [ ] 新功能
- [ ] 破壞性變更（請說明影響）
- [ ] 文檔更新

## 驗收標準
- [ ] 邏輯正確（通過代碼審查）
- [ ] 測試通過（單元/集成測試）
- [ ] 性能無迴歸
- [ ] 文檔已更新

## 測試方法
說明如何測試你的變更

## 截圖 / 結果
如果涉及績效分析，粘貼對比結果
```

### 提交流程
```bash
# 確保分支最新
git fetch upstream
git rebase upstream/main

# 提交提交
git add .
git commit -m "fix: 修復 max_positions 讀取邏輯

- 新增 engine: 配置區段
- 將 max_positions 存為實例屬性
- 更新所有讀取位置"

# 推送到 Fork
git push origin feature/your-feature-name

# 在 GitHub UI 中提交 PR
```

### PR 審查流程
1. 至少 1 名維護者審查
2. 所有測試必須通過
3. 無衝突的合併
4. 獲得批准後才能合併

---

## 程式碼風格

### Python 風格指南
遵循 [PEP 8](https://www.python.org/dev/peps/pep-0008/)，部分例外：

```python
# ✅ 好：清晰的變數名，完整的註釋
def calculate_shares(self, equity: float, entry_price: float, stop_price: float) -> int:
    """
    基於風險計算購買股數。

    Args:
        equity: 帳戶淨值
        entry_price: 進場價格
        stop_price: 停損價格

    Returns:
        應購買的股數（整數）
    """
    if entry_price <= 0:
        return 0

    # P0-3: 無停損時的 fallback 邏輯
    if stop_price <= 0:
        target_capital = equity * self.max_pos_pct
        return int(target_capital / entry_price)

    # 正常路徑
    risk_per_share = entry_price - stop_price
    shares_by_risk = int((equity * self.risk_pct) / risk_per_share)
    shares_by_capital = int((equity * self.max_pos_pct) / entry_price)

    return min(shares_by_risk, shares_by_capital)

# ❌ 不好：簡寫變數，無註釋，邏輯不清
def calc_sh(eq, ep, sp):
    if sp <= 0:
        return int(eq * 0.1 / ep)
    return int(min((eq * 0.01) / (ep - sp), (eq * 0.1) / ep))
```

### 註釋規範
- **修復標籤**：`# P0-1: ...` （Bug 修復）
- **新增標籤**：`# 🌟 新增: ...` （功能擴充）
- **段落註釋**：`# --- [描述] ---`
- **行內註釋**：必要時使用，但優先通過好的變數名自文檔化

### 命名規範
| 對象 | 規範 | 例子 |
|-----|------|------|
| 函數/方法 | snake_case | `calculate_shares()` |
| 常數 | UPPER_SNAKE_CASE | `MAX_POSITIONS = 10` |
| 類別 | PascalCase | `FixedRiskSizer` |
| 私有變數 | _leading_underscore | `self._internal_state` |
| 型別標註 | 完整型別提示 | `def run(self, strategy_instance: BaseStrategy) -> tuple` |

---

## 測試規範

### 測試位置
```
tests/
├── unit/                 # 單元測試（函數層級）
│   ├── test_sizer.py
│   ├── test_exits.py
│   └── test_engine.py
├── integration/          # 整合測試（多模組交互）
│   └── test_backtest_flow.py
└── fixtures/            # 測試數據和幫助函數
    └── sample_data.py
```

### 測試框架
使用 `pytest`：

```bash
# 運行所有測試
pytest tests/

# 運行特定文件
pytest tests/unit/test_sizer.py

# 帶覆蓋率報告
pytest --cov=core tests/
```

### 範例：P0-3 修復的測試
```python
import pytest
from core.sizer import FixedRiskSizer

class TestFixedRiskSizer:

    def test_with_stop_price(self):
        """有停損時的正常路徑"""
        sizer = FixedRiskSizer(risk_pct=0.01, max_pos_pct=0.10)
        equity = 1_000_000
        entry_price = 100
        stop_price = 90

        shares = sizer.calculate_shares(equity, entry_price, stop_price)

        # risk_per_share = 10
        # shares_by_risk = 10_000 / 10 = 1,000
        # shares_by_capital = 100_000 / 100 = 1,000
        assert shares == 1_000

    def test_without_stop_price(self):
        """P0-3: 無停損時的 fallback"""
        sizer = FixedRiskSizer(risk_pct=0.01, max_pos_pct=0.10)
        equity = 1_000_000
        entry_price = 100
        stop_price = 0  # 無停損

        shares = sizer.calculate_shares(equity, entry_price, stop_price)

        # target_capital = 100_000
        # shares = 100_000 / 100 = 1_000
        assert shares == 1_000

        # ✅ 驗證：無停損時仍投入 10%（而非舊邏輯的 1%）
        assert shares * entry_price == 100_000

    def test_invalid_entry_price(self):
        """邊界情況：無效進場價"""
        sizer = FixedRiskSizer()
        assert sizer.calculate_shares(1_000_000, -100, 90) == 0
        assert sizer.calculate_shares(1_000_000, 0, 90) == 0
```

### 測試檢查清單
- [ ] 新功能有單元測試
- [ ] Bug 修復附帶測試（驗證修復有效）
- [ ] 邊界情況被涵蓋（0、負數、無資料等）
- [ ] 測試名稱清晰描述場景
- [ ] 測試通過且覆蓋率 > 80%

---

## 常見貢獻場景

### 場景 1：修復 Bug
```bash
# 1. 創建分支
git checkout -b bugfix/max-positions-issue

# 2. 編寫測試（先寫測試，後修復代碼）
# tests/unit/test_engine.py - 驗證 max_positions 生效

# 3. 實現修復
# 修改 core/engine.py

# 4. 驗證測試通過
pytest tests/unit/test_engine.py::test_max_positions_limit

# 5. 提交 PR
# PR 標題：fix: max_positions 讀取邏輯不生效
```

### 場景 2：添加新策略
```bash
# 1. 在 strategies/ 中創建新文件
# strategies/my_strategy.py

# 2. 編寫策略類（繼承 BaseStrategy）

# 3. 添加單元測試
# tests/unit/test_my_strategy.py

# 4. 更新 config.yaml 範例
# strategies: 新增 MyStrategy 配置範例

# 5. 在 README.md 擴展指南中說明用法

# 6. 提交 PR
# PR 標題：feat: 新增 MyStrategy 策略
```

### 場景 3：性能優化
```bash
# 1. 建立基準測試
# tests/performance/benchmark_engine.py

# 2. 實現優化

# 3. 驗證性能改進
pytest tests/performance/benchmark_engine.py

# 4. 提交 PR（包含基準對比）
# PR 標題：perf: 優化 Step 2 盤中監控效率 (20% 加速)
```

---

## 常見問題

### Q：我的 PR 卡在審查中很久
A：維護者通常在 1 周內回應。可以在評論中溫和地提醒。

### Q：我想重寫某個大模組，應該怎樣提出？
A：先開 Issue 討論設計方案，獲得維護者同意後再實施。避免無謂的大改動。

### Q：代碼風格檢查失敗怎麼辦？
A：
```bash
# 自動格式化
black core/ strategies/

# 檢查 lint 錯誤
flake8 core/ strategies/

# 修復
# 手動調整不符合 lint 的部分
```

### Q：如何在本機測試我的修改？
A：
```bash
# 1. 在 test.ipynb 中導入你修改的模組
from core.engine import AdvancedEventEngine

# 2. 執行完整的回測流程
engine = AdvancedEventEngine(config, data_feed=df)
daily_log, trade_log, _ = engine.run(strategy_instance=strategy)

# 3. 驗證結果符合預期
analyzer = PerformanceAnalyzer(daily_log, trade_log)
analyzer.calculate()
```

---

## 資源連結

- [Issue 模板](ISSUE_TEMPLATE/)
- [修復日誌](CHANGELOG.md)
- [API 文檔](docs/API.md)（待補充）
- [量化社群 Slack](https://quantstudyslack.com)（待建立）

---

## 致謝

感謝所有貢獻者、報告 Bug、提供反饋的社群成員。你們的支持讓這個框架持續改進！

---

**最後更新**：2026-03-13
