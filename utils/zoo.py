import pandas as pd
import numpy as np
from scipy.stats import linregress

class Indicators:
    """
    指標動物園 (Indicator Zoo) - 擴充版
    職責：計算客觀的技術指標原始數值。
    適用：多標的 DataFrame (需包含 ticker 欄位)。
    """

    # =========================================================
    # 🌊 1. 趨勢類 (Trend) - 判斷方向
    # =========================================================

    @staticmethod
    def sma(df, window=20, price_col='close'):
        """簡單移動平均線 (Simple Moving Average)"""
        return df.groupby('ticker')[price_col].transform(
            lambda x: x.rolling(window).mean()
        )

    @staticmethod
    def ema(df, span=20, price_col='close'):
        """指數移動平均線 (Exponential Moving Average)"""
        # 注意：ewm 在 groupby 下需要用 lambda 包裹
        return df.groupby('ticker')[price_col].transform(
            lambda x: x.ewm(span=span, adjust=False).mean()
        )

    @staticmethod
    def macd(df, fast=12, slow=26, signal=9, price_col='close'):
        """MACD (Diff, Signal, Hist) - 回傳 DataFrame 包含三欄"""
        # 為了效率，我們在內部定義計算邏輯
        def _calc_macd(x):
            ema_fast = x.ewm(span=fast, adjust=False).mean()
            ema_slow = x.ewm(span=slow, adjust=False).mean()
            dif = ema_fast - ema_slow
            dem = dif.ewm(span=signal, adjust=False).mean()
            hist = dif - dem
            return pd.DataFrame({'dif': dif, 'dem': dem, 'hist': hist})

        # apply 會回傳 MultiIndex，需要 reset
        return df.groupby('ticker')[price_col].apply(_calc_macd).reset_index(level=0, drop=True)

    # =========================================================
    # 🚀 2. 動能類 (Momentum) - 判斷超買超賣
    # =========================================================

    @staticmethod
    def rsi(df, window=14, price_col='close'):
        """相對強弱指標 (RSI)"""
        def _calc_rsi(x):
            delta = x.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
            rs = gain / loss.replace(0, np.nan)
            return 100 - (100 / (1 + rs))
        
        return df.groupby('ticker')[price_col].transform(_calc_rsi)

    @staticmethod
    def bias(df, window=20, price_col='close'):
        """乖離率 (Bias)"""
        ma = Indicators.sma(df, window, price_col)
        return (df[price_col] - ma) / ma.replace(0, np.nan)

    @staticmethod
    def kd(df, window=9, smooth_k=3, smooth_d=3):
        """隨機指標 (KD) - 回傳 K, D 兩欄"""
        def _calc_kd(x):
            # x 包含 high, low, close
            low_min = x['low'].rolling(window).min()
            high_max = x['high'].rolling(window).max()
            rsv = (x['close'] - low_min) / (high_max - low_min) * 100
            
            # 使用 EWM 來模擬 SMA 平滑 (常見的 KD 算法是 1/3 權重，近似 com=2 的 ewm)
            k = rsv.ewm(com=smooth_k-1, adjust=False).mean()
            d = k.ewm(com=smooth_d-1, adjust=False).mean()
            return pd.DataFrame({'k': k, 'd': d})

        return df.groupby('ticker').apply(_calc_kd).reset_index(level=0, drop=True)

    @staticmethod
    def williams_r(df, window=14):
        """威廉指標 (Williams %R)"""
        def _calc_wr(x):
            high_max = x['high'].rolling(window).max()
            low_min = x['low'].rolling(window).min()
            return (high_max - x['close']) / (high_max - low_min) * -100
            
        return df.groupby('ticker').apply(_calc_wr).reset_index(level=0, drop=True)
    
    @staticmethod
    def clenow_momentum(df, window=90, price_col='close'):
        """
        [進階] Clenow 動能因子 (回歸斜率 * R平方)
        公式：Slope(log(price)) * R^2
        意義：尋找「漲勢最平滑且陡峭」的股票。
        注意：運算較慢，因為要跑迴歸。
        """
        def _calc_slope_r2(series):
            # 為了避開 log(0) 或負數，這裡假設價格都是正數
            y = np.log(series.values)
            x = np.arange(len(y))
            #計算回歸
            slope, intercept, r_value, p_value, std_err = linregress(x, y)
            # 動能分數 = 斜率 (漲速) * R平方 (穩定度)
            # 我們將年化一下斜率讓數值好看一點 (x 252)
            return (slope * 252) * (r_value ** 2)

        # 使用 rolling apply 應用到每個窗口
        return df.groupby('ticker')[price_col].transform(
            lambda x: x.rolling(window=window).apply(_calc_slope_r2, raw=False)
        )

    # =========================================================
    # 🎢 3. 波動類 (Volatility) - 判斷風險與壓縮
    # =========================================================

    @staticmethod
    def atr(df, window=14):
        """
        ATR 計算 (索引安全版)
        邏輯：先算出 TR，再利用 groupby rolling 計算平均，最後利用索引自動對齊。
        """
        # 1. 為了確保 shift 正確，我們必須確保 Close 是跟該股票的前一天比
        # 直接用 groupby shift，不管資料怎麼排序都不會錯
        prev_close = df.groupby('ticker')['close'].shift(1)
        
        # 2. 計算 TR (True Range)
        high = df['high']
        low = df['low']
        
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        
        # 取最大值作為 TR
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # 3. 計算 ATR (Rolling Mean)
        # 這裡是最關鍵的一步：groupby 之後做 rolling，index 會變成 (ticker, original_index)
        atr_multi_index = tr.groupby(df['ticker']).rolling(window).mean()
        
        # 4. 還原索引 (Index Alignment)
        # 我們要把 MultiIndex 的 'ticker' 層級拿掉，只保留 'original_index'
        # 這樣 assign 回去 df 時，Pandas 會自動依照 index 對齊，絕對不會錯！
        atr = atr_multi_index.reset_index(level=0, drop=True)
        
        return atr

    @staticmethod
    def bollinger_bands(df, window=20, std_dev=2, price_col='close'):
        """布林通道 (Upper, Mid, Lower, Width)"""
        def _calc_bb(x):
            mid = x.rolling(window).mean()
            std = x.rolling(window).std()
            upper = mid + (std * std_dev)
            lower = mid - (std * std_dev)
            width = (upper - lower) / mid # 通道寬度 (用於篩選盤整或突破)
            return pd.DataFrame({'bb_up': upper, 'bb_mid': mid, 'bb_low': lower, 'bb_width': width})

        return df.groupby('ticker')[price_col].apply(_calc_bb).reset_index(level=0, drop=True)

    @staticmethod
    def rolling_std(df, window=20, price_col='close'):
        """滾動標準差 (波動率)"""
        return df.groupby('ticker')[price_col].transform(
            lambda x: x.rolling(window).std()
        )

    # =========================================================
    # 💰 4. 量能與其他 (Volume & Others) - 籌碼與統計
    # =========================================================

    @staticmethod
    def obv(df):
        """能量潮 (On-Balance Volume)"""
        def _calc_obv(x):
            # 價格變化方向：漲為1, 跌為-1, 平為0
            direction = np.sign(x['close'].diff()).fillna(0)
            # 累積成交量
            return (direction * x['volume']).cumsum()
        
        return df.groupby('ticker').apply(_calc_obv).reset_index(level=0, drop=True)

    @staticmethod
    def donchian(df, window=20):
        """唐奇安通道 (用於海龜交易法，突破前高)"""
        def _calc_donchian(x):
            # 這裡回傳的是「過去 N 天」的極值 (不含今天，用於突破判斷)
            upper = x['high'].shift(1).rolling(window).max()
            lower = x['low'].shift(1).rolling(window).min()
            return pd.DataFrame({'donchian_up': upper, 'donchian_low': lower})
            
        return df.groupby('ticker').apply(_calc_donchian).reset_index(level=0, drop=True)

    @staticmethod
    def log_return(df, price_col='close'):
        """對數報酬率 (適合做統計分析)"""
        return df.groupby('ticker')[price_col].transform(
            lambda x: np.log(x / x.shift(1))
        )
    
    # =========================================================
    # 🌊 新增：震盪與位置指標 (Oscillators & Position)
    # =========================================================

    @staticmethod
    def rolling_rank(df, window=21, col='close', pct=True):
        """
        滾動排名 (Rolling Rank) - 用於你的第二個公式
        計算當前數值在過去 N 天中的排名 (預設為百分比 0~1)。
        
        應用：
        1. 價格排名: rolling_rank(df, 21, 'close') -> 1.0 代表創21日新高
        2. 量的排名: rolling_rank(df, 21, 'volume') -> 爆量程度
        """
        return df.groupby('ticker')[col].transform(
            lambda x: x.rolling(window).rank(pct=pct)
        )

    @staticmethod
    def price_position(df, window=21, col='close'):
        """
        價格相對位置 (Stochastic Position) - 另一種衡量位置的常見寫法
        公式: (C - Min_21) / (Max_21 - Min_21)
        這跟 Rank 很像，但它是計算「距離」，Rank 是計算「名次」。
        """
        def _calc_pos(x):
            low_min = x.rolling(window).min()
            high_max = x.rolling(window).max()
            # 避免分母為 0
            denom = high_max - low_min
            return (x - low_min) / denom.replace(0, np.nan)

        return df.groupby('ticker')[col].transform(_calc_pos)
    
    # =========================================================
    # ⚡ 5. 複合指標 (Composite) - CRSI
    # =========================================================

    @staticmethod
    def crsi(df, window_rsi=3, window_streak=2, window_rank=100):
        """
        Connors RSI (CRSI) 計算 - 索引安全版
        公式: (RSI(Price, 3) + RSI(Streak, 2) + PercentRank(100)) / 3
        """
        # 0. 準備工作：確保按 Ticker 分組運算，避免混到不同股票
        # 使用 groupby 確保 Close 是跟自己的昨天比
        # 這裡利用 transform 可以保留原始索引，非常安全
        close = df['close']
        prev_close = df.groupby('ticker')['close'].shift(1)
        
        # ----------------------------------------------------
        # 1. 計算 Price RSI (3)
        # ----------------------------------------------------
        def _calc_rsi_series(series, period):
            delta = series.diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)
            
            avg_gain = gain.rolling(window=period).mean()
            avg_loss = loss.rolling(window=period).mean()
            
            rs = avg_gain / avg_loss
            return 100 - (100 / (1 + rs))

        # 利用 groupby apply 計算，然後還原索引
        rsi_3_series = df.groupby('ticker')['close'].apply(lambda x: _calc_rsi_series(x, window_rsi))
        rsi_3 = rsi_3_series.reset_index(level=0, drop=True)

        # ----------------------------------------------------
        # 2. 計算 Streak (連漲連跌天數)
        # ----------------------------------------------------
        # 這部分最難，我們用邏輯運算解
        diff = close - prev_close
        
        # 建立一個臨時 DataFrame 來算 Streak
        # 1: 漲, -1: 跌, 0: 平
        # 為了計算方便，我們先把 diff 轉成 sign
        # 注意：這裡假設 df 已經依照 ticker, date 排序 (Step 1 的 SQL 有做 ORDER BY)
        # 如果沒排序，這裡會算錯。但通常 Engine 進來的都有排序。
        
        # 定義一個內部函式專門算 Streak (比較慢但穩)
        def _calc_streak_series(group_close):
            diff = group_close.diff().fillna(0)
            signs = np.sign(diff)
            
            # 魔法：利用 cumsum 找出連續區塊的 ID
            # 當符號改變時 (例如 1 變 -1)，block_id 就會 +1
            blocks = (signs != signs.shift()).cumsum()
            
            # 利用 cumcount 計算每個區塊累積了幾天
            streak_counts = signs.groupby(blocks).cumcount() + 1
            
            # 把符號乘回去 (漲3天=+3, 跌2天=-2)
            return streak_counts * signs

        streak_series = df.groupby('ticker')['close'].apply(_calc_streak_series)
        streak_series = streak_series.reset_index(level=0, drop=True)

        # 計算 Streak 的 RSI (2)
        rsi_streak_series = df.groupby('ticker').apply(lambda x: _calc_rsi_series(streak_series.loc[x.index], window_streak))
        rsi_streak = rsi_streak_series.reset_index(level=0, drop=True)

        # ----------------------------------------------------
        # 3. 計算 Percent Rank (100)
        # ----------------------------------------------------
        # 計算單日報酬率
        ret = (close / prev_close) - 1
        
        # Rolling Rank (0~1 之間，所以乘 100)
        # pct=True 代表回傳百分比排名
        pct_rank_series = ret.groupby(df['ticker']).rolling(window_rank).rank(pct=True)
        pct_rank = pct_rank_series.reset_index(level=0, drop=True) * 100

        # ----------------------------------------------------
        # 4. 最終合成
        # ----------------------------------------------------
        # 確保三者索引對齊 (利用 fillna 0 避免初期運算導致全體 NaN，或保留 NaN)
        # CRSI 定義：三者平均
        final_crsi = (rsi_3 + rsi_streak + pct_rank) / 3
        
        return final_crsi
    
    # =========================================================
    # 🛡️ 6. 市場濾網 (Market Regime Filters)
    # =========================================================

    @staticmethod
    def hv(df, window=21, price_col='close'):
        """
        歷史波動率 (Historical Volatility)
        計算：對數報酬率的標準差 * 年化係數 (根號252)
        用途：分辨市場是「冷靜」還是「躁動」。
        """
        def _calc_hv(x):
            log_ret = np.log(x / x.shift(1))
            return log_ret.rolling(window).std() * np.sqrt(252)
        
        return df.groupby('ticker')[price_col].transform(_calc_hv)
    
    @staticmethod
    def hv_ratio(df, short_window=20, long_window=100):
        """
        縱向波動率比較
        數值 > 1 代表現在比過去波動大 (恐慌)
        數值 < 1 代表現在比過去平靜 (盤整)
        """
        # 1. 計算短天期波動 (例如近 20 天)
        short_hv = Indicators.hv(df, window=short_window)
        
        # 2. 計算長天期波動 (例如過去 100 天的平均)
        # 注意：這裡不是直接算 100 天 HV，而是算 "HV 的移動平均"
        # 或者是直接算 100 天的 HV 也可以，視定義而定
        # 這裡我們用比較直觀的：目前的 HV / 過去 100 天 HV 的平均值
        
        # 先算每天的 HV
        daily_hv = Indicators.hv(df, window=20) 
        
        # 再算 HV 的 MA (長期基準線)
        avg_hv = daily_hv.rolling(window=long_window).mean()
        
        # 3. 計算比率
        return daily_hv / avg_hv

    @staticmethod
    def adx(df, window=14):
        """
        平均趨向指標 (ADX)
        用途：判斷「趨勢強度」(不管方向)。
        數值：> 25 代表有趨勢，< 20 代表盤整。
        """
        def _calc_adx(x):
            # 1. 計算 True Range (TR)
            # TR = max(H-L, |H-Cp|, |L-Cp|)
            close_shift = x['close'].shift(1)
            tr1 = x['high'] - x['low']
            tr2 = (x['high'] - close_shift).abs()
            tr3 = (x['low'] - close_shift).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

            # 2. 計算 Directional Movement (+DM, -DM)
            up = x['high'] - x['high'].shift(1)
            down = x['low'].shift(1) - x['low']
            
            # +DM: 創新高且幅度大於創新低
            pos_dm = np.where((up > down) & (up > 0), up, 0)
            # -DM: 創新低且幅度大於創新高
            neg_dm = np.where((down > up) & (down > 0), down, 0)
            
            # 3. 平滑處理 (Wilder's Smoothing 近似於 alpha=1/window 的 EMA)
            tr_smooth = tr.ewm(alpha=1/window, adjust=False).mean()
            pos_dm_smooth = pd.Series(pos_dm, index=x.index).ewm(alpha=1/window, adjust=False).mean()
            neg_dm_smooth = pd.Series(neg_dm, index=x.index).ewm(alpha=1/window, adjust=False).mean()

            # 4. 計算 DI (+DI, -DI)
            pos_di = 100 * (pos_dm_smooth / tr_smooth.replace(0, np.nan))
            neg_di = 100 * (neg_dm_smooth / tr_smooth.replace(0, np.nan))

            # 5. 計算 DX
            dx = 100 * (abs(pos_di - neg_di) / (pos_di + neg_di).replace(0, np.nan))

            # 6. 計算 ADX (DX 的平滑)
            return dx.ewm(alpha=1/window, adjust=False).mean()

        # 這裡需要傳入完整 df (含 high, low, close)
        return df.groupby('ticker').apply(_calc_adx).reset_index(level=0, drop=True)

    @staticmethod
    def ma_filter(df, window=200, price_col='close'):
        """
        長線趨勢濾網 (MA Filter)
        回傳：1 (價格在均線上), 0 (價格在均線下)
        最簡單但也最有效的濾網之一。
        """
        ma = df.groupby('ticker')[price_col].transform(
            lambda x: x.rolling(window).mean()
        )
        return (df[price_col] > ma).astype(int)
    
    @staticmethod
    def avg_turnover(df, window=20):
        """
        計算平均成交金額 (Average Dollar Volume)
        公式: RollingMean(Close * Volume, window)
        """
        # 1. 計算單日成交額 (收盤價 * 成交量)
        # 注意：美股資料通常 Volume 是股數，Close 是美元，相乘就是美元金額
        daily_turnover = df['raw_close'] * df['volume']
        
        # 2. 計算移動平均 (平滑化，避免單日爆量雜訊)
        avg_turnover = daily_turnover.rolling(window=window).mean()
        
        return avg_turnover
    
    @staticmethod
    def ibs(df):
        """
        Internal Bar Strength: (Close - Low) / (High - Low)
        回傳 0~1 的數值
        """
        # 防呆：避免 High == Low 造成除以零
        range_ = df['high'] - df['low']
        ibs_series = (df['close'] - df['low']) / range_
        return ibs_series.fillna(0.5) # 如果沒波動，給中性值
    
    @staticmethod
    def long_term_strength(df, window=100):
        """
        方案 A: 使用長天期 RSI 作為強勢股濾網
        """
        # 利用現有的 rsi 函數，只是參數變長
        return Indicators.rsi(df, window=window)

    @staticmethod
    def relative_strength_rank(df, window=126):
        """
        方案 B: 計算個股在全市場中的強弱排名 (0~100分)
        注意：這需要傳入包含多支股票的 df，並依照日期分組計算
        """
        # 1. 先算個股過去 N 天的報酬率 (ROC)
        # 這裡假設 df 已經是以 ticker 分組過的，或者外部呼叫時要注意
        # 如果是在 generate_signals 裡呼叫，通常 df 是整包資料
        
        # 安全起見，我們先算 ROC
        roc = df['close'].pct_change(window)
        
        # 2. 為了進行橫截面排名，我們需要把 roc 依照日期分組
        # Transform 會保持原本的索引長度，將排名結果填回每一行
        rank_series = roc.groupby(df['date']).rank(pct=True) * 100
        
        return rank_series.fillna(50) # 剛上市沒資料的給 50 分
    
    @staticmethod
    def gap_ratio(df):
        """
        計算跳空比率 = 今日 Open / 昨日 Close
        回傳值 < 1 代表向下跳空 (例如 0.95 代表低開 5%)
        回傳值 > 1 代表向上跳空
        """
        # 1. 取得昨日收盤價 (必須依照 ticker 分組 shift)
        # 假設您的 df 有 'ticker' 和 'close' 欄位
        prev_close = df.groupby('ticker')['close'].shift(1)
        
        # 2. 計算比率
        gap = df['open'] / prev_close
        
        # 3. 補值 (第一天沒昨收，設為 1.0 代表沒跳空)
        return gap.fillna(1.0)
    
    
    
    # =========================================================
    # 🧩 7. 補完計畫 (Missing Pieces)
    # =========================================================

    @staticmethod
    def roc(df, window=12, price_col='close'):
        """
        變動率 (Rate of Change)
        公式：(今日價格 - N天前價格) / N天前價格
        意義：最純粹的「速度」指標。
        由來：動能策略的始祖，用來測量價格衝刺的力道。
        """
        return df.groupby('ticker')[price_col].transform(
            lambda x: x.pct_change(periods=window) * 100
        )

    @staticmethod
    def cci(df, window=20):
        """
        順勢指標 (Commodity Channel Index)
        公式：(典型價格 - MA) / (0.015 * 平均絕對偏差)
        意義：測量價格偏離統計平均的程度。
        特點：不像 RSI 限制在 0-100，CCI 可以無限大或無限小，適合抓極端行情的「慣性」。
        """
        def _calc_cci(x):
            tp = (x['high'] + x['low'] + x['close']) / 3
            ma = tp.rolling(window).mean()
            # mad (Mean Absolute Deviation) 也就是平均絕對偏差
            mad = (tp - ma).abs().rolling(window).mean()
            return (tp - ma) / (0.015 * mad.replace(0, np.nan))

        return df.groupby('ticker').apply(_calc_cci).reset_index(level=0, drop=True)

    @staticmethod
    def mfi(df, window=14):
        """
        資金流量指標 (Money Flow Index)
        意義：這就是「有成交量加權的 RSI」。
        用途：RSI 只看價，MFI 同時看價量。當價格創新高但 MFI 沒創新高（背離），是極佳的反轉訊號。
        """
        def _calc_mfi(x):
            tp = (x['high'] + x['low'] + x['close']) / 3
            raw_money_flow = tp * x['volume']
            
            # 判斷資金流向 (正流向 vs 負流向)
            diff = tp.diff()
            pos_flow = raw_money_flow.where(diff > 0, 0).rolling(window).sum()
            neg_flow = raw_money_flow.where(diff < 0, 0).rolling(window).sum()
            
            money_ratio = pos_flow / neg_flow.replace(0, np.nan)
            return 100 - (100 / (1 + money_ratio))

        return df.groupby('ticker').apply(_calc_mfi).reset_index(level=0, drop=True)

    @staticmethod
    def keltner_channels(df, window=20, atr_mult=2):
        """
        肯特納通道 (Keltner Channels)
        組成：中軌是 EMA，上下軌是中軌加減 ATR。
        用途：搭配布林通道使用。
        策略：當「布林通道」縮到「肯特納通道」裡面時 (Squeeze)，代表暴風雨前的寧靜，即將大爆發。
        """
        def _calc_kc(x):
            # 1. 算出 ATR (這裡簡化重算一次，或可傳入已算好的)
            high, low, close = x['high'], x['low'], x['close']
            tr1 = high - low
            tr2 = (high - close.shift()).abs()
            tr3 = (low - close.shift()).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(window).mean()
            
            # 2. 中軌通常用 EMA
            mid = x['close'].ewm(span=window, adjust=False).mean()
            upper = mid + (atr * atr_mult)
            lower = mid - (atr * atr_mult)
            
            return pd.DataFrame({'kc_mid': mid, 'kc_up': upper, 'kc_low': lower})

        return df.groupby('ticker').apply(_calc_kc).reset_index(level=0, drop=True)
    
    # =========================================================
    # 📊 8. 統計與標準化 (Statistics & Standardization)
    # =========================================================

    @staticmethod
    def z_score(df, window=250, col='close'):
        """
        滾動 Z-Score (Rolling Z-Score)
        公式：(數值 - 平均值) / 標準差
        
        意義：將數據轉換為「常態分佈」的標準分數。
        數值解讀：
        * 0   : 代表數值等於平均 (正常)
        * +2  : 代表數值高於平均 2 個標準差 (極端高，機率約 2.5%)
        * -2  : 代表數值低於平均 2 個標準差 (極端低，機率約 2.5%)
        * >3  : 黑天鵝等級的極端值
        
        用途：
        1. 讓不同價位的股票可以比較 (台積電 vs 雞蛋水餃股)。
        2. 讓不同性質的指標可以比較 (乖離率 vs 成交量)。
        """
        return df.groupby('ticker')[col].transform(
            lambda x: (x - x.rolling(window).mean()) / x.rolling(window).std(ddof=1)
        )

    @staticmethod
    def percentile_rank(df, window=250, col='close'):
        """
        滾動百分位排名 (Rolling Percentile Rank)
        公式：當前數值在過去 N 天中排第幾名 (0.0 ~ 1.0)
        
        用途：
        如果你不喜歡 Z-Score (理論無上限)，可以用 PR 值。
        PR = 1.0 代表創 N 日新高。
        PR = 0.0 代表創 N 日新低。
        """
        return df.groupby('ticker')[col].transform(
            lambda x: x.rolling(window).rank(pct=True)
        )