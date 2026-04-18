import json
import os
import pandas as pd
from datetime import datetime

class PaperBroker:
    def __init__(self, state_file, log_file, initial_capital=100000000):
        self.state_file = state_file
        self.log_file = log_file
        self.initial_capital = initial_capital
        
        # Load state or initialize
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    self.state = json.load(f)
            except:
                self.state = self._init_default_state()
        else:
            self.state = self._init_default_state()
            self.save_state()

    def _init_default_state(self):
        return {
            "balance": self.initial_capital,
            "position": 0,          # 0: None, 1: Long, -1: Short
            "entry_price": 0.0,
            "highest_price": 0.0,
            "lowest_price": 0.0,
            "entry_time": None,
            "total_profit": 0.0
        }

    def save_state(self):
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        with open(self.state_file, 'w') as f:
            json.dump(self.state, f, indent=4)

    def log_trade(self, action, price, points, profit_vnd):
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        df = pd.DataFrame([{
            "Timestamp": timestamp,
            "Action": action,
            "Price": price,
            "Points": points,
            "Profit_VND": profit_vnd,
            "Balance": self.state["balance"]
        }])
        
        header = not os.path.exists(self.log_file)
        df.to_csv(self.log_file, mode='a', index=False, header=header)

    def open_position(self, pos_type, price):
        self.state["position"] = pos_type
        self.state["entry_price"] = price
        self.state["entry_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if pos_type == 1:
            self.state["highest_price"] = price
        else:
            self.state["lowest_price"] = price
            
        self.save_state()
        self.log_trade(f"OPEN_{'LONG' if pos_type==1 else 'SHORT'}", price, 0, 0)

    def close_position(self, price, fee_points=0.5):
        pos_type = self.state["position"]
        if pos_type == 0: return 0, 0
        
        entry_price = self.state["entry_price"]
        
        if pos_type == 1:
            points = (price - entry_price) - fee_points
        else:
            points = (entry_price - price) - fee_points
            
        # 1 point = 100,000 VND (VN30F1M multiplier)
        profit_vnd = points * 100000
        self.state["balance"] += profit_vnd
        self.state["total_profit"] += profit_vnd
        
        # Reset state
        self.state["position"] = 0
        self.state["entry_price"] = 0.0
        self.state["entry_time"] = None
        
        self.save_state()
        self.log_trade(f"CLOSE_{'LONG' if pos_type==1 else 'SHORT'}", price, points, profit_vnd)
        return points, profit_vnd

    def update_trailing(self, current_high, current_low):
        if self.state["position"] == 1:
            self.state["highest_price"] = max(self.state["highest_price"], current_high)
        elif self.state["position"] == -1:
            self.state["lowest_price"] = min(self.state["lowest_price"], current_low)
        self.save_state()
