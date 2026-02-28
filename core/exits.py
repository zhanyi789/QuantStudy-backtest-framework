import pandas as pd
import numpy as np
from abc import ABC, abstractmethod

# ==========================================
# 1. 抽象介面 (Interface)
# ==========================================

class ExitBase(ABC):
    """ 所有出場策略的基底 """
    @abstractmethod
    def check(self, bar, position_data):
        """
        檢查是否觸發出場
        bar: 當日的 OHLCV 資料 (dict or series)
        position_data: 持倉資訊 {'entry_price': ..., 'shares': ..., 'entry_date': ...}
        
        Returns:
            triggered (bool): 是否觸發
            price (float): 出場價格
            reason (str): 出場理由
        """
        pass

class RiskProvider(ABC):
    """ 
    介面：任何可以提供 '停損距離' 的模組都要繼承此類 
    這樣 Sizer 才知道要怎麼算股數
    """
    @abstractmethod
    def get_stop_price(self, bar, entry_price, action):
        """ 計算初始停損價 """
        pass

# ==========================================
# 2. 具體出場模組 (Exits)
# ==========================================

class FixedPercentStop(ExitBase, RiskProvider):
    """ 固定百分比停損 (硬停損) """
    def __init__(self, pct=0.05):
        self.pct = pct  # e.g. 0.05 = 5%

    def get_stop_price(self, bar, entry_price, action):
        # 實作 RiskProvider，給 Sizer 用
        if action == 'BUY':
            return entry_price * (1 - self.pct)
        return entry_price * (1 + self.pct)

    def check(self, bar, position):
        # 檢查盤中是否觸發
        entry_price = position['entry_price']
        
        # 多單邏輯
        stop_price = entry_price * (1 - self.pct)
        
        # 1. 檢查開盤是否直接跳空跌破
        if bar['open'] < stop_price:
            return True, bar['open'], "StopLoss_Gap"
            
        # 2. 檢查盤中最低價是否觸及
        if bar['low'] < stop_price:
            return True, stop_price, "StopLoss_Touch"
            
        return False, None, None

class ATRTrailingStop(ExitBase, RiskProvider): 
    """
    強健版 ATR 追蹤停損 (Robust ATR Trailing Stop)
    能夠自動適應各種 ATR 欄位名稱，並確保邏輯正確。
    """
    def __init__(self, multiplier=3.0, period=14):
        self.multiplier = multiplier
        self.period = period

    # 這個函數是專門給 Sizer 計算「進場當下」的初始風險用的
    def get_stop_price(self, bar, entry_price, action):
        # 嘗試讀取 ATR
        atr = bar.get('atr', 
              bar.get('ATR', 
              bar.get(f'atr_{self.period}', 
              bar.get(f'ATR_{self.period}', 0))))
        
        # 防呆機制：如果剛好那檔股票那天空缺 ATR，就給一個極寬的 10% 預設停損避免報錯
        if atr == 0 or pd.isna(atr):
            return entry_price * 0.9 if action == 'BUY' else entry_price * 1.1
            
        # 計算初始停損價 (買進價 - N倍ATR)
        if action == 'BUY':
            return entry_price - (atr * self.multiplier)
        return entry_price + (atr * self.multiplier)

    def check(self, bar, pos):
        # 1. 嘗試讀取 ATR 
        atr = bar.get('atr', 
              bar.get('ATR', 
              bar.get(f'atr_{self.period}', 
              bar.get(f'ATR_{self.period}', 0))))
        
        # 2. 安全防護：如果 ATR 是 0，代表數據缺失，絕對不觸發停損 (Pass)
        if atr == 0 or pd.isna(atr):
            return False, None, None

        # 3. 取得目前持倉的最高價 (High Water Mark)
        high_water_mark = pos.get('highest_price', pos['entry_price'])
        
        # 4. 計算停損價
        stop_price = high_water_mark - (atr * self.multiplier)
        
        # 5. 判斷是否觸發
        # 只有當「最低價」跌破「停損價」才出場
        if bar['low'] < stop_price:
            return True, stop_price, "ATR_Trailing"
            
        return False, None, None
    
class NBarExit(ExitBase):
    """ N Bar 時間出場 """
    def __init__(self, n=5):
        self.n = n

    def check(self, bar, position):
        # 計算持有天數
        days_held = (bar['date'] - position['entry_date']).days
        # 注意：這裡是簡化計算，嚴謹要算交易日 index 差
        # 我們假設 engine 會傳入 bars_held 計數
        
        current_bars_held = position.get('bars_held', 0)
        
        if current_bars_held >= self.n:
            return True, bar['close'], f"TimeExit_{self.n}Bars"
        
        return False, None, None

class IndicatorExit:
    """
    指標出場策略
    邏輯：當某個指標 (如 CRSI) > 門檻值，就出場。
    """
    def __init__(self, indicator='crsi', threshold=70, logic='>'):
        self.indicator = indicator # 要監控的指標名稱
        self.threshold = threshold # 門檻 (例如 70)
        self.logic = logic         # 大於還是小於

    def check(self, bar, pos):
        # 1. 取得指標數值 (Engine 會把指標放在 bar 裡面)
        val = bar.get(self.indicator)
        
        # 防呆：如果沒這個指標，就不做事
        if val is None: 
            return False, None, None

        # 2. 判斷是否觸發
        should_exit = False
        if self.logic == '>' and val > self.threshold:
            should_exit = True
        elif self.logic == '<' and val < self.threshold:
            should_exit = True
            
        # 3. 如果觸發，回傳 (True, 出場價, 原因)
        if should_exit:
            # 指標出場通常是用「收盤價」結算 (因為盤中不確定收盤會不會站上)
            return True, bar['close'], f"{self.indicator}_{self.logic}_{self.threshold}"
            
        return False, None, None
    
class RankExit(ExitBase):
    """
    動能策略專用：排名出場
    邏輯：
    1. 讀取 bar 裡面的 'exit_rank' (這是我們為了騙過 Engine 特地做的欄位)。
    2. 如果排名掉出 Top N (例如變成第 11 名)，就賣出。
    3. 如果排名是 9999 (代表無效數據)，則 "不動作 (Hold)"，避免因數據缺失誤砍單。
    """
    def __init__(self, top_n=10):
        self.top_n = top_n

    def check(self, bar, position):
        # 1. 取得當前排名 
        # [關鍵修改] 這裡要讀取 'exit_rank'，因為 'rank' 不會被 Engine 傳進來
        current_rank = bar.get('exit_rank', 9999)
        
        # 2. 防呆機制：過濾無效數據
        # 如果 rank 是 9999 (代表今天沒數據)，我們選擇 "不動 (Return False)"
        # 邏輯：9999 > 10 會由下面的邏輯觸發賣出，所以這裡要先攔截
        if current_rank >= 9999:
            return False, None, None

        # 3. 執行汰弱留強
        # 只有在 "有效排名" (例如 1~500) 的情況下才比較
        # 如果排名 (e.g. 15) > 門檻 (10) -> 賣出
        if current_rank > self.top_n:
            return True, bar['close'], f"RankDrop_to_{int(current_rank)}"
            
        # 如果還在榜單內 (rank <= top_n)，繼續持有
        return False, None, None
    

class BufferedRankExit(RankExit):
    def __init__(self, sell_rank=20):
        self.sell_rank = sell_rank # 設定較寬的賣出線

    def check(self, bar, position):
        if bar.get('is_rebalance', 0) == 0:
            return False, None, None # 如果不是換倉日，直接跳過檢查 (死抱)

        current_rank = bar.get('exit_rank', 9999)
        
        if current_rank >= 9999: return False, None, None

        # 關鍵差異：使用 sell_rank (20) 而不是 top_n (10)
        if current_rank > self.sell_rank:
            return True, bar['close'], f"RankDrop_to_{int(current_rank)}"
            
        return False, None, None
    

class PeriodicRebalanceExit(ExitBase):
    """ 
    動態調倉專用出場模組
    邏輯：只要看到策略發出的 force_exit 訊號，就強制在隔天開盤賣出。
    """
    def check(self, bar, position):
        if bar.get('force_exit', 0) == 1:
            return True, bar['close'], "Force_Rebalance"
        return False, None, None