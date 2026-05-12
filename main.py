import os
import requests
import pandas as pd
import ta
import pytz
import numpy as np

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
# USER STORE
# ==========================================

user_data_store = {}

# ==========================================
# FOREX PAIRS
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
    "CAD/JPY",
    "EUR/AUD",
    "GBP/AUD",
    "EUR/CAD",
    "GBP/CAD"
]

# ==========================================
# GET MARKET DATA
# ==========================================

def get_market_data(symbol, interval):

    url = (
        f"https://api.twelvedata.com/time_series"
        f"?symbol={symbol}"
        f"&interval={interval}"
        f"&outputsize=200"
        f"&apikey={API_KEY}"
    )

    response = requests.get(url)

    data = response.json()

    if "values" not in data:
        raise Exception(data)

    return data["values"]

# ==========================================
# SUPPORT & RESISTANCE
# ==========================================

def calculate_support_resistance(df):

    support = df["low"].tail(20).min()

    resistance = df["high"].tail(20).max()

    return support, resistance

# ==========================================
# CANDLE PATTERN
# ==========================================

def detect_candle_pattern(df):

    latest = df.iloc[-1]

    body = abs(latest["close"] - latest["open"])

    candle_range = latest["high"] - latest["low"]

    if candle_range == 0:
        return "NONE"

    body_percent = body / candle_range

    # Strong bullish candle
    if (
        latest["close"] > latest["open"]
        and body_percent > 0.6
    ):
        return "BULLISH"

    # Strong bearish candle
    elif (
        latest["close"] < latest["open"]
        and body_percent > 0.6
    ):
        return "BEARISH"

    return "NEUTRAL"

# ==========================================
# TREND STRENGTH
# ==========================================

def trend_strength(ema9, ema21):

    diff = abs(ema9 - ema21)

    if diff > 0.0015:
        return "STRONG"

    elif diff > 0.0007:
        return "MEDIUM"

    return "WEAK"

# ==========================================
# ANALYZE MARKET
# ==========================================

def analyze(symbol, interval):

    raw_data = get_market_data(symbol, interval)

    df = pd.DataFrame(raw_data)

    numeric_cols = [
        "open",
        "high",
        "low",
        "close"
    ]

    for col in numeric_cols:
        df[col] = df[col].astype(float)

    # Reverse dataframe
    df = df.iloc[::-1]

    # ==========================================
    # INDICATORS
    # ==========================================

    # EMA
    df["ema9"] = ta.trend.ema_indicator(
        df["close"],
        window=9
    )

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

    # ADX Trend Strength
    adx = ta.trend.ADXIndicator(
        high=df["high"],
        low=df["low"],
        close=df["close"]
    )

    df["adx"] = adx.adx()

    latest = df.iloc[-1]

    # ==========================================
    # SUPPORT & RESISTANCE
    # ==========================================

    support, resistance = calculate_support_resistance(df)

    # ==========================================
    # CANDLE PATTERN
    # ==========================================

    candle = detect_candle_pattern(df)

    # ==========================================
    # SIGNAL LOGIC
    # ==========================================

    signal = "WAIT"

    confidence = 50

    reasons = []

    # CALL CONDITIONS
    bullish_conditions = [
        latest["ema9"] > latest["ema21"],
        latest["rsi"] > 50,
        latest["macd"] > latest["macd_signal"],
        candle == "BULLISH",
        latest["close"] > support,
        latest["adx"] > 20
    ]

    # PUT CONDITIONS
    bearish_conditions = [
        latest["ema9"] < latest["ema21"],
        latest["rsi"] < 50,
        latest["macd"] < latest["macd_signal"],
        candle == "BEARISH",
        latest["close"] < resistance,
        latest["adx"] > 20
    ]

    bullish_score = bullish_conditions.count(True)

    bearish_score = bearish_conditions.count(True)

    # CALL SIGNAL
    if bullish_score >= 5:

        signal = "CALL"

        confidence = min(95, bullish_score * 15)

        reasons.append("Bullish EMA Trend")
        reasons.append("RSI Momentum Up")
        reasons.append("MACD Bullish")
        reasons.append("Strong Candle")

    # PUT SIGNAL
    elif bearish_score >= 5:

        signal = "PUT"

        confidence = min(95, bearish_score * 15)

        reasons.append("Bearish EMA Trend")
        reasons.append("RSI Momentum Down")
        reasons.append("MACD Bearish")
        reasons.append("Strong Candle")

    # TREND QUALITY
    trend = trend_strength(
        latest["ema9"],
        latest["ema21"]
    )

    return {
        "pair": symbol,
        "timeframe": interval,
        "signal": signal,
        "confidence": confidence,
        "rsi": round(latest["rsi"], 2),
        "adx": round(latest["adx"], 2),
        "trend": trend,
        "candle": candle,
        "support": round(support, 5),
        "resistance": round(resistance, 5),
        "reasons": reasons
    }

# ==========================================
# SHOW PAIRS
# ==========================================

async def show_pairs(message):

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

    await message.reply_text(
        "📊 SELECT TRADING PAIR",
        reply_markup=reply_markup
    )

# ==========================================
# START COMMAND
# ==========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await show_pairs(update.message)

# ==========================================
# BUTTON HANDLER
# ==========================================

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    chat_id = query.message.chat_id

    data = query.data

    # ==========================================
    # SELECT PAIR
    # ==========================================

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

    # ==========================================
    # BACK BUTTON
    # ==========================================

    elif data == "back_pairs":

        await show_pairs(query.message)

    # ==========================================
    # TIMEFRAME
    # ==========================================

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

    # ==========================================
    # GET SIGNAL
    # ==========================================

    elif data == "get_signal":

        pair = user_data_store[chat_id]["pair"]

        timeframe = user_data_store[chat_id]["timeframe"]

        result = analyze(pair, timeframe)

        kigali = pytz.timezone("Africa/Kigali")

        now = datetime.now(kigali)

        # EXPIRE TIME
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

        # REASONS
        reasons = "\n".join(
            [f"✅ {r}" for r in result["reasons"]]
        )

        text = f"""
━━━━━━━━━━━━━━━
📊 ADVANCED VIP SIGNAL
━━━━━━━━━━━━━━━

💱 Pair: {result['pair']}

⏰ Entry Time: {entry_time}
🇷🇼 Kigali Time

⌛ Expire Time: {expire_time}

📈 Signal: {result['signal']} {signal_emoji}

🎯 Confidence: {result['confidence']}%

📊 RSI: {result['rsi']}

🔥 ADX Trend: {result['adx']}

📉 Trend Strength: {result['trend']}

🕯 Candle: {result['candle']}

🟢 Support: {result['support']}

🔴 Resistance: {result['resistance']}

━━━━━━━━━━━━━━━
📌 ANALYSIS
━━━━━━━━━━━━━━━

{reasons}

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
    CommandHandler("start", start)
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
        "status": "RUNNING",
        "bot": "ACTIVE"
        }
