import os
import requests
import pandas as pd
import ta

from fastapi import FastAPI
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

# ENV VARIABLES
API_KEY = os.getenv("TWELVE_DATA_API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")

app = FastAPI()

# USER SETTINGS
user_data_store = {}


# =========================
# MARKET ANALYSIS
# =========================

def get_market_data(symbol, interval):

    url = (
        f"https://api.twelvedata.com/time_series"
        f"?symbol={symbol}"
        f"&interval={interval}"
        f"&outputsize=100"
        f"&apikey={API_KEY}"
    )

    response = requests.get(url)

    data = response.json()

    if "values" not in data:
        raise Exception(data)

    return data["values"]


def analyze(symbol, interval):

    df = pd.DataFrame(get_market_data(symbol, interval))

    df["close"] = df["close"].astype(float)

    df = df.iloc[::-1]

    # Indicators
    df["ema9"] = ta.trend.ema_indicator(
        df["close"],
        window=9
    )

    df["ema21"] = ta.trend.ema_indicator(
        df["close"],
        window=21
    )

    df["rsi"] = ta.momentum.rsi(
        df["close"],
        window=14
    )

    macd = ta.trend.MACD(df["close"])

    df["macd"] = macd.macd()

    df["macd_signal"] = macd.macd_signal()

    latest = df.iloc[-1]

    signal = "WAIT"

    confidence = 50

    # CALL
    if (
        latest["ema9"] > latest["ema21"]
        and latest["rsi"] > 50
        and latest["macd"] > latest["macd_signal"]
    ):

        signal = "CALL"
        confidence = 85

    # PUT
    elif (
        latest["ema9"] < latest["ema21"]
        and latest["rsi"] < 50
        and latest["macd"] < latest["macd_signal"]
    ):

        signal = "PUT"
        confidence = 85

    return {
        "pair": symbol,
        "timeframe": interval,
        "signal": signal,
        "confidence": confidence,
        "rsi": round(latest["rsi"], 2)
    }


# =========================
# TELEGRAM BOT
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = [

        [
            InlineKeyboardButton(
                "EUR/USD",
                callback_data="pair_EUR/USD"
            ),

            InlineKeyboardButton(
                "GBP/USD",
                callback_data="pair_GBP/USD"
            )
        ],

        [
            InlineKeyboardButton(
                "USD/JPY",
                callback_data="pair_USD/JPY"
            )
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "📊 Select Trading Pair",
        reply_markup=reply_markup
    )


async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    chat_id = query.message.chat_id

    data = query.data

    # SELECT PAIR
    if data.startswith("pair_"):

        pair = data.replace("pair_", "")

        user_data_store[chat_id] = {
            "pair": pair
        }

        keyboard = [

            [
                InlineKeyboardButton(
                    "1m",
                    callback_data="tf_1min"
                ),

                InlineKeyboardButton(
                    "3m",
                    callback_data="tf_3min"
                ),

                InlineKeyboardButton(
                    "5m",
                    callback_data="tf_5min"
                )
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.reply_text(
            f"✅ Pair Selected: {pair}\n\nSelect Timeframe",
            reply_markup=reply_markup
        )

    # SELECT TIMEFRAME
    elif data.startswith("tf_"):

        timeframe = data.replace("tf_", "")

        user_data_store[chat_id]["timeframe"] = timeframe

        keyboard = [

            [
                InlineKeyboardButton(
                    "📈 GET SIGNAL",
                    callback_data="get_signal"
                )
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.reply_text(
            f"✅ Timeframe Selected: {timeframe}",
            reply_markup=reply_markup
        )

    # GET SIGNAL
    elif data == "get_signal":

        pair = user_data_store[chat_id]["pair"]

        timeframe = user_data_store[chat_id]["timeframe"]

        result = analyze(pair, timeframe)

        text = f"""
📊 BINARY SIGNAL

💱 Pair: {result['pair']}

⏱ Timeframe: {result['timeframe']}

📈 Signal: {result['signal']}

🎯 Confidence: {result['confidence']}%

📊 RSI: {result['rsi']}
"""

        await query.message.reply_text(text)


# =========================
# RUN BOT
# =========================

telegram_app = Application.builder().token(BOT_TOKEN).build()

telegram_app.add_handler(
    CommandHandler("start", start)
)

telegram_app.add_handler(
    CallbackQueryHandler(button_click)
)


@app.on_event("startup")
async def startup():

    await telegram_app.initialize()

    await telegram_app.start()

    await telegram_app.updater.start_polling()


@app.get("/")
def home():

    return {
        "status": "RUNNING"
    }
