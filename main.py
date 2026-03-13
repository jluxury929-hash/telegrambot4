import os
import sys
import subprocess
import logging
import requests
from decimal import Decimal, getcontext

# --- 1. AUTO-DEPENDENCY & RESTART ---
try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import OrderArgs, OrderType
    from py_clob_client.order_builder.constants import BUY
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "py-clob-client", "requests", "python-telegram-bot", "web3"])
    os.execv(sys.executable, ['python'] + sys.argv)

from web3 import Web3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters

# --- 2. CONFIGURATION ---
getcontext().prec = 10
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = os.getenv("TELEGRAM_TOKEN")
P_KEY = os.getenv("PRIVATE_KEY")
WALLET = os.getenv("USER_WALLET_ADDRESS")

# --- 3. GHOST PROCESS CLEANER ---
def kill_existing_sessions(token):
    url = f"https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=True"
    try: requests.get(url, timeout=5)
    except: pass

# --- 4. IMPROVED LIVE ENGINE ---

class HydraEngine:
    def __init__(self):
        self.client = ClobClient("https://clob.polymarket.com", key=P_KEY, chain_id=137)
        try:
            creds = self.client.create_or_derive_api_creds()
            self.client.set_api_creds(creds)
        except: pass

    async def get_instant_market(self):
        """Iterates through top events to GUARANTEE a market is found"""
        try:
            # Fetch top 20 events to ensure we have plenty of options
            url = "https://gamma-api.polymarket.com/events?active=true&closed=false&order=volume_24hr&ascending=false&limit=20"
            r = requests.get(url, timeout=10).json()
            
            for event in r:
                markets = event.get('markets', [])
                if not markets:
                    continue
                
                market = markets[0]
                # Ensure the market has a valid CLOB ID and price
                clob_ids = market.get('clobTokenIds')
                if clob_ids and len(clob_ids) > 0:
                    price = market.get('bestYesBid') or market.get('lastTradePrice') or 0.50
                    return {
                        "id": clob_ids[0],
                        "name": event.get('title', 'Unknown Market'),
                        "price": float(price)
                    }
            return None
        except Exception as e:
            logging.error(f"Harvester Failure: {e}")
            return None

    async def execute_trade(self, token_id, price, amount_usd):
        try:
            shares = float(amount_usd) / price
            order = OrderArgs(price=price, size=round(shares, 2), side=BUY, token_id=token_id)
            signed = self.client.create_order(order)
            resp = self.client.post_order(signed, OrderType.GTC)
            return True, resp.get("orderID", "Success")
        except Exception as e:
            return False, str(e)

# --- 5. TELEGRAM UI ---

def get_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Set Stake Amount", callback_data='set_amt')],
        [InlineKeyboardButton("🚀 EXECUTE INSTANT BET", callback_data='exec')],
        [InlineKeyboardButton("🏠 Refresh Home", callback_data='home')]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amt = context.user_data.get('stake', 100)
    text = (
        "⚡ **HYDRA TERMINAL: AGGRESSIVE HARVEST**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 **Current Stake:** `${amt} USDC`\n"
        "🟢 **Status:** Scanning High-Volume Events..."
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=get_kb(), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=get_kb(), parse_mode='Markdown')

async def button_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'home': 
        await start(update, context)
    elif query.data == 'set_amt':
        await query.edit_message_text("⌨️ **Enter USDC stake amount:**")
    elif query.data == 'exec':
        await query.edit_message_text("📡 **Deep Scanning Polymarket...**")
        h = HydraEngine()
        m = await h.get_instant_market()
        
        if m:
            stake = context.user_data.get('stake', 100)
            await query.edit_message_text(f"🎯 **Market Found:**\n`{m['name']}`\n\n🚀 **Broadcasting Trade...**")
            ok, res = await h.execute_trade(m['id'], m['price'], stake)
            await query.edit_message_text(f"{'✅ SUCCESS' if ok else '⚠️ FAILED'}\nID/Error: `{res}`", reply_markup=get_kb())
        else:
            await query.edit_message_text("❌ ERROR: No active high-volume markets found. Check API connectivity.", reply_markup=get_kb())

async def catch_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.isdigit():
        context.user_data['stake'] = int(update.message.text)
        await update.message.reply_text(f"✅ Stake set to **${update.message.text}**", reply_markup=get_kb())

# --- 6. LAUNCH ---

if __name__ == '__main__':
    if not TOKEN: sys.exit("❌ TOKEN missing")
    kill_existing_sessions(TOKEN)
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_router))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), catch_text))
    print("🚀 Hydra Deep-Scanner Live.")
    app.run_polling(drop_pending_updates=True)
