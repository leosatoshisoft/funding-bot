"""
Launcher: corre el bot y el dashboard en paralelo
"""
import os
import threading
import subprocess
import sys

def run_bot():
    subprocess.run([sys.executable, "bot.py"])

def run_dashboard():
    subprocess.run([sys.executable, "dashboard.py"])

if __name__ == "__main__":
    os.makedirs("logs", exist_ok=True)
    os.makedirs("data", exist_ok=True)

    t1 = threading.Thread(target=run_bot, daemon=True)
    t2 = threading.Thread(target=run_dashboard, daemon=True)

    t1.start()
    t2.start()

    t1.join()
    t2.join()
