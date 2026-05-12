import os
import requests
import pandas as pd
import ta

from fastapi import FastAPI
from telegram import Bot

# Railway Variables
API_KEY = os.getenv("TWELVE_DATA_API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# Fixed Pair
SYMBOL = "EUR/USD"
INTERVAL = "1min"

bot = Bot(token=BOT_TOKEN)

app = FastAPI()

last_signal = None


def get_market_data():

    url = (
        f"https://api.twelvedata.com/time_series"
        f"?symbol={SYMBOL}"
        f"&interval={INTERVAL}"
        f"&outputsize=100"
        f"&apikey={API_KEY}"
    )

    response = requests.get(url)

    data = response.json()

    if "values" not in data:
        raise Exception(data)

    return data["values"]


def analyze():

    df = pd.DataFrame(get_market_data())

    df["close"] = df["close"].astype(float)

    df = df.iloc[::-1]

    # Indicators
    df["ema9"] = ta.trend.ema_indicator(df["close"], window=9)

    df["ema21"] = ta.trend.ema_indicator(df["close"], window=21)

    df["rsi"] = ta.momentum.rsi(df["close"], window=14)

    macd = ta.trend.MACD(df["close"])

    df["macd"] = macd.macd()

    df["macd_signal"] = macd.macd_signal()

    latest = df.iloc[-1]

    signal = "WAIT"

    confidence = 50

    # CALL SIGNAL
    if (
        latest["ema9"] > latest["ema21"]
        and latest["rsi"] > 50
        and latest["macd"] > latest["macd_signal"]
    ):

        signal = "CALL"

        confidence = 85

    # PUT SIGNAL
    elif (
        latest["ema9"] < latest["ema21"]
        and latest["rsi"] < 50
        and latest["macd"] < latest["macd_signal"]
    ):

        signal = "PUT"

        confidence = 85

    return {
        "pair": SYMBOL,
        "signal": signal,
        "confidence": confidence,
        "rsi": round(latest["rsi"], 2),
    }


@app.get("/")
def home():

    return {
        "status": "RUNNING"
    }


@app.get("/signal")
def signal():

    global last_signal

    try:

        result = analyze()

        current_signal = result["signal"]

        # Prevent duplicate alerts
        if (
            current_signal != "WAIT"
            and current_signal != last_signal
        ):

            text = f"""
📊 Binary Signal

Pair: {result['pair']}

Signal: {result['signal']}

Confidence: {result['confidence']}%

RSI: {result['rsi']}
"""

            bot.send_message(
                chat_id=CHAT_ID,
                text=text
            )

            last_signal = current_signal

        return result

    except Exception as e:

        return {
            "error": str(e)
}
