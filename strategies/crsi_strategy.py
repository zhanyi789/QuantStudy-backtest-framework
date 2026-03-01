import pandas as pd
import numpy as np
from zoo import Indicators

class CRSI_Reversion_Limit:
    """
    CRSI 消融研究專用版 (8合1 濾網)
    
    特點：
    - 所有濾網參數若設為 0，則視為關閉 (不計算也不過濾)。
    - 支援 8 種濾網疊加測試。
    - 遵守引擎「不深拷貝」黃金法則，確保記憶體安全。
    """
    def __init__(self, 
                 # 1. 核心參數
                 entry_crsi=10, 
                 exit_crsi=70, 
                 limit_pct=0.0,        
                 
                 # 2. 濾網參數 (設為 0 代表關閉)
                 ma_window=0,          
                 min_turnover=0,       
                 spy_ma_window=0,      
                 hv_threshold=0,       
                 adx_threshold=0,      
                 ibs_threshold=0,      
                 gap_threshold=0,      
                 rsi_strength_threshold=0, 
                 
                 # 3. 外部數據
                 benchmark_df=None):   
        
        self.entry_crsi = entry_crsi
        self.exit_crsi = exit_crsi
        self.limit_pct = limit_pct
        
        self.ma_window = ma_window
        self.min_turnover = min_turnover
        self.spy_ma_window = spy_ma_window
        self.hv_threshold = hv_threshold
        self.adx_threshold = adx_threshold
        self.ibs_threshold = ibs_threshold
        self.gap_threshold = gap_threshold
        self.rsi_strength_threshold = rsi_strength_threshold
        self.benchmark_df = benchmark_df
        
        tags = []
        if ma_window > 0: tags.append("MA")
        if spy_ma_window > 0: tags.append("SPY")
        if min_turnover > 0: tags.append("Vol")
        if hv_threshold > 0: tags.append("HV")
        if adx_threshold > 0: tags.append("ADX")
        if ibs_threshold > 0: tags.append("IBS")
        if gap_threshold > 0: tags.append("Gap")
        if rsi_strength_threshold > 0: tags.append("Str")
        
        tag_str = "+".join(tags) if tags else "Raw"
        self.name = f"CRSI({tag_str})"

    def generate_signals(self, df):
        # 🛡️ 絕對防禦領域：建立專屬工作區，保護底層全域資料不被污染！
        out = df.copy()
        
        # ----------------------------------------
        # 1. 基礎指標計算
        # ----------------------------------------
        if 'crsi' not in out.columns:
            out['crsi'] = Indicators.crsi(out, 3, 2, 100)
        
        combined_filter = pd.Series(True, index=out.index)

        # ----------------------------------------
        # 2. 逐一應用 8 大濾網
        # ----------------------------------------
        
        if self.ma_window > 0:
            col_name = f'ma_{self.ma_window}' 
            out[col_name] = Indicators.sma(out, window=self.ma_window)
            combined_filter &= (out['close'] > out[col_name])

        if self.spy_ma_window > 0 and self.benchmark_df is not None:
            spy_data = self.benchmark_df.copy()
            # 🐛 修復：統一抓取小寫的 'close'
            spy_data['spy_ma'] = spy_data['close'].rolling(window=self.spy_ma_window).mean()
            spy_data['spy_bullish'] = (spy_data['close'] > spy_data['spy_ma']).astype(int)
            
            # Left Join 併入個股工作區 (out)
            out = pd.merge(out, spy_data[['date', 'spy_bullish']], on='date', how='left')
            out['spy_bullish'] = out['spy_bullish'].fillna(0) 
            combined_filter &= (out['spy_bullish'] == 1)

        if self.min_turnover > 0:
            if 'turnover_ma' not in out.columns:
                out['turnover_ma'] = Indicators.avg_turnover(out, 20)
            combined_filter &= (out['turnover_ma'] > self.min_turnover)

        if self.hv_threshold > 0:
            if 'hv' not in out.columns:
                out['hv'] = Indicators.hv(out, window=100)
            combined_filter &= (out['hv'] > self.hv_threshold)

        if self.adx_threshold > 0:
            if 'adx' not in out.columns:
                out['adx'] = Indicators.adx(out, window=14)
            combined_filter &= (out['adx'] > self.adx_threshold)

        if self.ibs_threshold > 0:
            if 'ibs' not in out.columns:
                out['ibs'] = Indicators.ibs(out)
            combined_filter &= (out['ibs'] < self.ibs_threshold)

        if self.gap_threshold > 0:
            if 'gap_ratio' not in out.columns:
                out['gap_ratio'] = Indicators.gap_ratio(out)
            combined_filter &= (out['gap_ratio'] > self.gap_threshold)
            
        if self.rsi_strength_threshold > 0:
            if 'rsi_long' not in out.columns:
                out['rsi_long'] = Indicators.rsi(out, window=100)
            combined_filter &= (out['rsi_long'] > self.rsi_strength_threshold)

        # ----------------------------------------
        # 3. 綜合訊號生成
        # ----------------------------------------
        condition = (out['crsi'] < self.entry_crsi) & combined_filter
        out['signal'] = condition.astype(int)
        
        if self.limit_pct is None:
            out['limit_price'] = np.nan 
        else:
            out['limit_price'] = out['close'] * (1 - self.limit_pct)
        
        # ----------------------------------------
        # 4. 出場訊號
        # ----------------------------------------
        out['exit_signal'] = (out['crsi'] > self.exit_crsi).astype(int)
        
        # 🛡️ 回傳專屬的工作區資料
        return out