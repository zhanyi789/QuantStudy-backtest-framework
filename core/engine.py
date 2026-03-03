import duckdb
import pandas as pd
import numpy as np
from collections import defaultdict

# ==========================================
# 核心引擎 
# ==========================================

class AdvancedEventEngine:
    # 我們把 config 字典傳進來
    def __init__(self, config: dict, data_feed=None): 
        self.config = config
        if data_feed is not None:
            self.df_data = data_feed
        else:
            self.df_data = None
            
        # 從你專屬的 config 食譜中讀取系統設定
        self.initial_cash = config.get('initial_capital', 100000)
        self.cash = self.initial_cash
        self.portfolio_value = self.initial_cash
        
        self.impact_cost = config.get('slippage_percent', 0.002)
        self.comm_rate = config.get('commission_rate', 0.001)
        
        self.positions = {}
        self.pending_entries = []
        self.daily_log = []
        self.trade_log = []
        
        # 準備一個空列表來接每期的橫截面排名快照
        self.rank_log = [] 
        
        self.exit_policies = []
        self.sizer = None
        self.primary_risk_stop = None
        
    def set_components(self, exits, sizer, risk_stop_module):
        self.exit_policies = exits
        self.sizer = sizer
        self.primary_risk_stop = risk_stop_module

    def load_data(self, ohlcv_path, universe_path, start_date='2010-01-01'):
        print(f"🚀 [Engine] Loading RAW & ADJUSTED data from {start_date}...")
        
        self.con = duckdb.connect(':memory:')
        query = f"""
        SELECT 
            t1.date, 
            t1.ticker, 
            
            t1.open  AS raw_open,
            t1.high  AS raw_high,
            t1.low   AS raw_low,
            t1.raw_close AS raw_close,
            t1.volume,
            
            (t1.open  * t1.adj_factor) AS open,
            (t1.high  * t1.adj_factor) AS high,
            (t1.low   * t1.adj_factor) AS low,
            t1.adj_close              AS close
            
        FROM read_parquet('{ohlcv_path}') AS t1
        INNER JOIN read_parquet('{universe_path}') AS t2
          ON t1.date = t2.date 
          AND t1.ticker = t2.ticker
          
        WHERE t1.date >= '{start_date}'
        ORDER BY t1.date, t1.ticker
        """
        
        try:
            self.df_data = self.con.execute(query).df()
            print(f"✅ Data Loaded. Rows: {len(self.df_data)}")
            print(f"   Columns: {list(self.df_data.columns)}")
        except Exception as e:
            print("❌ 資料載入失敗，請檢查欄位名稱")
            raise e
            
        return self
    
    def load_data_tw(self, parquet_path, start_date='2010-01-01'):
        print(f"🚀 [Engine] Loading TAIWAN Market Data from {start_date}...")
        self.con = duckdb.connect(':memory:')
        
        query = f"""
        SELECT 
            Date AS date, 
            Ticker AS ticker, 
            
            "開盤價(元)" AS raw_open,
            "最高價(元)" AS raw_high,
            "最低價(元)" AS raw_low,
            "收盤價(元)" AS raw_close,
            "成交量(千股)" AS volume,
            
            "還原開盤價" AS open,
            "還原最高價" AS high,
            "還原最低價" AS low,
            "還原收盤價" AS close,
            
            "漲跌停" AS limit_status,
            "成交值(千元)" AS turnover_value,
            "最終_單月營收YoY" AS rev_yoy,    
            "ROE(A)－稅後" AS roe             
            
        FROM read_parquet('{parquet_path}')
        WHERE Date >= '{start_date}'
        ORDER BY Date, Ticker
        """
        
        try:
            self.df_data = self.con.execute(query).df()
            print(f"✅ Taiwan Data Loaded. Rows: {len(self.df_data)}")
            print("讀取的欄位有：", list(self.df_data.columns))
        except Exception as e:
            print("❌ 台股資料載入失敗，請檢查欄位名稱")
            raise e
            
        return self

    # 🌟 [升級] 加入 shares_to_sell 參數，支援部分平倉
    def _execute_sell(self, date, ticker, raw_price, reason, shares_to_sell=None):
        if ticker not in self.positions: 
            return
            
        pos = self.positions[ticker]
        current_shares = pos['shares']
        
        # 判斷是「全部平倉」還是「部分平倉」
        if shares_to_sell is None or shares_to_sell >= current_shares:
            shares_to_sell = current_shares
            is_partial = False
            # 全部賣出，把該檔股票從帳戶字典中剔除
            self.positions.pop(ticker)
        else:
            is_partial = True
            # 部分賣出，扣除指定股數
            pos['shares'] -= shares_to_sell
            
        # 計算實際成交價與手續費
        exec_price = raw_price * (1 - self.impact_cost)
        proceeds = shares_to_sell * exec_price
        comm = proceeds * self.comm_rate
        net_proceeds = proceeds - comm
        
        # 錢回到帳戶
        self.cash += net_proceeds
        
        # 🌟 核心會計邏輯：按比例計算被賣掉的那部分成本 (平均成本法)
        avg_cost_per_share = pos['cost'] / current_shares
        cost_of_sold = avg_cost_per_share * shares_to_sell
        
        # 如果是部分平倉，要把剩餘的部位成本扣掉
        if is_partial:
            pos['cost'] -= cost_of_sold
            
        # 計算這筆交易的獲利
        profit = net_proceeds - cost_of_sold
        profit_pct = (net_proceeds / cost_of_sold) - 1 if cost_of_sold > 0 else 0
        
        # 紀錄交易日誌 (標註是否為部分平倉)
        log_reason = reason + (" (Partial)" if is_partial else "")
        
        self.trade_log.append({
            'ticker': ticker,
            'entry_date': pos['entry_date'],
            'exit_date': date,
            'entry_price': pos['entry_price'], 
            'exit_price': exec_price,          
            'shares': shares_to_sell,  # 紀錄賣出的股數
            'profit': profit,
            'profit_pct': profit_pct,
            'reason': log_reason,
            'bars_held': pos['bars_held'],
            'entry_value': cost_of_sold,
            'highest_price': pos['highest_price'], # 🌟 新增：匯出給績效模組算 MFE
            'lowest_price': pos['lowest_price'],   # 🌟 新增：匯出給績效模組算 MAE
            'net_proceeds': net_proceeds
        })

    def run(self, strategy_instance, max_positions=None):
        print(f"🕹️ Engine Started. (Slippage: {self.impact_cost:.2%})")
        
        df_full = strategy_instance.generate_signals(self.df_data)
        
        print("⚡ Indexing data...")
        standard_cols = {'date', 'ticker', 'open', 'high', 'low', 'close', 'volume', 
                         'raw_open', 'raw_high', 'raw_low', 'raw_close', 
                         'signal', 'rank', 'limit_price'}
        
        indicator_cols = [c for c in df_full.columns if c not in standard_cols]
        
        pivots = {}
        target_cols = list(standard_cols.intersection(df_full.columns)) + indicator_cols
        for col in target_cols:
            pivots[col] = df_full.pivot(index='date', columns='ticker', values=col)
            
        all_dates = sorted(pivots['close'].index)
        print(f"💰 Loop Start ({len(all_dates)} days)...")
        
        for today in all_dates:
            todays_data = {col: pivots[col].loc[today] for col in pivots if today in pivots[col].index}
            if 'close' not in todays_data: continue

            has_limit_status = 'limit_status' in todays_data
            
            # --- [Step 1-A] 執行賣單 ---
            for ticker in list(self.positions.keys()):
                pos = self.positions[ticker]
                if pos.get('exit_pending', False):
                    # 跌停板賣不掉的防呆
                    if has_limit_status and todays_data['limit_status'].get(ticker) == '-':
                        continue 
                        
                    raw_open = todays_data['raw_open'].get(ticker)
                    if not pd.isna(raw_open):
                        # 🌟 新增：讀取要賣出的股數 (停損預設為 None 全部賣出，再平衡會有指定股數)
                        shares_to_sell = pos.get('exit_shares', None)
                        self._execute_sell(today, ticker, raw_open, pos['exit_reason'], shares_to_sell=shares_to_sell)
                        
                        # 🌟 新增：如果是「部分平倉(減碼)」，股票還在帳戶裡，要把它的賣出狀態重置
                        if ticker in self.positions:
                            self.positions[ticker]['exit_pending'] = False
                            self.positions[ticker]['exit_reason'] = None
                            self.positions[ticker]['exit_shares'] = None

            # --- [Step 1-B] 執行買單 ---
            for entry_order in self.pending_entries:
                max_pos = self.config.get('max_positions', 0)
                if max_pos > 0 and len(self.positions) >= max_pos: break 
                
                ticker = entry_order['ticker']
                if ticker in self.positions: continue
                
                if has_limit_status and todays_data['limit_status'].get(ticker) == '+':
                    continue
                
                raw_open = todays_data['raw_open'].get(ticker)
                raw_low = todays_data['raw_low'].get(ticker)
                adj_close = todays_data['close'].get(ticker)
                raw_close = todays_data['raw_close'].get(ticker)
                
                if pd.isna(raw_open) or pd.isna(raw_low): continue
                if pd.isna(adj_close) or adj_close == 0: continue
                price_ratio = raw_close / adj_close 

                target_adj_price = entry_order.get('limit_price')
                exec_raw_price = None
                
                if target_adj_price is None or pd.isna(target_adj_price):
                    exec_raw_price = raw_open
                else:
                    target_raw_price = target_adj_price * price_ratio
                    if raw_open <= target_raw_price:
                        exec_raw_price = raw_open 
                    elif raw_low <= target_raw_price:
                        exec_raw_price = target_raw_price 
                    else:
                        exec_raw_price = None 
                
                if exec_raw_price:
                    bar_for_calc = {'close': adj_close, 'atr': entry_order['indicators'].get('atr', 0)}
                    
                    stop_price_raw = 0
                    if self.primary_risk_stop is not None:  
                        stop_price_adj = self.primary_risk_stop.get_stop_price(bar_for_calc, adj_close, 'BUY')
                        stop_price_raw = stop_price_adj * price_ratio
                    else:
                        stop_price_raw = 0

                    # 🌟 新增：如果是再平衡訂單，直接使用算好的目標股數；否則呼叫 Sizer
                    if 'target_shares' in entry_order:
                        shares = entry_order['target_shares']
                    else:
                        shares = self.sizer.calculate_shares(self.portfolio_value, exec_raw_price, stop_price_raw)
                    
                    if shares > 0:
                        final_cost_price = exec_raw_price * (1 + self.impact_cost)
                        total_outlay = (shares * final_cost_price) * (1 + self.comm_rate)
                        
                        if self.cash >= total_outlay:
                            self.cash -= total_outlay
                            self.positions[ticker] = {
                                'shares': shares, 
                                'entry_price': final_cost_price, 
                                'cost': total_outlay,
                                'entry_date': today, 
                                'bars_held': 0, 
                                'highest_price': exec_raw_price, 
                                'lowest_price': exec_raw_price,
                                'indicators': entry_order['indicators'],
                                'exit_pending': False, 
                                'exit_reason': None,
                                'price_ratio': price_ratio 
                            }

            self.pending_entries = []

            # --- [Step 2] 盤中監控 (Intraday Stop) ---
            active_tickers = list(self.positions.keys())
            for ticker in active_tickers:
                pos = self.positions[ticker]
                pos['bars_held'] += 1
                
                try:
                    raw_low = todays_data['raw_low'].get(ticker)
                    raw_high = todays_data['raw_high'].get(ticker)
                    raw_open = todays_data['raw_open'].get(ticker)
                    raw_close = todays_data['raw_close'].get(ticker)
                    adj_close = todays_data['close'].get(ticker)
                    if pd.isna(raw_close): continue
                except: continue

                current_ratio = raw_close / adj_close if adj_close else 1.0

                check_bar = {
                    'open': raw_open, 'high': raw_high, 'low': raw_low, 'close': raw_close,
                    'date': today
                }
                check_bar.update(pos['indicators'])

                if 'atr' in check_bar:
                    check_bar['atr'] = check_bar['atr'] * current_ratio

                triggered_stop = False
                for exit_mod in self.exit_policies:
                    mod_name = exit_mod.__class__.__name__
                    is_intraday = "Stop" in mod_name or "Trailing" in mod_name
                    
                    if is_intraday:
                        is_hit, price, reason = exit_mod.check(check_bar, pos)
                        if is_hit:
                            self._execute_sell(today, ticker, price, reason)
                            triggered_stop = True
                            break 
                
                if triggered_stop: continue 

                pos['highest_price'] = max(pos['highest_price'], raw_high)
                pos['lowest_price'] = min(pos['lowest_price'], raw_low)

                for col in indicator_cols:
                    val = todays_data[col].get(ticker)
                    if not pd.isna(val): pos['indicators'][col] = val

                eod_bar = check_bar.copy() 
                
                for exit_mod in self.exit_policies:
                    mod_name = exit_mod.__class__.__name__
                    is_eod = not ("Stop" in mod_name or "Trailing" in mod_name)
                    if is_eod:
                        is_hit, _, reason = exit_mod.check(eod_bar, pos)
                        if is_hit:
                            pos['exit_pending'] = True
                            pos['exit_reason'] = reason
                            break
                            
            # ==========================================
            # 🌟 [新增] 擷取橫截面排名快照 (Cross-Sectional Snapshot)
            # ==========================================
            if 'rank' in todays_data:
                valid_ranks = todays_data['rank'].dropna()
                
                if not valid_ranks.empty:
                    # 如果當天有排名資料，把所有標的的狀態抓下來
                    snap_df = pd.DataFrame({
                        'date': today,
                        'ticker': valid_ranks.index,
                        'rank': valid_ranks.values
                    })
                    
                    # 紀錄它今天是否有觸發買進訊號 (如果沒有 signal 欄位預設為 0)
                    if 'signal' in todays_data:
                        snap_df['signal'] = snap_df['ticker'].map(todays_data['signal']).fillna(0)
                    else:
                        snap_df['signal'] = 0
                        
                    # 把策略動態計算的所有指標 (momentum_score, atr 等) 一併放入快照中
                    for col in indicator_cols:
                        if col in todays_data:
                            snap_df[col] = snap_df['ticker'].map(todays_data[col])
                            
                    self.rank_log.append(snap_df)
            
            # --- [Step 3] 產生買單 ---
            if 'signal' in todays_data:
                signal_series = todays_data['signal']
                candidates = signal_series[signal_series == 1].index.tolist()
                
                if candidates:
                    # 1. 讀取 Config 中的排序設定 (預設使用 crsi)
                    rank_col = self.config.get('rank_metric', 'crsi')
                    asc = self.config.get('ascending', True)
                    
                    # 2. 執行排序
                    if rank_col in todays_data:
                        candidate_ranks = todays_data[rank_col].loc[candidates]
                        sorted_candidates = candidate_ranks.sort_values(ascending=asc).index.tolist()
                    else:
                        sorted_candidates = sorted(candidates)
                        
                    # 3. 計算剩餘空缺並截斷清單
                    max_pos = self.config.get('max_positions', 0)
                    if max_pos > 0:
                        current_pos = len(self.positions)
                        available_slots = max_pos - current_pos
                        if available_slots <= 0:
                            sorted_candidates = [] # 持倉已滿，不產生新買單
                        else:
                            sorted_candidates = sorted_candidates[:available_slots]
                
                    # 4. 將過濾後的標的加入待買清單
                    for ticker in sorted_candidates:
                        if ticker in self.positions: continue
                        
                        indicators_snapshot = {}
                        for col in indicator_cols:
                            val = todays_data[col].get(ticker)
                            if not pd.isna(val): indicators_snapshot[col] = val
                        
                        limit_p = todays_data['limit_price'].get(ticker) if 'limit_price' in todays_data else None

                        self.pending_entries.append({
                            'ticker': ticker, 
                            'signal_date': today, 
                            'indicators': indicators_snapshot,
                            'limit_price': limit_p 
                        })

            # ==========================================
            # 🌟 [新增 Step 3-B] 目標權重再平衡 (Target Weight Rebalancing)
            # ==========================================
            if 'target_weight' in todays_data:
                weights = todays_data['target_weight'].dropna()
                if not weights.empty:
                    # 找出所有「目標要買的」跟「目前持有的」標的聯集
                    target_tickers = set(weights.index)
                    current_tickers = set(self.positions.keys())
                    all_rebalance_tickers = target_tickers.union(current_tickers)
                    
                    for ticker in all_rebalance_tickers:
                        # 如果股票不在目標權重清單中，代表新權重為 0 (必須清倉)
                        target_w = weights.get(ticker, 0.0) 
                        
                        raw_close = todays_data['raw_close'].get(ticker)
                        if pd.isna(raw_close) or raw_close == 0: continue
                        
                        # 1. 精算目標股數
                        target_capital = self.portfolio_value * target_w
                        target_shares = int(target_capital / raw_close)
                        
                        # 2. 獲取目前股數
                        current_shares = self.positions[ticker]['shares'] if ticker in self.positions else 0
                        
                        # 3. 計算差額
                        diff_shares = target_shares - current_shares
                        
                        # 4. 發送對應的 T+1 訂單
                        if diff_shares > 0: 
                            # 加碼或新建倉：丟入待買清單
                            self.pending_entries.append({
                                'ticker': ticker, 
                                'signal_date': today, 
                                'indicators': {}, # 可根據策略補上
                                'limit_price': None,
                                'target_shares': diff_shares, # 🌟 指定加碼股數
                                'reason': 'Rebalance Buy'
                            })
                        elif diff_shares < 0: 
                            # 減碼或清倉：標記為待賣出
                            shares_to_sell = abs(diff_shares)
                            if ticker in self.positions:
                                self.positions[ticker]['exit_pending'] = True
                                self.positions[ticker]['exit_reason'] = 'Rebalance Sell'
                                self.positions[ticker]['exit_shares'] = shares_to_sell # 🌟 指定減碼股數

            # --- [Step 4] 結算 ---
            equity = self.cash
            for ticker, pos in self.positions.items():
                curr_raw_price = todays_data['raw_close'].get(ticker, pos['entry_price'])
                if not pd.isna(curr_raw_price):
                    equity += pos['shares'] * curr_raw_price
            
            self.portfolio_value = equity 
            self.daily_log.append({'date': today, 'equity': round(equity, 2), 'cash': round(self.cash, 2), 'positions': len(self.positions)})

        print(f"✅ Backtest finished. Final Equity: {self.portfolio_value:,.0f}")
        
        # ==========================================
        # 🌟 [新增] 將收集到的快照合併並回傳
        # ==========================================
        if self.rank_log:
            df_rank = pd.concat(self.rank_log, ignore_index=True)
            # 依照日期和名次排序，讓報表更具可讀性
            df_rank = df_rank.sort_values(['date', 'rank']).reset_index(drop=True)
        else:
            # 防呆機制：如果沒有用到 rank 的策略，就回傳空表
            df_rank = pd.DataFrame()
            
        # ⚠️ 注意：這裡的 return 從 2 個變成 3 個了！
        return pd.DataFrame(self.daily_log), pd.DataFrame(self.trade_log), df_rank