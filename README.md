# MACD_RSI_Trend_System - Advanced Algorithmic Trading Bot

## Overview

This project is a comprehensive algorithmic trading system designed for the Vietnam Derivatives Market (VN30F1M). It is a unified platform that allows you to: **Optimize**, **Backtest**, and **Paper Trade** in real-time.

## Introduction

The system utilizes a MACD-based strategy combined with an EMA Trend filter and RSI overbought/oversold filters. The bot is designed with a professional modular architecture, ensuring separation between data, strategy logic, and execution engine.

### Key Features:
1. **Backtesting Engine**: Simulates strategy performance on historical data with full support for transaction fees and dynamic stop-loss (Trailing Stop).
2. **Optuna Optimizer**: Automatically searches for the optimal parameter set (Fast, Slow, Signal, TP/SL, etc.) to maximize the Sharpe Ratio.
3. **Live Paper Trading**: Runs directly in the terminal with a real-time Dashboard updated every minute, managing a virtual capital of 100M VND.

## Project Structure

```
MACD_RSI_Trend_System/
├── config/
│   └── config.yaml          # Unified configuration (Dates, Parameters, Paper Trading)
├── src/
│   ├── data_fetcher.py      # Fetches data from vnstock (Batch & Live)
│   ├── logic.py             # Core strategy logic (Indicators, Signals & Engine)
│   ├── paper_broker.py      # Virtual wallet for account and trade history management
│   ├── live_engine.py       # Live execution engine and Terminal Dashboard
│   └── driver.py            # CLI entry point (Use with --mode)
├── results/                 # Stores charts, reports, and trading states
└── requirements.txt         # Required libraries (Pandas, Matplotlib, Optuna, Rich...)
```

## Usage

### 1. Installation
```bash
pip install -r requirements.txt
```

### 2. Backtesting
Test the strategy on In-sample or Out-of-sample data defined in the config.
```bash
python src/driver.py --mode backtest --data out_sample
```

### 3. Optimization
Find the most profitable parameters using Optuna.
```bash
python src/driver.py --mode optimize
```

### 4. Live Paper Trading
Launch the bot directly in the terminal. The bot automatically updates prices every minute and reports to the Dashboard.
```bash
python src/driver.py --mode live
```

## Strategy Logic

- **Long Entry**: MACD crosses above Signal AND Price > EMA Trend AND RSI < Overbought.
- **Short Entry**: MACD crosses below Signal AND Price < EMA Trend AND RSI > Oversold.
- **Exit Logic**:
  - Hits fixed Take Profit or Stop Loss.
  - Trailing Stop activates after reaching a profit threshold.
  - Trend reversal signal from MACD.

## Configuration

All parameters are centrally managed in `config/config.yaml`. You can easily adjust:
- Initial Capital.
- MACD/RSI/EMA parameters.
- Backtest date ranges.
- Live polling frequency.

## Algorithm Development Journey (Demo Results)

We documented the transition from a standard naive strategy to a professionally optimized trading system for the VN30F1M 15m timeframe.

### 1. Stage 1: Naive Baseline (Initial State)
*The strategy used standard MACD settings found in most retail tutorials.*
- **Indicators**:
  - `Fast EMA: 12`, `Slow EMA: 26`, `Signal Period: 9`
  - `EMA Trend Filter: 200`
  - `RSI Period: 14` (Overbought: 70, Oversold: 30)
- **Risk Management**:
  - `Take Profit: 10 pts`, `Stop Loss: 5 pts`
  - `Trailing Stop: Disabled`
- **Results**:
  - **In-Sample PnL: -6,510,000 VND**
  - Sharpe Ratio: -0.42

### 2. Stage 2: Optimized Strategy (Training)
*Using the Optuna engine to search through 300 iterations to find the optimal mathematical edge.*
- **Indicators**:
  - `Fast EMA: 8`, `Slow EMA: 53`, `Signal Period: 15`
  - `EMA Trend Filter: 38`
  - `RSI Period: 13` (Overbought: 57, Oversold: 45)
- **Risk Management**:
  - `Take Profit: 18 pts`, `Stop Loss: 5 pts`
  - `Trailing Stop: Enabled` (Activation: 16, Step: 14)
- **Results**:
  - **In-Sample PnL: +23,700,000 VND**
  - Sharpe Ratio: 1.59

### 3. Stage 3: Real-World Validation (Testing)
*Validated the optimized parameters on Out-of-Sample data (April 2025 - Dec 2025) that the system has never seen before.*
- **Out-of-Sample Result**:
  - **Net Profit: +8,530,000 VND**
  - Sharpe Ratio: 1.52


## Disclaimer

This project is for educational and research purposes only. Trading derivatives involves significant financial risk. Always verify thoroughly before using real capital.
