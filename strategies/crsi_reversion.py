from .base import BaseStrategy
from utils.zoo import Indicators

class CRSIStrategy(BaseStrategy):
    def __init__(self, config: dict):
        super().__init__(config)
        self.entry_threshold = self.config.get('crsi_entry', 10)
        self.exit_threshold = self.config.get('crsi_exit', 70)
        self.crsi_period = self.config.get('crsi_period', 3)

    # 注意這裡！我們只覆寫 generate_raw_signals (第一關)
    def generate_raw_signals(self, df):
        df['signal'] = 0
        df['crsi'] = Indicators.crsi(df, period=self.crsi_period)
        
        # 最純粹的核心邏輯：低於門檻買，高於門檻賣
        buy_signal = df['crsi'] < self.entry_threshold
        sell_signal = df['crsi'] > self.exit_threshold
        
        df.loc[buy_signal, 'signal'] = 1
        df.loc[sell_signal, 'signal'] = -1
        
        return df