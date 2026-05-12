import os
import requests
import pandas as pd
import ta
import pytz

from datetime import datetime, timedelta
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

# ==========================================
# ENV VARIABLES
# ==========================================

API_KEY = os.getenv("TWELVE_DATA_API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ==========================================
# FASTAPI
# ==========================================

app = FastAPI()

# ==========================================
# STORE USER DATA
# ==========================================

user_data_store = {}

# ==========================================
# AVAILABLE PAIRS
# ==========================================

PAIRS = [

    "EUR/USD",
    "GBP/USD",
    "USD/JPY",
    "AUD/USD",
    "USD/CAD",
    "EUR/JPY",
    "GBP/JPY",
    "EUR/GBP",
    "NZD/USD",
    "USD/CHF",
    "AUD/JPY",
    "CAD/JPY"

]

# ==========================================
# GET MARKET DATA
# ==========================================

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

# ==========================================
# ANALYZE MARKET
# ==========================================

def analyze(symbol, interval):

    df = pd.DataFrame(
        get_market_data(symbol, interval)
    )

    df["close"] = df["close"].astype(float)

    # Reverse dataframe
    df = df.iloc[::-1]

    # ==========================
    # INDICATORS
    # ==========================

    # EMA 9
    df["ema9"] = ta.trend.ema_indicator(
        df["close"],
        window=9
    )

    # EMA 21
    df["ema21"] = ta.trend.ema_indicator(
        df["close"],
        window=21
    )

    # RSI
    df["rsi"] = ta.momentum.rsi(
        df["close"],
        window=14
    )

    # MACD
    macd = ta.trend.MACD(df["close"])

    df["macd"] = macd.macd()

    df["macd_signal"] = macd.macd_signal()

    latest = df.iloc[-1]

    # ==================================
    # SIGNAL LOGIC
    # ==================================

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

        "pair": symbol,

        "timeframe": interval,

        "signal": signal,

        "confidence": confidence,

        "rsi": round(latest["rsi"], 2)

    }

# ==========================================
# START COMMAND
# ==========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = []

    row = []

    for i, pair in enumerate(PAIRS, start=1):

        row.append(

            InlineKeyboardButton(
                pair,
                callback_data=f"pair_{pair}"
            )

        )

        if i % 2 == 0:

            keyboard.append(row)

            row = []

    if row:

        keyboard.append(row)

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(

        "📊 SELECT TRADING PAIR",

        reply_markup=reply_markup

    )

# ==========================================
# HANDLE BUTTONS
# ==========================================

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    chat_id = query.message.chat_id

    data = query.data

    # ==================================
    # SELECT PAIR
    # ==================================

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

            ],

            [

                InlineKeyboardButton(
                    "⬅ BACK",
                    callback_data="back_pairs"
                )

            ]

        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.reply_text(

            f"✅ Pair Selected: {pair}\n\n⏰ Select Timeframe",

            reply_markup=reply_markup

        )

    # ==================================
    # BACK BUTTON
    # ==================================

    elif data == "back_pairs":

        keyboard = []

        row = []

        for i, pair in enumerate(PAIRS, start=1):

            row.append(

                InlineKeyboardButton(
                    pair,
                    callback_data=f"pair_{pair}"
                )

            )

            if i % 2 == 0:

                keyboard.append(row)

                row = []

        if row:

            keyboard.append(row)

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.reply_text(

            "📊 SELECT TRADING PAIR",

            reply_markup=reply_markup

        )

    # ==================================
    # SELECT TIMEFRAME
    # ==================================

    elif data.startswith("tf_"):

        timeframe = data.replace("tf_", "")

        user_data_store[chat_id]["timeframe"] = timeframe

        keyboard = [

            [

                InlineKeyboardButton(
                    "📈 GET SIGNAL",
                    callback_data="get_signal"
                )

            ],

            [

                InlineKeyboardButton(
                    "⬅ BACK",
                    callback_data="back_pairs"
                )

            ]

        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.reply_text(

            f"✅ Timeframe Selected: {timeframe}",

            reply_markup=reply_markup

        )

    # ==================================
    # GET SIGNAL
    # ==================================

    elif data == "get_signal":

        pair = user_data_store[chat_id]["pair"]

        timeframe = user_data_store[chat_id]["timeframe"]

        result = analyze(pair, timeframe)

        # Rwanda Time
        kigali = pytz.timezone("Africa/Kigali")

        now = datetime.now(kigali)

        # Expire Time
        if timeframe == "1min":

            expire = now + timedelta(minutes=1)

        elif timeframe == "3min":

            expire = now + timedelta(minutes=3)

        else:

            expire = now + timedelta(minutes=5)

        entry_time = now.strftime("%I:%M:%S %p")

        expire_time = expire.strftime("%I:%M:%S %p")

        # SIGNAL EMOJI
        signal_emoji = "⏸"

        if result["signal"] == "CALL":

            signal_emoji = "⬆️"

        elif result["signal"] == "PUT":

            signal_emoji = "⬇️"

        # MESSAGE
        text = f"""
━━━━━━━━━━━━━━━
📊 BINARY VIP SIGNAL
━━━━━━━━━━━━━━━

💱 Pair: {result['pair']}

⏰ Entry Time: {entry_time}
🇷🇼 Kigali Time

⌛ Expire Time: {expire_time}

📈 Signal: {result['signal']} {signal_emoji}

🎯 Confidence: {result['confidence']}%

📊 RSI: {result['rsi']}

━━━━━━━━━━━━━━━
🔥 Trade Smart
━━━━━━━━━━━━━━━
"""

        keyboard = [

            [

                InlineKeyboardButton(
                    "🔄 NEW SIGNAL",
                    callback_data="back_pairs"
                )

            ]

        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.reply_text(

            text,

            reply_markup=reply_markup

        )

# ==========================================
# TELEGRAM BOT
# ==========================================

telegram_app = Application.builder().token(BOT_TOKEN).build()

telegram_app.add_handler(

    CommandHandler(
        "start",
        start
    )

)

telegram_app.add_handler(

    CallbackQueryHandler(button_click)

)

# ==========================================
# FASTAPI STARTUP
# ==========================================

@app.on_event("startup")
async def startup():

    await telegram_app.initialize()

    await telegram_app.start()

    await telegram_app.updater.start_polling()

# ==========================================
# HOME ROUTE
# ==========================================

@app.get("/")
def home():

    return {

        "status": "RUNNING"

    }
