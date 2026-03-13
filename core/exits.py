import pandas as pd
import numpy as np
from abc import ABC, abstractmethod

# ==========================================
# 1. 抽象介面 (Interface)
# ==========================================

class ExitBase(ABC):
    # P1-2: 宣告是否為盤中即時出場（子類別覆寫此屬性）
    is_intraday: bool = False

    @abstractmethod
    def check(self, bar, position_data):
        pass

class RiskProvider(ABC):
    @abstractmethod
    def get_stop_price(self, bar, entry_price, action):
        pass

# ==========================================
# 2. 具體出場模組 (保險絲與擇時出場)
# ==========================================

class FixedPercentStop(ExitBase, RiskProvider):
    """ 固定百分比停損 (硬停損) """
    is_intraday = True  # P1-2: 盤中即時停損

    def __init__(self, pct=0.05):
        self.pct = pct  

    def get_stop_price(self, bar, entry_price, action):
        if action == 'BUY':
            return entry_price * (1 - self.pct)
        return entry_price * (1 + self.pct)

    def check(self, bar, position):
        entry_price = position['entry_price']
        stop_price = entry_price * (1 - self.pct)
        
        # 1. 檢查開盤是否直接跳空跌破 (以開盤價出場)
        if bar['open'] < stop_price:
            return True, bar['open'], "StopLoss_Gap"
            
        # 2. 檢查盤中最低價是否觸及 (以停損價出場)
        if bar['low'] < stop_price:
            return True, stop_price, "StopLoss_Touch"
            
        return False, None, None

class ATRTrailingStop(ExitBase, RiskProvider):
    """ 強健版 ATR 追蹤停損 """
    is_intraday = True  # P1-2: 盤中即時追蹤停損

    def __init__(self, multiplier=3.0, period=14):
        self.multiplier = multiplier
        self.period = period

    def get_stop_price(self, bar, entry_price, action):
        atr = bar.get('atr', bar.get('ATR', bar.get(f'atr_{self.period}', bar.get(f'ATR_{self.period}', 0))))
        if atr == 0 or pd.isna(atr):
            return entry_price * 0.9 if action == 'BUY' else entry_price * 1.1
            
        if action == 'BUY':
            return entry_price - (atr * self.multiplier)
        return entry_price + (atr * self.multiplier)

    def check(self, bar, pos):
        atr = bar.get('atr', bar.get('ATR', bar.get(f'atr_{self.period}', bar.get(f'ATR_{self.period}', 0))))
        if atr == 0 or pd.isna(atr):
            return False, None, None

        high_water_mark = pos.get('highest_price', pos['entry_price'])
        stop_price = high_water_mark - (atr * self.multiplier)
        
        if bar['low'] < stop_price:
            return True, stop_price, "ATR_Trailing"
            
        return False, None, None
    
class NBarExit(ExitBase):
    """ N Bar 時間出場 """
    def __init__(self, n=5):
        self.n = n

    def check(self, bar, position):
        current_bars_held = position.get('bars_held', 0)
        if current_bars_held >= self.n:
            return True, bar['close'], f"TimeExit_{self.n}Bars"
        return False, None, None

class IndicatorExit(ExitBase):
    """ 指標出場策略 (如 CRSI 超買出場) """
    def __init__(self, indicator='crsi', threshold=70, logic='>'):
        self.indicator = indicator 
        self.threshold = threshold 
        self.logic = logic         

    def check(self, bar, pos):
        val = bar.get(self.indicator)
        if val is None or pd.isna(val): 
            return False, None, None

        should_exit = False
        if self.logic == '>' and val > self.threshold:
            should_exit = True
        elif self.logic == '<' and val < self.threshold:
            should_exit = True
            
        if should_exit:
            return True, bar['close'], f"{self.indicator}_{self.logic}_{self.threshold}"
            
        return False, None, None