import time
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich import box

from src.data_fetcher import fetch_live_data
from src.logic import compute_indicators, get_latest_signal
from src.paper_broker import PaperBroker

console = Console()

class LiveEngine:
    def __init__(self, config):
        self.cfg = config
        pt_cfg = config["paper_trading"]
        self.broker = PaperBroker(
            state_file=pt_cfg["state_file"],
            log_file=pt_cfg["log_file"],
            initial_capital=pt_cfg["initial_capital"]
        )
        self.strategy_params = config["strategy"]
        self.symbol = config["data"]["symbol"]
        self.source = config["data"]["source"]
        self.interval = config["data"]["interval"]
        self.poll_interval = pt_cfg["poll_interval_seconds"]

    def is_market_open(self):
        now = datetime.now()
        if now.weekday() >= 5: return False
        current_time = now.time()
        morning_start = datetime.strptime("08:44", "%H:%M").time()
        morning_end   = datetime.strptime("11:31", "%H:%M").time()
        afternoon_start = datetime.strptime("12:59", "%H:%M").time()
        afternoon_end   = datetime.strptime("14:46", "%H:%M").time()
        return (morning_start <= current_time <= morning_end) or \
               (afternoon_start <= current_time <= afternoon_end)

    def generate_dashboard(self, status, last_price, stats):
        table = Table(box=box.ROUNDED, show_header=False, expand=True)
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("MARKET", f"[bold green]{self.symbol}[/] | [bold yellow]{last_price:,.2f}[/]")
        table.add_row("TIME", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        table.add_row("STATUS", f"[bold white]{status}[/]")
        table.add_section()

        pos = self.broker.state["position"]
        pos_str = "[bold white]NONE[/]"
        if pos == 1: pos_str = "[bold green]LONG[/]"
        elif pos == -1: pos_str = "[bold red]SHORT[/]"
        
        table.add_row("POSITION", pos_str)
        table.add_row("BALANCE", f"{self.broker.state['balance']:,.0f} VND")
        table.add_row("PROFIT", f"{self.broker.state['total_profit']:,.0f} VND")
        table.add_section()

        if stats:
            macd_color = "green" if stats['macd'] > stats['signal'] else "red"
            table.add_row("MACD / SIG", f"[{macd_color}]{stats['macd']:.2f} / {stats['signal']:.2f}[/]")
            table.add_row("RSI", f"{stats['rsi']:.2f}")
            table.add_row("TREND", f"{stats['trend']:.2f}")

        return Panel(table, title="[bold magenta]VN30F1M LIVE DASHBOARD[/]", subtitle="Press Ctrl+C to Exit")

    def run(self):
        console.clear()
        console.print("[bold green]Starting Unified Live Engine...[/]")
        
        with Live(auto_refresh=False) as live:
            while True:
                try:
                    if not self.is_market_open():
                        live.update(self.generate_dashboard("MARKET CLOSED", 0, None), refresh=True)
                        time.sleep(60); continue

                    df = fetch_live_data(self.symbol, self.source, self.interval)
                    if df is None:
                        time.sleep(10); continue

                    df_ind = compute_indicators(df, self.strategy_params)
                    signal, stats = get_latest_signal(df_ind, self.strategy_params)
                    last_price = df.iloc[-1]["Close"]
                    
                    # 1. Update Trailing Stop
                    if self.broker.state["position"] != 0:
                        self.broker.update_trailing(df.iloc[-1]["High"], df.iloc[-1]["Low"])
                        self.check_exit_conditions(last_price)

                    # 2. Check Entry Signal
                    elif signal != 0:
                        self.broker.open_position(signal, last_price)
                        console.print(f"[bold cyan][{datetime.now().strftime('%H:%M:%S')}] ENTRY: {'LONG' if signal==1 else 'SHORT'} at {last_price}[/]")

                    live.update(self.generate_dashboard("LIVE TRADING", last_price, stats), refresh=True)
                    time.sleep(self.poll_interval)

                except KeyboardInterrupt: break
                except Exception as e:
                    console.print(f"[red]Error: {e}[/]"); time.sleep(10)

    def check_exit_conditions(self, current_price):
        state = self.broker.state
        entry_price = state["entry_price"]
        pos = state["position"]
        params = self.strategy_params
        
        should_exit = False
        reason = ""

        if pos == 1:
            if current_price - entry_price >= params["take_profit"]:
                should_exit = True; reason = "TAKE_PROFIT"
            elif entry_price - current_price >= params["cut_loss"]:
                should_exit = True; reason = "STOP_LOSS"
            elif state["highest_price"] - entry_price >= params["trailing_activation"]:
                if current_price <= state["highest_price"] - params["trailing_step"]:
                    should_exit = True; reason = "TRAILING_STOP"
        
        elif pos == -1:
            if entry_price - current_price >= params["take_profit"]:
                should_exit = True; reason = "TAKE_PROFIT"
            elif current_price - entry_price >= params["cut_loss"]:
                should_exit = True; reason = "STOP_LOSS"
            elif entry_price - state["lowest_price"] >= params["trailing_activation"]:
                if current_price >= state["lowest_price"] + params["trailing_step"]:
                    should_exit = True; reason = "TRAILING_STOP"

        if should_exit:
            pts, profit = self.broker.close_position(current_price, params["fee_per_trade"])
            console.print(f"[bold yellow][{datetime.now().strftime('%H:%M:%S')}] EXIT: {reason} at {current_price} | Profit: {profit:,.0f} VND[/]")
