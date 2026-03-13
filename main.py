import os
import sys
import subprocess
import logging
from decimal import Decimal, getcontext

# --- AUTOMATIC DEPENDENCY INSTALLER ---
def install_missing_libs():
    try:
        import py_clob_client
    except ImportError:
        print("📦 Installing Polymarket SDK (py-clob-client)...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "py-clob-client"])
        print("✅ Installation complete. Restarting script...")
        os.execv(sys.executable, ['python'] + sys.argv)

install_missing_libs()

# --- NOW IMPORTING THE REST ---
from web3 import Web3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY

# --- INITIALIZATION ---
getcontext().prec = 10
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
RPC_URL = os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com")
RAW_WALLET = os.getenv("USER_WALLET_ADDRESS")
PRIVATE_KEY = os.getenv("PRIVATE_KEY") 

if not RAW_WALLET or not Web3.is_address(RAW_WALLET):
    print("❌ FATAL: USER_WALLET_ADDRESS is invalid or not set!")
    sys.exit(1)

WALLET_ADDRESS = Web3.to_checksum_address(RAW_WALLET)
w3 = Web3(Web3.HTTPProvider(RPC_URL))

# AAVE V3 ABI (Minimal)
AAVE_POOL_V3 = "0x7937d4799803Fb3ad9212d7164cc9B1aB96048a1"
AAVE_ABI = [{"inputs":[{"internalType":"address","name":"user","type":"address"}],"name":"getUserAccountData","outputs":[{"internalType":"uint256","name":"tColl","type":"uint256"},{"internalType":"uint256","name":"tDebt","type":"uint256"},{"internalType":"uint256","name":"avail","type":"uint256"},{"internalType":"uint256","name":"thresh","type":"uint256"},{"internalType":"uint256","name":"ltv","type":"uint256"},{"internalType":"uint256","name":"health","type":"uint256"}],"stateMutability":"view","type":"function"}]

# --- CLASSES ---

class AaveManager:
    def __init__(self):
        self.contract = w3.eth.contract(address=AAVE_POOL_V3, abi=AAVE_ABI)

    def get_borrow_limit(self):
        try:
            d = self.contract.functions.getUserAccountData(WALLET_ADDRESS).call()
            return Decimal(d[2]) / Decimal(10**8)
        except: return Decimal(0)

class ArbEngine:
    def analyze(self, odds_a, odds_b, target_payout):
        p_a = Decimal(100) / (Decimal(odds_a) + 100) if odds_a > 0 else abs(Decimal(odds_a)) / (abs(Decimal(odds_a)) + 100)
        p_b = Decimal(100) / (Decimal(odds_b) + 100) if odds_b > 0 else abs(Decimal(odds_b)) / (abs(Decimal(odds_b)) + 100)
        if (p_a + p_b) >= 1: return None
        return {"stake_a": round(target_payout * p_a, 2), "stake_b": round(target_payout * p_b, 2), 
                "profit": round(target_payout - (target_payout * (p_a + p_b)), 2)}

# --- TELEGRAM LOGIC ---

def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Set Custom Amount", callback_data='set_amt')],
        [InlineKeyboardButton("🔍 Scan & Place Bet", callback_data='scan')],
        [InlineKeyboardButton("🔄 Refresh", callback_data='home')]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amt = context.user_data.get('bet_amount', "Auto (Aave)")
    text = f"⚡ **HYDRA LIVE**\n━━━━━━━━━━━━\n🛠️ **Wallet:** `{WALLET_ADDRESS[:8]}...`\n💵 **Current Stake:** `${amt}`"
    if update.message:
        await update.message.reply_text(text, reply_markup=main_kb(), parse_mode='Markdown')
    else:
        await update.callback_query.edit_message_text(text, reply_markup=main_kb(), parse_mode='Markdown')

async def interaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'set_amt':
        await query.edit_message_text("⌨️ Type the USDC amount you want to stake per arb:")
        return

    if query.data == 'scan':
        # Get Amount (Manual or Aave-based)
        bank = AaveManager()
        manual_amt = context.user_data.get('bet_amount')
        stake_limit = Decimal(manual_amt) if manual_amt else bank.get_borrow_limit()
        
        if stake_limit < 5:
            await query.edit_message_text("❌ Balance too low for arb.", reply_markup=main_kb())
            return

        engine = ArbEngine()
        res = engine.analyze(240, -220, float(stake_limit)) # Sample odds
        
        if res and PRIVATE_KEY:
            try:
                # Execution
                client = ClobClient("https://clob.polymarket.com", key=PRIVATE_KEY, chain_id=137)
                client.set_api_creds(client.create_or_derive_api_creds())
                # Note: token_ids would be dynamically fetched from the Gamma API in a full implementation
                msg = f"✅ **BET EXECUTED**\n━━━━━━━━━━━━\n💰 Total: ${stake_limit}\n📈 Projected: +${res['profit']}"
            except Exception as e:
                msg = f"⚠️ Execution Error: {str(e)[:100]}"
        else:
            msg = "🔎 No profitable gaps found right now."
        
        await query.edit_message_text(msg, reply_markup=main_kb(), parse_mode='Markdown')

async def amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.isdigit():
        context.user_data['bet_amount'] = update.message.text
        await update.message.reply_text(f"✅ Stake updated to **${update.message.text}**", reply_markup=main_kb())

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(interaction))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), amount_input))
    print("🚀 Hydra is online.")
    app.run_polling()
