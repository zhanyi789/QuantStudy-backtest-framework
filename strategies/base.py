from utils.zoo import Indicators

class BaseStrategy:
    def __init__(self, config: dict):
        self.config = config
        self.active_filters = {} 
        for filter_name, filter_value in self.config.items():
            if filter_value > 0:
                self.active_filters[filter_name] = filter_value

    def generate_raw_signals(self, df):
        # 這是留給小孩寫的空白考卷
        df['signal'] = 0
        return df

    def apply_global_filters(self, df):
        # 老爸的專屬濾網審查室：預設大家都有通行證 (True)
        global_condition = True 

        # 這裡統一管理所有可能的濾網！
        if 'ma_window' in self.active_filters:
            ma_win = self.active_filters['ma_window']
            df['ma'] = Indicators.sma(df, period=ma_win)
            global_condition &= (df['close'] > df['ma'])

        if 'adx_threshold' in self.active_filters:
            adx_th = self.active_filters['adx_threshold']
            df['adx'] = Indicators.adx(df)
            global_condition &= (df['adx'] > adx_th)

        # 未來你想加 VIX 濾網、波動率濾網，全部都在這裡加！
        return global_condition

    def generate_signals(self, df):
        # 生產線啟動！
        # 1. 讓小孩去算原始訊號 (也就是第一關的草稿)
        df = self.generate_raw_signals(df)
        
        # 2. 老爸統一算出濾網通行證
        pass_filters = self.apply_global_filters(df)
        
        # 3. 嚴格把關：本來想買 (signal == 1) 但沒通過濾網的，通通取消 (改成 0)
        # 注意：通常濾網只擋進場，賣出訊號 (signal == -1) 不受濾網限制
        df.loc[(df['signal'] == 1) & (~pass_filters), 'signal'] = 0
        
        return df