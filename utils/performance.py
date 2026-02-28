import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

class PerformanceAnalyzer:
    def __init__(self, daily_log, trade_log, risk_free_rate=0.02):
        self.daily_df = pd.DataFrame(daily_log).set_index('date')
        self.trade_df = pd.DataFrame(trade_log)
        self.rf = risk_free_rate

    def calculate(self):
        d = self.daily_df
        t = self.trade_df
        
        if d.empty or t.empty: return {"Error": "No trades or data"}

        # 基礎數據
        final_equity = d['equity'].iloc[-1]
        initial_equity = d['equity'].iloc[0]
        total_days = len(d)
        total_years = total_days / 252
        
        # 1. Net Profit
        net_profit = final_equity - initial_equity
        
        # 2. Annual Return (算術平均) vs 5. CAGR (幾何平均)
        # 業界通常講 Annual Return 指的是 CAGR，但您區分了兩者
        # 算術平均年報酬 = 總報酬率 / 年數
        total_ret_pct = (final_equity / initial_equity) - 1
        arithmetic_annual_ret = total_ret_pct / total_years 
        
        # CAGR = (End/Start)^(1/Years) - 1
        cagr = (final_equity / initial_equity) ** (1/total_years) - 1
        
        # 3. % Profit (總報酬率)
        pct_profit = total_ret_pct * 100
        
        # 4. Exposure % (修正後定義)
        # 每日曝險 = (Equity - Cash) / Equity
        d['exposure'] = (d['equity'] - d['cash']) / d['equity']
        exposure_pct = d['exposure'].mean() # 取平均
        
        # 6. RAR (Risk Adjusted Return)
        if exposure_pct > 0:
            rar = cagr / exposure_pct
        else:
            rar = 0
        
        # 7. MDD
        d['peak'] = d['equity'].cummax()
        d['dd'] = (d['equity'] - d['peak']) / d['peak']
        mdd = d['dd'].min() # 這是負數，例如 -0.2
        
        # 8. Recovery Factor = Net Profit / Max Drawdown Amount
        mdd_amount = (d['peak'] - d['equity']).max()
        recovery_factor = net_profit / mdd_amount if mdd_amount > 0 else 999
        
        # 9. CAGR / MDD (Mar Ratio 變形)
        cagr_mdd = cagr / abs(mdd) if mdd != 0 else 0
        
        # 10. RAR / MDD
        rar_mdd = rar / abs(mdd) if mdd != 0 else 0
        
        # 交易統計
        wins = t[t['profit'] > 0]
        losses = t[t['profit'] <= 0]
        
        avg_win = wins['profit'].mean() if len(wins) > 0 else 0
        avg_loss = abs(losses['profit'].mean()) if len(losses) > 0 else 0
        
        # 11. Profit Factor = Gross Profit / Gross Loss
        gross_profit = wins['profit'].sum()
        gross_loss = abs(losses['profit'].sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 999
        
        # 12. Payoff Ratio = Avg Win / Avg Loss
        payoff_ratio = avg_win / avg_loss if avg_loss > 0 else 0
        
        # 13. Sharpe Ratio
        # Daily returns
        d['ret'] = d['equity'].pct_change().fillna(0)
        daily_rf = self.rf / 252
        excess_ret = d['ret'] - daily_rf
        sharpe = (excess_ret.mean() / excess_ret.std()) * np.sqrt(252) if excess_ret.std() > 0 else 0
        
        # 其他
        win_rate = len(wins) / len(t)
        avg_bars = t['bars_held'].mean()
        
        return {
            "Net Profit": net_profit,
            "Annual Return (Arith)": f"{arithmetic_annual_ret*100:.2f}%",
            "% Profit": f"{pct_profit:.2f}%",
            "Exposure %": f"{exposure_pct*100:.2f}%",
            "CAGR": f"{cagr*100:.2f}%",
            "RAR": f"{rar*100:.2f}%",
            "MDD": f"{mdd*100:.2f}%",
            "Recovery Factor": f"{recovery_factor:.2f}",
            "CAGR/MDD": f"{cagr_mdd:.2f}",
            "RAR/MDD": f"{rar_mdd:.2f}",
            "Profit Factor": f"{profit_factor:.2f}",
            "Payoff Ratio": f"{payoff_ratio:.2f}",
            "Sharpe Ratio": f"{sharpe:.2f}",
            "# Trades": len(t),
            "Avg Profit": f"{t['profit'].mean():.2f}",
            "Avg % Profit": f"{(t['profit']/t['entry_value']).mean()*100:.2f}%",
            "Avg Bars Held": f"{avg_bars:.1f}",
            "% Winners": f"{win_rate*100:.2f}%"
        }