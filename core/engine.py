import duckdb
import pandas as pd
import numpy as np
from collections import defaultdict

# ==========================================
# 核心引擎 
# ==========================================

class AdvancedEventEngine:
    def __init__(self, data_feed=None, 
                 initial_cash=100000, 
                 impact_cost=0.0, 
                 comm_rate=0.0):
        
        if data_feed is not None:
            self.df_data = data_feed
        else:
            self.df_data = None
            
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.portfolio_value = initial_cash
        
        self.impact_cost = impact_cost
        self.comm_rate = comm_rate
        
        self.positions = {}
        self.pending_entries = []
        self.daily_log = []
        self.trade_log = []
        
        # 🌟 [新增] 準備一個空列表來接每期的橫截面排名快照
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

    def _execute_sell(self, date, ticker, raw_price, reason):
        pos = self.positions.pop(ticker)
        shares = pos['shares']
        
        exec_price = raw_price * (1 - self.impact_cost)
        
        proceeds = shares * exec_price
        comm = proceeds * self.comm_rate
        net_proceeds = proceeds - comm
        
        self.cash += net_proceeds
        
        cost = pos['cost'] 
        profit = net_proceeds - cost
        profit_pct = (net_proceeds / cost) - 1
        
        self.trade_log.append({
            'ticker': ticker,
            'entry_date': pos['entry_date'],
            'exit_date': date,
            'entry_price': pos['entry_price'], 
            'exit_price': exec_price,          
            'shares': shares,
            'profit': profit,
            'profit_pct': profit_pct,
            'reason': reason,
            'bars_held': pos['bars_held'],
            'entry_value': cost,
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
                    if has_limit_status and todays_data['limit_status'].get(ticker) == '-':
                        continue 
                        
                    raw_open = todays_data['raw_open'].get(ticker)
                    if not pd.isna(raw_open):
                        self._execute_sell(today, ticker, raw_open, pos['exit_reason'])

            # --- [Step 1-B] 執行買單 ---
            for entry_order in self.pending_entries:
                if max_positions and len(self.positions) >= max_positions: break 
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
                
                if 'rank' in todays_data and candidates:
                    candidate_ranks = todays_data['rank'].loc[candidates]
                    sorted_candidates = candidate_ranks.sort_values().index.tolist()
                else:
                    sorted_candidates = sorted(candidates)
                
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