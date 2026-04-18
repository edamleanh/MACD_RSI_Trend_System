"""
logic.py
--------
Contains the entire MACD strategy logic:
  - Indicator Calculation (MACD, EMA Trend, RSI)
  - Backtest Loop (StopLoss / TakeProfit / TrailingStop)
  - Performance Metrics calculation (Sharpe, Drawdown, HPR...)
  - Result persistence to files
"""

import os
import math
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")          # No window display, only file saving
import matplotlib.pyplot as plt

# =========================================================================
# INDICATORS
# =========================================================================

def _compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta    = series.diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def compute_indicators(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """
    Adds indicator columns to the DataFrame.
    """
    d = df.copy()
    d["EMA_fast"]     = d["Close"].ewm(span=params["fast"],             adjust=False).mean()
    d["EMA_slow"]     = d["Close"].ewm(span=params["slow"],             adjust=False).mean()
    d["MACD"]         = d["EMA_fast"] - d["EMA_slow"]
    d["Signal"]       = d["MACD"].ewm(span=params["signal_period"],     adjust=False).mean()
    d["Histogram"]    = d["MACD"] - d["Signal"]
    d["EMA_Trend"]    = d["Close"].ewm(span=params["ema_trend_period"], adjust=False).mean()
    d["RSI"]          = _compute_rsi(d["Close"], period=params["rsi_period"])
    d["Point_Change"] = d["Close"].diff()
    return d

def get_latest_signal(df: pd.DataFrame, params: dict):
    """
    Gets the current signal from the last row of the DataFrame (for Live Trading).
    Returns: action (1: Long, -1: Short, 0: None), stats (dict)
    """
    if len(df) < 2:
        return 0, {}
        
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    macd_cross_up = (prev["MACD"] <= prev["Signal"]) and (last["MACD"] > last["Signal"])
    macd_cross_down = (prev["MACD"] >= prev["Signal"]) and (last["MACD"] < last["Signal"])
    
    stats = {
        "price":  last["Close"],
        "macd":   last["MACD"],
        "signal": last["Signal"],
        "rsi":    last["RSI"],
        "trend":  last["EMA_Trend"]
    }
    
    # Long Logic
    if macd_cross_up and last["Close"] > last["EMA_Trend"] and last["RSI"] < params["rsi_overbought"]:
        return 1, stats
        
    # Short Logic
    if macd_cross_down and last["Close"] < last["EMA_Trend"] and last["RSI"] > params["rsi_oversold"]:
        return -1, stats
        
    return 0, stats

# =========================================================================
# BACKTEST ENGINE
# =========================================================================

def run_backtest(df: pd.DataFrame, params: dict) -> dict:
    """
    Executes backtest loop candle by candle.
    """
    take_profit         = params["take_profit"]
    cut_loss            = params["cut_loss"]
    use_trailing        = params.get("use_trailing", True)
    trailing_activation = params["trailing_activation"]
    trailing_step       = params["trailing_step"]
    rsi_overbought      = params["rsi_overbought"]
    rsi_oversold        = params["rsi_oversold"]
    fee                 = params["fee_per_trade"]

    positions       = [0]
    strategy_points = [0.0]
    trade_counts    = 0
    curr_pos        = 0
    entry_price     = 0.0
    highest_price   = 0.0
    lowest_price    = 0.0

    close_arr  = df["Close"].values
    high_arr   = df["High"].values
    low_arr    = df["Low"].values
    macd_arr   = df["MACD"].values
    signal_arr = df["Signal"].values
    trend_arr  = df["EMA_Trend"].values
    rsi_arr    = df["RSI"].values

    for i in range(1, len(df)):
        macd        = macd_arr[i]
        sig         = signal_arr[i]
        prev_macd   = macd_arr[i - 1]
        prev_signal = signal_arr[i - 1]
        curr_price  = close_arr[i]
        prev_price  = close_arr[i - 1]
        curr_high   = high_arr[i]
        curr_low    = low_arr[i]
        ema_trend   = trend_arr[i]
        curr_rsi    = rsi_arr[i]
        pts         = 0.0

        # --- RISK MANAGEMENT ---
        if curr_pos == 1:
            highest_price = max(highest_price, curr_high)

            if entry_price - curr_low >= cut_loss:
                curr_pos = 0; trade_counts += 1
                pts = (entry_price - cut_loss) - prev_price - fee

            elif use_trailing and highest_price - entry_price >= trailing_activation:
                t_exit = highest_price - trailing_step
                if curr_low <= t_exit:
                    curr_pos = 0; trade_counts += 1
                    pts = (min(prev_price, t_exit) - prev_price) - fee
                else:
                    pts = curr_price - prev_price

            elif curr_high - entry_price >= take_profit:
                curr_pos = 0; trade_counts += 1
                pts = (entry_price + take_profit) - prev_price - fee
            else:
                pts = curr_price - prev_price

        elif curr_pos == -1:
            lowest_price = min(lowest_price, curr_low)

            if curr_high - entry_price >= cut_loss:
                curr_pos = 0; trade_counts += 1
                pts = prev_price - (entry_price + cut_loss) - fee

            elif use_trailing and entry_price - lowest_price >= trailing_activation:
                t_exit = lowest_price + trailing_step
                if curr_high >= t_exit:
                    curr_pos = 0; trade_counts += 1
                    pts = (prev_price - max(prev_price, t_exit)) - fee
                else:
                    pts = prev_price - curr_price

            elif entry_price - curr_low >= take_profit:
                curr_pos = 0; trade_counts += 1
                pts = prev_price - (entry_price - take_profit) - fee
            else:
                pts = prev_price - curr_price

        # --- SIGNAL GENERATION (MACD + EMA Trend + RSI) ---
        if prev_macd <= prev_signal and macd > sig \
                and curr_price > ema_trend and curr_rsi < rsi_overbought:
            if curr_pos in (-1, 0):
                if curr_pos == -1:
                    trade_counts += 1; pts -= fee
                trade_counts += 1; pts -= fee
                curr_pos = 1; entry_price = curr_price; highest_price = curr_price

        elif prev_macd >= prev_signal and macd < sig \
                and curr_price < ema_trend and curr_rsi > rsi_oversold:
            if curr_pos in (1, 0):
                if curr_pos == 1:
                    trade_counts += 1; pts -= fee
                trade_counts += 1; pts -= fee
                curr_pos = -1; entry_price = curr_price; lowest_price = curr_price

        strategy_points.append(pts)
        positions.append(curr_pos)

    # --- RESULTS ---
    df_res = df.copy()
    df_res["Position"]           = positions
    df_res["Strategy_Points"]    = strategy_points
    df_res["Cumulative_Market"]  = df_res["Point_Change"].cumsum()
    df_res["Cumulative_Strategy"]= pd.Series(strategy_points).cumsum().values

    total_points = df_res["Cumulative_Strategy"].iloc[-1]

    # Sharpe Ratio (Daily)
    daily = df_res["Strategy_Points"].resample("D").sum().dropna()
    if daily.std() == 0 or len(daily) < 5:
        sharpe = float("nan")
    else:
        sharpe = (daily.mean() / daily.std()) * math.sqrt(252)

    # Max Drawdown
    cum = df_res["Cumulative_Strategy"].values
    peak = np.maximum.accumulate(cum)
    dd = cum - peak
    max_drawdown = float(dd.min())

    return {
        "df_result":    df_res,
        "total_points": total_points,
        "trade_counts": trade_counts,
        "sharpe":       sharpe,
        "max_drawdown": max_drawdown,
    }

# =========================================================================
# PERFORMANCE METRICS
# =========================================================================

def compute_metrics(result: dict, capital: float = 400_000_000,
                    contract_value: float = 100_000) -> dict:
    """Calculates performance metrics from backtest results."""
    total_pts  = result["total_points"]
    net_profit = total_pts * contract_value
    hpr        = (net_profit / capital) * 100

    # Longest drawdown
    df_res = result["df_result"]
    cum    = df_res["Cumulative_Strategy"].resample("D").last().dropna()
    peak   = cum.expanding().max()
    in_dd  = cum < peak
    longest_dd = 0
    count = 0
    for v in in_dd:
        if v:
            count += 1
            longest_dd = max(longest_dd, count)
        else:
            count = 0

    return {
        "total_trades":   result["trade_counts"],
        "total_points":   total_pts,
        "net_profit":     net_profit,
        "hpr_pct":        hpr,
        "max_drawdown":   result["max_drawdown"],
        "longest_dd_days":longest_dd,
        "sharpe":         result["sharpe"],
        "final_capital":  capital + net_profit,
    }

# =========================================================================
# SAVE RESULTS
# =========================================================================

def save_results(result: dict, metrics: dict, params: dict,
                 out_dir: str, mode_label: str = "backtest") -> None:
    """Saves equity curve, performance metrics, and trade log to folder."""
    os.makedirs(out_dir, exist_ok=True)
    df_res = result["df_result"]

    # --- Equity Curve ---
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8),
                                   gridspec_kw={"height_ratios": [2, 1]})
    ax1.plot(df_res.index, df_res["Cumulative_Strategy"],
             label="MACD Strategy", color="green")
    ax1.plot(df_res.index, df_res["Cumulative_Market"],
             label="Buy & Hold", color="gray", linestyle="--", alpha=0.6)
    ax1.set_title(f"MACD Strategy - Equity Curve ({mode_label})")
    ax1.legend(); ax1.grid(True, alpha=0.3)

    ax2.bar(df_res.index, df_res["Histogram"],
            color=["green" if v >= 0 else "red" for v in df_res["Histogram"]],
            alpha=0.5, label="MACD Histogram")
    ax2.plot(df_res.index, df_res["MACD"],   color="blue",  label="MACD",   linewidth=0.8)
    ax2.plot(df_res.index, df_res["Signal"], color="red",   label="Signal", linewidth=0.8)
    ax2.legend(); ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, "equity_curve.png"), dpi=120)
    plt.close()

    # --- Performance Metrics ---
    with open(os.path.join(out_dir, "performance_metrics.txt"), "w") as f:
        f.write(f"=== MACD Strategy - Performance Metrics ({mode_label}) ===\n\n")
        f.write(f"Total trades      : {metrics['total_trades']}\n")
        f.write(f"Total points      : {metrics['total_points']:.2f}\n")
        f.write(f"Net profit        : {metrics['net_profit']:,.0f} VND\n")
        f.write(f"HPR               : {metrics['hpr_pct']:.2f}%\n")
        f.write(f"Max Drawdown      : {metrics['max_drawdown']:.2f} pts\n")
        f.write(f"Longest Drawdown  : {metrics['longest_dd_days']} days\n")
        f.write(f"Sharpe Ratio      : {metrics['sharpe']:.4f}\n")
        f.write(f"Final capital     : {metrics['final_capital']:,.0f} VND\n")
        f.write(f"\n=== Parameters ===\n")
        for k, v in params.items():
            f.write(f"  {k}: {v}\n")

    # --- Trade Log ---
    trades = df_res[df_res["Strategy_Points"] != 0.0][
        ["Close", "Position", "Strategy_Points", "Cumulative_Strategy"]
    ]
    trades.to_csv(os.path.join(out_dir, "trade_log.csv"))

    print(f"[OK] Results saved to: {out_dir}")
    print(f"     Total trades : {metrics['total_trades']}")
    print(f"     Net profit   : {metrics['net_profit']:,.0f} VND")
    print(f"     HPR          : {metrics['hpr_pct']:.2f}%")
    print(f"     Sharpe Ratio : {metrics['sharpe']:.4f}")
