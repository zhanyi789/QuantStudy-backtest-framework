import pandas as pd
import numpy as np
from utils.zoo import Indicators

class BaseStrategy:
    """
    策略基底類別 (量化瑞士刀老爸)
    集中管理所有的「全局濾網」、「消融測試濾網」與「訊號生產管線」
    採用「白名單字典法」優雅管理濾網狀態。
    """
    def __init__(self, config: dict):
        self.config = config
        
        # 🌟 1. 定義「合法」的數值型濾網白名單
        self.known_filters = [
            'vix_max', 'vix_min', 'market_ma_window',
            'ma_window', 'min_turnover', 'spy_ma_window',
            'hv_threshold', 'adx_threshold', 'ibs_threshold',
            'gap_threshold', 'rsi_strength_threshold'
        ]
        
        # 🌟 2. 建立 active_filters 字典 (安全過濾版)
        self.active_filters = {}
        for f_name in self.known_filters:
            val = self.config.get(f_name, 0)
            if val > 0:
                self.active_filters[f_name] = val
                
        # 🌟 3. 其它非數值的特殊參數 (布林值或 DataFrame)
        self.avoid_friday = self.config.get('avoid_friday', False)
        self.benchmark_df = self.config.get('benchmark_df', None)

    # =========================================
    # 核心管線 1：留給小孩發揮的空白畫布
    # =========================================
    def generate_raw_signals(self, df):
        """ 子類別必須覆寫這個方法，只負責產生純粹的 signal = 1 或 -1 """
        out = df.copy()
        out['signal'] = 0
        return out

    # =========================================
    # 核心管線 2：老爸的專屬濾網審查室
    # =========================================
    def apply_global_filters(self, df):
        """ 執行所有被啟動的濾網檢查，回傳 True/False 的 Series """
        pass_filters = pd.Series(True, index=df.index)
        
        # ----------------------------------------
        # [A] 大盤與時間濾網
        # ----------------------------------------
        if 'vix_max' in self.active_filters and 'vix' in df.columns:
            pass_filters &= (df['vix'] <= self.active_filters['vix_max'])
            
        if 'vix_min' in self.active_filters and 'vix' in df.columns:
            pass_filters &= (df['vix'] >= self.active_filters['vix_min'])
            
        if 'market_ma_window' in self.active_filters and 'benchmark_close' in df.columns:
            ma_win = self.active_filters['market_ma_window']
            market_ma = df['benchmark_close'].rolling(window=ma_win).mean()
            pass_filters &= (df['benchmark_close'] > market_ma)
            
        if self.avoid_friday:
            if pd.api.types.is_datetime64_any_dtype(df.index):
                pass_filters &= (df.index.dayofweek != 4)
            elif 'date' in df.columns and pd.api.types.is_datetime64_any_dtype(df['date']):
                pass_filters &= (df['date'].dt.dayofweek != 4)

        # ----------------------------------------
        # [B] 8 大消融測試濾網
        # ----------------------------------------
        if 'ma_window' in self.active_filters:
            ma_win = self.active_filters['ma_window']
            col_name = f'ma_{ma_win}' 
            if col_name not in df.columns: 
                df[col_name] = Indicators.sma(df, window=ma_win)
            pass_filters &= (df['close'] > df[col_name])

        if 'spy_ma_window' in self.active_filters and self.benchmark_df is not None:
            spy_win = self.active_filters['spy_ma_window']
            spy_data = self.benchmark_df.copy()
            spy_data['spy_ma'] = spy_data['close'].rolling(window=spy_win).mean()
            spy_data['spy_bullish'] = (spy_data['close'] > spy_data['spy_ma']).astype(int)
            
            # 確保對齊日期 (使用 map 或 merge 以防當機)
            if 'date' in df.columns and 'date' in spy_data.columns:
                mapping = spy_data.set_index('date')['spy_bullish']
                df['spy_bullish'] = df['date'].map(mapping).fillna(0)
            else:
                df['spy_bullish'] = spy_data['spy_bullish'].reindex(df.index).fillna(0)
            pass_filters &= (df['spy_bullish'] == 1)

        if 'min_turnover' in self.active_filters:
            min_turn = self.active_filters['min_turnover']
            if 'turnover_ma' not in df.columns: 
                df['turnover_ma'] = Indicators.avg_turnover(df, 20)
            pass_filters &= (df['turnover_ma'] > min_turn)

        if 'hv_threshold' in self.active_filters:
            hv_th = self.active_filters['hv_threshold']
            if 'hv' not in df.columns: 
                df['hv'] = Indicators.hv(df, window=100)
            pass_filters &= (df['hv'] > hv_th)

        if 'adx_threshold' in self.active_filters:
            adx_th = self.active_filters['adx_threshold']
            if 'adx' not in df.columns: 
                df['adx'] = Indicators.adx(df, window=14)
            pass_filters &= (df['adx'] > adx_th)

        if 'ibs_threshold' in self.active_filters:
            ibs_th = self.active_filters['ibs_threshold']
            if 'ibs' not in df.columns: 
                df['ibs'] = Indicators.ibs(df)
            pass_filters &= (df['ibs'] < ibs_th)

        if 'gap_threshold' in self.active_filters:
            gap_th = self.active_filters['gap_threshold']
            if 'gap_ratio' not in df.columns: 
                df['gap_ratio'] = Indicators.gap_ratio(df)
            pass_filters &= (df['gap_ratio'] > gap_th)
            
        if 'rsi_strength_threshold' in self.active_filters:
            rsi_th = self.active_filters['rsi_strength_threshold']
            if 'rsi_long' not in df.columns: 
                df['rsi_long'] = Indicators.rsi(df, window=100)
            pass_filters &= (df['rsi_long'] > rsi_th)

        return pass_filters

    # =========================================
    # 核心管線 3：生產線總開關 (絕對不讓小孩碰！)
    # =========================================
    def generate_signals(self, df):
        """ 外部 (如 Engine 或 main.py) 統一呼叫這個入口 """
        # 1. 讓小孩去算第一關的草稿
        out = self.generate_raw_signals(df)
        
        # 2. 老爸統一算出濾網通行證
        pass_filters = self.apply_global_filters(out)
        
        # 3. 嚴格把關：沒通過濾網的買單，通通取消！(賣單 -1 不受影響)
        out.loc[~pass_filters & (out['signal'] == 1), 'signal'] = 0
        
        return out