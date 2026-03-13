import pandas as pd
import numpy as np
import matplotlib.pyplot as plt



class FixedRiskSizer:
    # max_pos_pct: 單筆最大資金佔比，預設 0.1 (10%)，避免無停損時全押一檔
    def __init__(self, risk_pct=0.01, max_pos_pct=0.1):
        self.risk_pct = risk_pct
        self.max_pos_pct = max_pos_pct

    def calculate_shares(self, equity, entry_price, stop_price):
        if entry_price <= 0:
            return 0

        # P0-3: 無停損 fallback（stop_price <= 0 代表沒有設定停損價）
        # 改用 max_pos_pct 直接計算等額倉位，確保資金充分利用
        if stop_price <= 0:
            target_capital = equity * self.max_pos_pct
            return int(target_capital / entry_price)

        if stop_price >= entry_price:
            return 0

        # 1. 計算基於風險的理想股數
        risk_per_share = entry_price - stop_price
        total_risk_allowed = equity * self.risk_pct
        shares_by_risk = int(total_risk_allowed / risk_per_share)

        # 2. 計算基於現金的上限股數
        max_capital_shares = int((equity * self.max_pos_pct) / entry_price)

        # 3. 取兩者較小值
        return min(shares_by_risk, max_capital_shares)
    
    
class EqualWeightSizer:
    """
    等權重部位管理器 (融合版)
    邏輯：(資金總額 * 緩衝比例) / 最大持倉數 = 每檔股票可分配金額
    """
    def __init__(self, max_positions=10, buffer=0.95):
        self.max_positions = max_positions
        self.buffer = buffer

    def calculate_shares(self, equity, entry_price, stop_price=None): # stop_price 留著當備用參數，保持介面統一
        if entry_price <= 0: 
            return 0
        
        # 計算每檔標的的目標投入金額
        target_capital = (equity * self.buffer) / self.max_positions
        
        # 換算股數 (無條件捨去成整數)
        shares = int(target_capital / entry_price)
        return shares



