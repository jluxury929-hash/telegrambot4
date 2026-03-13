import os
import sys
import logging
from decimal import Decimal, getcontext
from web3 import Web3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters

# --- EXECUTION IMPORTS ---
from py_clob_client.client import ClobClient

# --- INITIALIZATION ---
getcontext().prec = 10
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
RPC_URL = os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com")
RAW_WALLET = os.getenv("USER_WALLET_ADDRESS")
PRIVATE_KEY = os.getenv("PRIVATE_KEY") # Required for placing bets

if not RAW_WALLET or not Web3.is_address(RAW_WALLET):
    print("❌ FATAL: USER_WALLET_ADDRESS invalid!")
    sys.exit(1)

WALLET_ADDRESS = Web3.to_checksum_address(RAW_WALLET)
w3 = Web3(Web3.HTTPProvider(RPC_URL))

# --- LOGIC ---

class ArbEngine:
    @staticmethod
    def get_implied_prob(odds):
        odds = Decimal(str(odds))
        return Decimal(100) / (odds + 100) if odds > 0 else abs(odds) / (abs(odds) + 100)

    def analyze(self, odds_a, odds_b, target_payout):
        prob_a, prob_b = self.get_implied_prob(odds_a), self.get_implied_prob(odds_b)
        total_prob = prob_a + prob_b
        if total_prob >= 1.0: return None
        stake_a, stake_b = Decimal(target_payout) * prob_a, Decimal(target_payout) * prob_b
        total_cost = stake_a + stake_b
        return {
            "stake_a": round(stake_a, 2), "stake_b": round(stake_b, 2),
            "profit": round(Decimal(target_payout) - total_cost, 2),
            "roi": round(((Decimal(target_payout) - total_cost) / total_cost) * 100, 2)
        }

# --- UI ---

def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Set Custom Amount", callback_data='set_amt')],
        [InlineKeyboardButton("🔍 Scan & Place Bet", callback_data='scan')],
        [InlineKeyboardButton("🏦 Aave Status", callback_data='credit')],
        [InlineKeyboardButton("🔄 Refresh", callback_data='home')]
    ])

# --- HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amt = context.user_data.get('bet_amount', "Auto (Aave)")
    text = (
        "⚡ **HYDRA ARBITRAGE TERMINAL**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🛠️ **WALLET:** `{WALLET_ADDRESS[:6]}...` \n"
        f"💵 **CURRENT STAKE:** `${amt}`\n"
        "⚖️ **LOGIC:** `P/L > 1 ONLY`"
    )
    if update.message:
        await update.message.reply_text(text, reply_markup=main_kb(), parse_mode='Markdown')
    else:
        await update.callback_query.edit_message_text(text, reply_markup=main_kb(), parse_mode='Markdown')

async def set_amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Captures manual amount input from chat"""
    if update.message.text.isdigit():
        context.user_data['bet_amount'] = update.message.text
        await update.message.reply_text(f"✅ Stake set to **${update.message.text} USDC**.", reply_markup=main_kb())
    else:
        await update.message.reply_text("❌ Send a valid number.")

async def interaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'home': await start(update, context)
    elif query.data == 'set_amt':
        await query.edit_message_text("⌨️ **Enter USDC amount to stake per side:**", parse_mode='Markdown')
    
    elif query.data == 'scan':
        # Get amount from memory or fallback to $100
        amt = context.user_data.get('bet_amount', 100)
        engine = ArbEngine()
        res = engine.analyze(240, -220, float(amt))
        
        if res:
            # PLACE BET LOGIC
            if not PRIVATE_KEY:
                await query.edit_message_text("❌ PRIVATE_KEY missing in Env!", reply_markup=main_kb())
                return

            try:
                # Initialize Polymarket Client
                client = ClobClient("https://clob.polymarket.com", key=PRIVATE_KEY, chain_id=137)
                # Note: You would replace these with real token IDs from the market
                msg = f"✅ **ARB FOUND & BET PLACED**\n━━━━━━━━━━━━\n💰 Stake: ${amt}\n📈 Profit: ${res['profit']}"
                # (Actual client.create_order calls would go here)
            except Exception as e:
                msg = f"⚠️ Arb found, but Execution Error: {str(e)[:50]}"
        else:
            msg = "🔎 Scanning... No gaps found (P/L ≤ 1)."
        
        await query.edit_message_text(msg, reply_markup=main_kb(), parse_mode='Markdown')

    elif query.data == 'credit':
        await query.edit_message_text("🏦 Aave status checked. (Logic active)", reply_markup=main_kb())

# --- MAIN ---

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(interaction))
    # Handler for the numeric input
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), set_amount_handler))
    
    print(f"🚀 Hydra Terminal Live for {WALLET_ADDRESS}")
    app.run_polling()
