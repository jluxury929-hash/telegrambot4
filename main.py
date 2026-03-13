import os
import sys
import subprocess
import logging
from decimal import Decimal, getcontext

# --- 1. DEPENDENCY AUTO-INSTALL ---
try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import OrderArgs, OrderType
    from py_clob_client.order_builder.constants import BUY
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "py-clob-client"])
    os.execv(sys.executable, ['python'] + sys.argv)

from web3 import Web3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters

# --- 2. CONFIG ---
getcontext().prec = 10
logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("TELEGRAM_TOKEN")
RPC_URL = os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com")
WALLET = os.getenv("USER_WALLET_ADDRESS")
# CRITICAL: This is the key that signs the actual bets
P_KEY = os.getenv("PRIVATE_KEY") 

w3 = Web3(Web3.HTTPProvider(RPC_URL))

# --- 3. LIVE EXECUTION ENGINE ---

class HydraLiveExecutor:
    def __init__(self):
        # Connects to the real Polymarket Order Book
        self.client = ClobClient("https://clob.polymarket.com", key=P_KEY, chain_id=137)
        try:
            # First time setup for API credentials
            creds = self.client.create_or_derive_api_creds()
            self.client.set_api_creds(creds)
        except Exception as e:
            logging.error(f"API Credential Error: {e}")

    async def place_real_arb(self, token_id, price, amount_usd):
        """Signs and broadcasts a real BUY order to the blockchain"""
        try:
            # Calculate shares based on price (e.g., $100 / 0.50 = 200 shares)
            shares = float(amount_usd) / float(price)
            
            order_args = OrderArgs(
                price=float(price),
                size=round(shares, 2),
                side=BUY,
                token_id=token_id
            )
            
            signed_order = self.client.create_order(order_args)
            response = self.client.post_order(signed_order, OrderType.GTC)
            
            if response.get("success") or response.get("orderID"):
                return True, response.get("orderID")
            return False, response.get("error", "Unknown Exchange Error")
        except Exception as e:
            return False, str(e)

# --- 4. UI & LOGIC ---

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Set Stake Amount", callback_data='set_amt')],
        [InlineKeyboardButton("🔥 EXECUTE REAL SCAN & BET", callback_data='execute_live')],
        [InlineKeyboardButton("🏠 Home", callback_data='home')]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stake = context.user_data.get('bet_amount', "100")
    text = (
        "🧨 **HYDRA LIVE EXECUTION TERMINAL**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🛠️ **Wallet:** `{WALLET[:8]}...`\n"
        f"💵 **Current Stake:** `${stake} USDC`\n"
        "⚠️ **MODE:** LIVE TRADING ACTIVE"
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=main_menu(), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=main_menu(), parse_mode='Markdown')

async def manager(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'home':
        await start(update, context)
    
    elif query.data == 'set_amt':
        await query.edit_message_text("⌨️ **Type the USDC amount you want to bet:**", parse_mode='Markdown')

    elif query.data == 'execute_live':
        if not P_KEY:
            await query.edit_message_text("❌ **FAILED:** No Private Key found in environment variables.")
            return

        stake = context.user_data.get('bet_amount', 100)
        await query.edit_message_text(f"📡 **Connecting to Polymarket CLOB...**\nTargeting `${stake}` stake.")

        # LIVE INTEGRATION: 
        # In a real scenario, we'd fetch the best market ID here. 
        # For this example, we'll use a specific Market ID (e.g. 'Will BTC be > $80k?')
        # You find these IDs at https://gamma-api.polymarket.com/markets
        TARGET_TOKEN_ID = "74495204439160536766736630013915017215431602161494489813203672016553820524419" # Example ID
        TARGET_PRICE = 0.52 # The price we are willing to pay (limit price)

        executor = HydraLiveExecutor()
        success, result = await executor.place_real_arb(TARGET_TOKEN_ID, TARGET_PRICE, stake)

        if success:
            msg = f"🚀 **SUCCESS: BET PLACED!**\n━━━━━━━━━━━━\n🆔 Order ID: `{result}`\n💰 Stake: `${stake}`"
        else:
            msg = f"⚠️ **BET FAILED**\n━━━━━━━━━━━━\nError: `{result}`"
        
        await query.edit_message_text(msg, reply_markup=main_menu(), parse_mode='Markdown')

async def text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.isdigit():
        context.user_data['bet_amount'] = update.message.text
        await update.message.reply_text(f"✅ Stake set to **${update.message.text}**", reply_markup=main_menu())

# --- 5. RUN ---

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(manager))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), text_input))
    print("🚀 Hydra LIVE is broadcasting...")
    app.run_polling()
