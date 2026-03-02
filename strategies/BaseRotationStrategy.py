import pandas as pd
import numpy as np
from .base import BaseStrategy

class BaseRotationStrategy(BaseStrategy):
    def __init__(self, config: dict):
        # 先呼叫老爸的 __init__，繼承大盤濾網設定
        super().__init__(config)
        
        # 讀取輪動專屬的參數
        self.buy_top_n = config.get('buy_top_n', 5)
        self.hold_top_n = config.get('hold_top_n', 10)
        self.min_price = config.get('min_price', 5.0)       # 股價濾網
        self.min_volume = config.get('min_volume', 100000)  # 成交量濾網

    def apply_universe_filters(self, df):
        """
        [濾網 1] 選股池過濾：剔除雞蛋水餃股與缺乏流動性的股票
        (在計算排名之前呼叫)
        """
        is_valid_price = df['close'] >= self.min_price
        is_valid_vol = df['volume'] >= self.min_volume
        
        # 把不合格的股票 rank 強制設為 NaN，讓它無法參與排名
        df.loc[~(is_valid_price & is_valid_vol), 'rank'] = np.nan
        return df

    def apply_rank_buffer(self, df):
        """
        [濾網 2] 排名緩衝與權重分配：降低換手率的靈魂機制
        """
        # 為了方便比對「昨日狀態」，我們把資料轉成寬表 (Pivot)
        rank_wide = df.pivot(index='date', columns='ticker', values='rank')
        
        # 建立布林遮罩 (是否符合標準)
        is_top_buy = rank_wide <= self.buy_top_n
        is_top_hold = rank_wide <= self.hold_top_n
        
        # 建立權重表，先全部填 0
        weights = pd.DataFrame(0.0, index=rank_wide.index, columns=rank_wide.columns)
        
        # 逐日計算 (因為依賴昨天持股，迴圈是最穩的做法)
        for i in range(len(rank_wide.index)):
            today = rank_wide.index[i]
            if i == 0:
                # 第一天沒有昨天可以參考，只能用嚴格買進標準
                weights.loc[today, is_top_buy.loc[today]] = 1.0 / self.buy_top_n
                continue
                
            yesterday = rank_wide.index[i-1]
            
            # 條件 A：今天強勢擠進前 N 名 -> 買進
            cond_buy = is_top_buy.loc[today]
            # 條件 B：今天還在前 M 名，且「昨天已經持有 (權重>0)」 -> 續抱
            cond_hold = is_top_hold.loc[today] & (weights.loc[yesterday] > 0)
            
            # 只要符合 A 或 B 就給權重
            final_selected = cond_buy | cond_hold
            selected_tickers = final_selected[final_selected].index
            
            # 等權重分配 (例如選出 6 檔，每檔就拿 1/6 的資金)
            if len(selected_tickers) > 0:
                weights.loc[today, selected_tickers] = 1.0 / len(selected_tickers)
                
        # 將寬表轉回長表，準備合併回原本的 df
        weights_long = weights.unstack().reset_index()
        weights_long.columns = ['ticker', 'date', 'target_weight']
        
        # 把算好的 target_weight 貼回給 df
        df = df.merge(weights_long, on=['date', 'ticker'], how='left')
        df['target_weight'] = df['target_weight'].fillna(0)
        
        return df