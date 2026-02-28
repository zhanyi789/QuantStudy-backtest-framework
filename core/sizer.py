import pandas as pd
import numpy as np
import matplotlib.pyplot as plt



class FixedRiskSizer:
    # 加入 max_pos_pct 參數，預設 1.0 (100% 現金)，保守可設 0.95
    def __init__(self, risk_pct=0.01, max_pos_pct=1.0):
        self.risk_pct = risk_pct
        self.max_pos_pct = max_pos_pct

    def calculate_shares(self, equity, entry_price, stop_price):
        if stop_price >= entry_price: return 0
        
        # 1. 計算基於風險的理想股數 (您的邏輯)
        risk_per_share = entry_price - stop_price
        total_risk_allowed = equity * self.risk_pct
        shares_by_risk = int(total_risk_allowed / risk_per_share)
        
        # 2. 計算基於現金的上限股數 (防爆衝補丁)
        # 看看口袋裡的錢夠買幾股
        max_capital_shares = int((equity * self.max_pos_pct) / entry_price)
        
        # 3. 取兩者較小值
        return min(shares_by_risk, max_capital_shares)
    
    
class FixedWeightSizer:
    """
    固定權重 Sizer (Equal Weight)
    不依賴停損價，單純依照資金比例分配倉位。
    """
    def __init__(self, pos_pct=0.10):
        self.pos_pct = pos_pct      # 預設每檔買 10%

    def calculate_shares(self, equity, entry_price, stop_price=None):
        # 防呆
        if entry_price <= 0: return 0
        
        # 1. 計算目標投入金額
        target_capital = equity * self.pos_pct
        
        # 2. 換算股數
        shares = int(target_capital / entry_price)
        
        return shares
    
import math

class EqualWeightSizer:
    """
    等權重部位管理器
    邏輯：資金總額 / 最大持倉數 = 每檔股票可分配金額
    """
    def __init__(self, max_positions=10, buffer=0.95):
        self.max_positions = max_positions
        self.buffer = buffer # 保留 5% 現金緩衝，避免因價格波動導致下單失敗

    def calculate_shares(self, portfolio_value, entry_price, stop_price=0):
        if entry_price == 0: return 0
        
        # 計算每檔股票的目標金額 (例如 10萬 / 10 = 1萬)
        target_capital = (portfolio_value * self.buffer) / self.max_positions
        
        # 計算股數 (無條件捨去)
        shares = int(target_capital / entry_price)
        return shares



