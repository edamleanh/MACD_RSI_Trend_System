"""
driver.py - Main Entry Point for MACD Strategy
------------------------------------------------
Usage:
    python src/driver.py --mode backtest --data in_sample
    python src/driver.py --mode backtest --data out_sample
    python src/driver.py --mode optimize
    python src/driver.py --mode live
"""

import os
import sys
import argparse
import datetime
import warnings
import yaml
import optuna

warnings.filterwarnings("ignore")
optuna.logging.set_verbosity(optuna.logging.WARNING)

# Add root directory to sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.data_fetcher import fetch_data, filter_date_range, fetch_live_data
from src.logic import (
    compute_indicators,
    run_backtest,
    compute_metrics,
    save_results,
)
from src.live_engine import LiveEngine

# =========================================================================
# LOAD CONFIG
# =========================================================================

def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def params_from_config(cfg: dict) -> dict:
    """Extracts strategy parameters from the config dictionary."""
    s = cfg["strategy"]
    return {
        "fast":               s["fast"],
        "slow":               s["slow"],
        "signal_period":      s["signal_period"],
        "ema_trend_period":   s["ema_trend_period"],
        "take_profit":        s["take_profit"],
        "cut_loss":           s["cut_loss"],
        "use_trailing":       s.get("use_trailing", True),
        "trailing_activation":s["trailing_activation"],
        "trailing_step":      s["trailing_step"],
        "rsi_period":         s["rsi_period"],
        "rsi_overbought":     s["rsi_overbought"],
        "rsi_oversold":       s["rsi_oversold"],
        "fee_per_trade":      s["fee_per_trade"],
    }

# =========================================================================
# BACKTEST MODE
# =========================================================================

def run_backtest_mode(cfg: dict, data_mode: str) -> None:
    d_cfg = cfg["data"]
    r_cfg = cfg["results"]

    # Create results folder
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir   = os.path.join(ROOT, r_cfg["base_directory"],
                             "backtest", timestamp)
    print(f"\nResults will be saved to: {out_dir}")

    # Fetch data
    df_all = fetch_data(
        symbol     = d_cfg["symbol"],
        source     = d_cfg["source"],
        start_date = d_cfg["start_date"],
        end_date   = d_cfg["end_date"],
        interval   = d_cfg["interval"],
    )

    # Filter by date range
    if data_mode == "in_sample":
        label = "in_sample"
        sd = d_cfg["in_sample"]["start_date"]
        ed = d_cfg["in_sample"]["end_date"]
    else:
        label = "out_sample"
        sd = d_cfg["out_sample"]["start_date"]
        ed = d_cfg["out_sample"]["end_date"]

    df = filter_date_range(df_all, sd, ed)
    print(f"\nRunning backtest on {label} data with {len(df):,} candles...")

    # Calculate indicators and run backtest
    params = params_from_config(cfg)
    df_ind = compute_indicators(df, params)
    result = run_backtest(df_ind, params)

    # Compute metrics and save
    metrics = compute_metrics(result)
    save_results(result, metrics, params, out_dir, mode_label=label)

# =========================================================================
# OPTIMIZATION MODE
# =========================================================================

def run_optimize_mode(cfg: dict) -> None:
    d_cfg = cfg["data"]
    o_cfg = cfg["optimization"]
    r_cfg = cfg["results"]

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir   = os.path.join(ROOT, r_cfg["base_directory"],
                             "optimize", timestamp)
    print(f"\nResults will be saved to: {out_dir}")

    # Fetch data and use in_sample for optimization
    df_all = fetch_data(
        symbol     = d_cfg["symbol"],
        source     = d_cfg["source"],
        start_date = d_cfg["start_date"],
        end_date   = d_cfg["end_date"],
        interval   = d_cfg["interval"],
    )

    df_train = filter_date_range(
        df_all,
        d_cfg["in_sample"]["start_date"],
        d_cfg["in_sample"]["end_date"],
    )

    min_trades = o_cfg.get("min_trades", 30)
    fee        = cfg["strategy"]["fee_per_trade"]

    def objective(trial):
        fast          = trial.suggest_int("fast",         *o_cfg["fast_range"])
        slow          = trial.suggest_int("slow",         *o_cfg["slow_range"])
        if fast >= slow:
            return -999.0

        signal_period = trial.suggest_int("signal_period",  *o_cfg["signal_range"])
        ema_trend     = trial.suggest_int("ema_trend_period",*o_cfg["ema_trend_range"])
        take_profit   = trial.suggest_int("take_profit",    *o_cfg["take_profit_range"])
        cut_loss      = trial.suggest_int("cut_loss",        *o_cfg["cut_loss_range"])
        rsi_period    = trial.suggest_int("rsi_period",      *o_cfg["rsi_period_range"])
        rsi_ob        = trial.suggest_int("rsi_overbought",  *o_cfg["rsi_overbought_range"])
        rsi_os        = trial.suggest_int("rsi_oversold",    *o_cfg["rsi_oversold_range"])

        trail_act = trial.suggest_int("trailing_activation", 2, max(3, take_profit - 1))
        trail_stp = trial.suggest_int("trailing_step",       1, max(2, trail_act - 1))

        params = {
            "fast": fast, "slow": slow, "signal_period": signal_period,
            "ema_trend_period": ema_trend, "take_profit": take_profit,
            "cut_loss": cut_loss, "use_trailing": True,
            "trailing_activation": trail_act, "trailing_step": trail_stp,
            "rsi_period": rsi_period, "rsi_overbought": rsi_ob,
            "rsi_oversold": rsi_os, "fee_per_trade": fee,
        }

        df_ind = compute_indicators(df_train, params)
        res    = run_backtest(df_ind, params)

        if res["trade_counts"] < min_trades:
            return -999.0

        return res["sharpe"] if not (res["sharpe"] != res["sharpe"]) else -999.0

    n_trials = o_cfg.get("n_trials", 200)
    print(f"\n[>>] Starting optimization ({n_trials} trials)...\n")
    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=n_trials, show_progress_bar=True)

    best_params = study.best_params
    best_sharpe = study.best_value

    best_params["use_trailing"]  = True
    best_params["fee_per_trade"] = fee

    print("\n" + "=" * 55)
    print("  BEST PARAMETERS FOUND")
    print("=" * 55)
    print(f"  Sharpe (in_sample): {best_sharpe:.4f}\n")
    for k, v in best_params.items():
        print(f"  {k}: {v}")

    # Save optimization results
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "best_params.yaml"), "w") as f:
        yaml.dump({"strategy": best_params}, f, default_flow_style=False)

    # Re-run backtest on out_sample with best params
    print("\n[>>] Auto re-running backtest on out_sample with best params...")
    df_test = filter_date_range(
        df_all,
        d_cfg["out_sample"]["start_date"],
        d_cfg["out_sample"]["end_date"],
    )
    df_ind  = compute_indicators(df_test, best_params)
    result  = run_backtest(df_ind, best_params)
    metrics = compute_metrics(result)

    opt_bt_dir = os.path.join(out_dir, "optimized_backtest")
    save_results(result, metrics, best_params, opt_bt_dir,
                 mode_label="out_sample (optimized)")

    print(f"\n[OK] All results saved to: {out_dir}")

# =========================================================================
# LIVE MODE
# =========================================================================

def run_live_mode(cfg: dict) -> None:
    """Starts the real-time Paper Trading engine."""
    engine = LiveEngine(cfg)
    try:
        engine.run()
    except Exception as e:
        print(f"[!] Live Engine Error: {e}")

# =========================================================================
# CLI
# =========================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="MACD Strategy Backtest, Optimization & Live Trading"
    )
    parser.add_argument("--mode", required=True,
                        choices=["backtest", "optimize", "live"],
                        help="Run mode: backtest, optimize or live")
    parser.add_argument("--data",
                        choices=["in_sample", "out_sample"],
                        default="out_sample",
                        help="Data range to use (backtest mode only)")
    parser.add_argument("--config",
                        default=os.path.join(ROOT, "config", "config.yaml"),
                        help="Path to config file")
    return parser.parse_args()

def main():
    args = parse_args()
    cfg  = load_config(args.config)

    print("=" * 55)
    print("  MACD_RSI_Trend_System - VN30F1M")
    print("=" * 55)

    if args.mode == "backtest":
        run_backtest_mode(cfg, args.data)
    elif args.mode == "optimize":
        run_optimize_mode(cfg)
    elif args.mode == "live":
        run_live_mode(cfg)

if __name__ == "__main__":
    main()
