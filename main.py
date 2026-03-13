import os
import sys
import subprocess
import logging
import requests
import time
from decimal import Decimal, getcontext

# --- 1. DEPENDENCY CHECK ---
try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import OrderArgs, OrderType
    from py_clob_client.order_builder.constants import BUY
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "py-clob-client", "requests", "python-telegram-bot", "web3"])
    os.execv(sys.executable, ['python'] + sys.argv)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler

# --- 2. CONFIG ---
getcontext().prec = 10
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = os.getenv("TELEGRAM_TOKEN")
P_KEY = os.getenv("PRIVATE_KEY")
WALLET = os.getenv("USER_WALLET_ADDRESS")

# --- 3. LIVE ENGINE ---
class HydraEngine:
    def __init__(self):
        self.client = None
        if P_KEY:
            self.client = ClobClient("https://clob.polymarket.com", key=P_KEY, chain_id=137)
            try:
                creds = self.client.create_or_derive_api_creds()
                self.client.set_api_creds(creds)
            except: pass

    async def harvest_live_bets(self):
        try:
            url = "https://gamma-api.polymarket.com/events?active=true&closed=false&order=volume_24hr&ascending=false&limit=15"
            r = requests.get(url, timeout=10).json()
            valid_markets = []
            for event in r:
                markets = event.get('markets', [])
                for m in markets:
                    clob_ids = m.get('clobTokenIds')
                    if clob_ids:
                        price = m.get('bestYesBid') or m.get('lastTradePrice') or 0.50
                        valid_markets.append({
                            "id": clob_ids[0],
                            "name": event.get('title'),
                            "price": float(price)
                        })
            return valid_markets
        except Exception as e:
            logging.error(f"Scanner Error: {e}")
            return []

# --- 4. UI ---
def get_main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Deep Scan Markets", callback_data='scan')],
        [InlineKeyboardButton("🏦 Aave Credit", callback_data='credit')],
        [InlineKeyboardButton("🛑 Emergency Stop", callback_data='stop')]
    ])

async def post_init(application):
    await application.bot.set_my_commands([BotCommand("start", "Launch Hydra")])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "🛡️ **HYDRA TERMINAL V2.5**\n━━━━━━━━━━━━\n🟢 **Status:** Exclusive Link Established"
    if update.message:
        await update.message.reply_text(msg, reply_markup=get_main_menu_keyboard(), parse_mode='Markdown')
    else:
        await update.callback_query.edit_message_text(msg, reply_markup=get_main_menu_keyboard(), parse_mode='Markdown')

async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'scan':
        await query.edit_message_text("📡 **SCANNING POLYMARKET...**")
        engine = HydraEngine()
        markets = await engine.harvest_live_bets()
        if markets:
            report = "✅ **OPPORTUNITIES FOUND**\n━━━━━━━━━━━━\n"
            for m in markets[:5]:
                report += f"🎯 `{m['name'][:35]}...`\n💰 Price: `${m['price']}`\n\n"
            await query.edit_message_text(report, reply_markup=get_main_menu_keyboard(), parse_mode='Markdown')
        else:
            await query.edit_message_text("❌ No liquid markets found. Retry?", reply_markup=get_main_menu_keyboard())

# --- 5. EXECUTION (The Conflict-Killer) ---
if __name__ == '__main__':
    if not TOKEN:
        sys.exit("❌ TOKEN NOT FOUND")

    print("🧹 Clearing previous sessions (Anti-Conflict)...")
    # Tell Telegram to drop all connections and ignore past messages
    requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=True")
    
    # Wait for the API to settle
    time.sleep(5)
    
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handler))

    print("🚀 Hydra is online. If you still see 409, REVOKE your token in BotFather.")
    app.run_polling(drop_pending_updates=True)
