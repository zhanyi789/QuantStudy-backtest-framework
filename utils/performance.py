import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

class PerformanceAnalyzer:
    def __init__(self, daily_log, trade_log, risk_free_rate=0.02, benchmark_prices=None):
        self.daily_df = pd.DataFrame(daily_log)
        if not self.daily_df.empty and 'date' in self.daily_df.columns:
            self.daily_df['date'] = pd.to_datetime(self.daily_df['date'])
            self.daily_df = self.daily_df.set_index('date')
            
        self.trade_df = pd.DataFrame(trade_log)
        self.rf = risk_free_rate
        self.benchmark_prices = benchmark_prices 
        self.metrics = {}

    def calculate(self):
        d = self.daily_df
        t = self.trade_df
        
        if d.empty or t.empty: 
            return {"Error": "No trades or data"}

        initial_equity = d['equity'].iloc[0]
        final_equity = d['equity'].iloc[-1]
        total_days = len(d)
        total_years = total_days / 252.0
        
        # --- 報酬率計算 (策略) ---
        d['ret'] = d['equity'].pct_change().fillna(0)
        total_ret_pct = (final_equity / initial_equity) - 1
        cagr = (final_equity / initial_equity) ** (1/total_years) - 1
        
        # 🌟 單利計算與高點紀錄
        d['simple_equity'] = initial_equity * (1 + d['ret'].cumsum())
        d['peak'] = d['equity'].cummax()               # 複利高點
        d['simple_peak'] = d['simple_equity'].cummax() # 單利高點
        simple_ret_pct = d['ret'].sum()
        
        # --- 最大回撤 (MDD) ---
        d['dd'] = (d['equity'] - d['peak']) / d['peak']
        mdd = d['dd'].min()
        
        # --- 曝險與風險調整後報酬 ---
        d['exposure'] = (d['equity'] - d['cash']) / d['equity']
        exposure_pct = d['exposure'].mean() 
        daily_rf = self.rf / 252.0
        excess_ret = d['ret'] - daily_rf
        sharpe = (excess_ret.mean() / excess_ret.std()) * np.sqrt(252) if excess_ret.std() > 0 else 0
        # Sortino 分母：半變異數（Semi-deviation），用全部天數當分母，符合標準公式
        # sqrt(mean(min(ret, 0)^2)) * sqrt(252)，而非只看負報酬天數的標準差
        downside_sq = np.minimum(d['ret'], 0) ** 2
        downside_std = np.sqrt(downside_sq.mean()) * np.sqrt(252)
        sortino = (cagr - self.rf) / downside_std if downside_std > 0 else 0
        calmar = cagr / abs(mdd) if mdd != 0 else 0

        # --- 大盤基準 (Benchmark) 計算 ---
        bench_cagr = 0
        bench_simple_ret = 0
        if self.benchmark_prices is not None:
            bench = self.benchmark_prices.reindex(d.index).ffill().bfill()
            bench_ret = bench.pct_change().fillna(0)
            d['bench_equity'] = initial_equity * (bench / bench.iloc[0])
            d['bench_simple'] = initial_equity * (1 + bench_ret.cumsum())
            
            bench_total_ret = (d['bench_equity'].iloc[-1] / initial_equity) - 1
            bench_cagr = (1 + bench_total_ret) ** (1/total_years) - 1
            bench_simple_ret = bench_ret.sum()

        # --- 交易統計與 MAE/MFE ---
        wins = t[t['profit'] > 0]
        losses = t[t['profit'] <= 0]
        win_rate = len(wins) / len(t) if len(t) > 0 else 0
        gross_profit = wins['profit'].sum()
        gross_loss = abs(losses['profit'].sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 999
        
        if 'lowest_price' in t.columns and 'highest_price' in t.columns:
            t['MAE_%'] = (t['lowest_price'] / t['entry_price']) - 1
            t['MFE_%'] = (t['highest_price'] / t['entry_price']) - 1
            avg_mae = f"{t['MAE_%'].mean()*100:.2f}%"
            avg_mfe = f"{t['MFE_%'].mean()*100:.2f}%"
        else:
            avg_mae = avg_mfe = "N/A"
        
        self.metrics = {
            "Total Return (Compound)": f"{total_ret_pct*100:.2f}%",
            "Total Return (Simple)": f"{simple_ret_pct*100:.2f}%",
            "CAGR": f"{cagr*100:.2f}%",
            "MDD": f"{mdd*100:.2f}%",
            "Sharpe Ratio": f"{sharpe:.2f}",
            "Sortino Ratio": f"{sortino:.2f}",
            "Calmar Ratio": f"{calmar:.2f}",
            "Profit Factor": f"{profit_factor:.2f}",
            "Win Rate": f"{win_rate*100:.2f}%",
            "Total Trades": len(t),
            "Exposure %": f"{exposure_pct*100:.2f}%",
            "Avg MAE (Risk)": avg_mae,
            "Avg MFE (Reward)": avg_mfe,
            "_bench_cagr": bench_cagr,
            "_bench_simple_ret": bench_simple_ret
        }
        return self.metrics

    def plot_tearsheet(self):
        if self.daily_df.empty: return

        fig = plt.figure(figsize=(16, 24))
        gs = fig.add_gridspec(6, 2, hspace=0.4, wspace=0.2)
        fig.suptitle('Quantitative Strategy Performance Tear Sheet', fontsize=20, fontweight='bold', y=0.92)

        # =========================================
        # 1. 資金曲線 - 複利版 (含大盤對比、回撤區、創新高亮點)
        # =========================================
        ax1 = fig.add_subplot(gs[0, :])
        
        if 'bench_equity' in self.daily_df.columns:
            ax1.plot(self.daily_df.index, self.daily_df['bench_equity'], color='gray', linestyle='--', linewidth=1.5, 
                     label=f"Benchmark (CAGR: {self.metrics.get('_bench_cagr', 0)*100:.2f}%)")
        
        ax1.plot(self.daily_df.index, self.daily_df['equity'], color='#1f77b4', linewidth=2, 
                 label=f"Strategy (CAGR: {self.metrics.get('CAGR', 'N/A')})")
        
        # 粉紅回撤填色
        ax1.fill_between(self.daily_df.index, self.daily_df['equity'], self.daily_df['peak'], color='lightpink', alpha=0.5)
        
        # 🌟 點綴創新高的綠色點點 (邏輯：今天淨值 == 歷史高點，且嚴格大於昨天的歷史高點)
        new_highs = self.daily_df[(self.daily_df['equity'] == self.daily_df['peak']) & 
                                  (self.daily_df['equity'] > self.daily_df['peak'].shift(1).fillna(0))]
        ax1.scatter(new_highs.index, new_highs['equity'], color='#2ca02c', s=20, zorder=5, label='New High')
        
        ax1.set_title("Cumulative Equity (Compound)", fontsize=14)
        ax1.set_ylabel('Compound Equity ($)')
        ax1.grid(True, alpha=0.3, linestyle='--')
        ax1.legend(loc='upper left', fontsize=12)

        # =========================================
        # 2. 資金曲線 - 單利版 (含大盤對比、回撤區、創新高亮點)
        # =========================================
        ax1_simple = fig.add_subplot(gs[1, :])
        
        if 'bench_simple' in self.daily_df.columns:
            ax1_simple.plot(self.daily_df.index, self.daily_df['bench_simple'], color='gray', linestyle='--', linewidth=1.5, 
                            label=f"Benchmark (Return: {self.metrics.get('_bench_simple_ret', 0)*100:.2f}%)")
            
        ax1_simple.plot(self.daily_df.index, self.daily_df['simple_equity'], color='#ff7f0e', linewidth=2, 
                        label=f"Strategy (Return: {self.metrics.get('Total Return (Simple)', 'N/A')})")
        
        # 粉紅回撤填色
        ax1_simple.fill_between(self.daily_df.index, self.daily_df['simple_equity'], self.daily_df['simple_peak'], color='lightpink', alpha=0.5)

        # 🌟 單利版的創新高綠色點點
        simple_new_highs = self.daily_df[(self.daily_df['simple_equity'] == self.daily_df['simple_peak']) & 
                                         (self.daily_df['simple_equity'] > self.daily_df['simple_peak'].shift(1).fillna(0))]
        ax1_simple.scatter(simple_new_highs.index, simple_new_highs['simple_equity'], color='#2ca02c', s=20, zorder=5, label='New High')

        ax1_simple.set_title("Cumulative Equity (Simple)", fontsize=14)
        ax1_simple.set_ylabel('Simple Equity ($)')
        ax1_simple.grid(True, alpha=0.3, linestyle='--')
        ax1_simple.legend(loc='upper left', fontsize=12)

        # =========================================
        # 3. 水下圖與部位曝險
        # =========================================
        ax2 = fig.add_subplot(gs[2, :])
        ax2.fill_between(self.daily_df.index, self.daily_df['dd'] * 100, 0, color='#d62728', alpha=0.4, label='Drawdown')
        ax2.plot(self.daily_df.index, self.daily_df['dd'] * 100, color='#d62728', linewidth=1)
        ax2.set_ylabel('Drawdown (%)', color='#d62728')
        ax2.set_title(f"Underwater Plot & Exposure Timeline (MDD: {self.metrics.get('MDD', 'N/A')})", fontsize=14)
        
        ax2_exp = ax2.twinx()
        ax2_exp.fill_between(self.daily_df.index, self.daily_df['exposure'] * 100, 0, color='gray', alpha=0.15, label='Exposure')
        ax2_exp.plot(self.daily_df.index, self.daily_df['exposure'] * 100, color='gray', linewidth=0.5, alpha=0.5)
        ax2_exp.set_ylabel('Exposure (%)', color='gray')
        ax2_exp.set_ylim(0, 105) 

        # =========================================
        # 4. 月報酬率熱力圖
        # =========================================
        ax3 = fig.add_subplot(gs[3:5, 0])
        try:
            monthly_ret = self.daily_df['equity'].resample('ME').last().pct_change()
            m_df = pd.DataFrame({'return': monthly_ret})
            m_df['Year'] = m_df.index.year
            m_df['Month'] = m_df.index.month
            heatmap_data = m_df.pivot(index='Year', columns='Month', values='return')
            heatmap_data.columns = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][:len(heatmap_data.columns)]
            sns.heatmap(heatmap_data, annot=True, cmap='RdYlGn', center=0, fmt='.1%', ax=ax3, cbar=False, linewidths=.5)
            ax3.set_title('Monthly Return Heatmap', fontsize=14)
            ax3.set_ylabel(''); ax3.set_xlabel('')
        except Exception as e:
            ax3.text(0.5, 0.5, f"Heatmap Error: {e}", ha='center', va='center')

        # =========================================
        # 5. 報酬率分佈直方圖
        # =========================================
        ax4 = fig.add_subplot(gs[3, 1])
        sns.histplot(self.daily_df['ret'] * 100, bins=50, kde=True, color='purple', ax=ax4)
        ax4.axvline(x=0, color='black', linestyle='--', alpha=0.5)
        ax4.set_title('Daily Return Distribution Histogram', fontsize=14)
        ax4.set_xlabel('Daily Return (%)')
        ax4.set_ylabel('Frequency')

        # =========================================
        # 6. 滾動夏普值
        # =========================================
        ax5 = fig.add_subplot(gs[4, 1])
        roll_window = 126
        if len(self.daily_df) > roll_window:
            roll_ret = self.daily_df['ret'].rolling(roll_window)
            roll_sharpe = (roll_ret.mean() / roll_ret.std()) * np.sqrt(252)
            ax5.plot(self.daily_df.index, roll_sharpe, color='darkorange', linewidth=1.5)
            ax5.axhline(y=1.0, color='black', linestyle='--', alpha=0.5) 
            ax5.set_title('Rolling 6-Month Sharpe Ratio', fontsize=14)
            ax5.set_ylabel('Sharpe Ratio')
            ax5.grid(True, alpha=0.3)
        else:
            ax5.text(0.5, 0.5, "Not enough data for Rolling Sharpe", ha='center', va='center')

        # =========================================
        # 7. MAE 與 MFE 散佈圖
        # =========================================
        ax6 = fig.add_subplot(gs[5, :])
        if not self.trade_df.empty and 'MAE_%' in self.trade_df.columns:
            sns.scatterplot(x=self.trade_df['MAE_%']*100, y=self.trade_df['profit_pct']*100, 
                            hue=(self.trade_df['profit'] > 0), palette={True: 'green', False: 'red'}, 
                            alpha=0.6, s=50, ax=ax6, legend=False)
            ax6.axvline(x=0, color='black', linestyle='-', alpha=0.3)
            ax6.axhline(y=0, color='black', linestyle='-', alpha=0.3)
            ax6.set_title('Trade Risk vs Reward (MAE vs Final Profit)', fontsize=14)
            ax6.set_xlabel('Maximum Adverse Excursion / Max Floating Loss (%)')
            ax6.set_ylabel('Final Trade Profit (%)')
            ax6.grid(True, alpha=0.3, linestyle='--')
        else:
            ax6.text(0.5, 0.5, "MAE/MFE Data Not Available in Trade Log", ha='center', va='center')

        plt.tight_layout(rect=[0, 0, 1, 0.96]) 
        plt.show()