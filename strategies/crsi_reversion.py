from .base import BaseStrategy
from utils.zoo import Indicators
import numpy as np

class CRSIStrategy(BaseStrategy):
    def __init__(self, config: dict):
        super().__init__(config) 
        
        # 🌟 只保留你原本設計的進出場門檻與限價參數
        self.entry_threshold = self.config.get('crsi_entry', 10)
        self.exit_threshold = self.config.get('crsi_exit', 70)
        self.limit_pct = self.config.get('limit_pct', 0.0)

    def generate_raw_signals(self, df):
        out = df.copy()
        out['signal'] = 0
        
        # 🌟 完美還原：套用你原本寫好的 3, 2, 100 經典參數
        out['crsi'] = Indicators.crsi(out, 3, 2, 100)
        
        # 最純粹的核心邏輯：低於門檻買，高於門檻賣
        out.loc[out['crsi'] < self.entry_threshold, 'signal'] = 1
        out.loc[out['crsi'] > self.exit_threshold, 'signal'] = -1
        
        # 限價單計算
        if self.limit_pct is None or self.limit_pct == 0:
            out['limit_price'] = np.nan 
        else:
            out['limit_price'] = out['close'] * (1 - self.limit_pct)
            
        return out