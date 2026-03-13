import os
import sys
import logging
from decimal import Decimal, getcontext
from web3 import Web3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler

# --- INITIALIZATION ---
getcontext().prec = 10
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Environment Variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
RPC_URL = os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com")
WALLET_ADDRESS = os.getenv("USER_WALLET_ADDRESS", "0x0000000000000000000000000000000000000000")

# Contract Constants (Polygon)
AAVE_POOL_V3 = "0x7937d4799803Fb3ad9212d7164cc9B1aB96048a1"
AAVE_ABI = [{"inputs":[{"internalType":"address","name":"user","type":"address"}],"name":"getUserAccountData","outputs":[{"internalType":"uint256","name":"totalCollateralBase","type":"uint256"},{"internalType":"uint256","name":"totalDebtBase","type":"uint256"},{"internalType":"uint256","name":"availableBorrowsBase","type":"uint256"},{"internalType":"uint256","name":"currentLiquidationThreshold","type":"uint256"},{"internalType":"uint256","name":"ltv","type":"uint256"},{"internalType":"uint256","name":"healthFactor","type":"uint256"}],"stateMutability":"view","type":"function"}]

w3 = Web3(Web3.HTTPProvider(RPC_URL))

# --- LOGIC MODULES ---

class ArbEngine:
    @staticmethod
    def get_implied_prob(odds):
        odds = Decimal(odds)
        if odds > 0:
            return Decimal(100) / (odds + 100)
        return abs(odds) / (abs(odds) + 100)

    def analyze(self, odds_a, odds_b, target_payout):
        prob_a = self.get_implied_prob(odds_a)
        prob_b = self.get_implied_prob(odds_b)
        total_prob = prob_a + prob_b

        if total_prob >= 1.0: # Filter for P/L > 1 only
            return None

        stake_a = Decimal(target_payout) * prob_a
        stake_b = Decimal(target_payout) * prob_b
        total_cost = stake_a + stake_b
        profit = Decimal(target_payout) - total_cost
        
        return {
            "stake_a": round(stake_a, 2),
            "stake_b": round(stake_b, 2),
            "total_cost": round(total_cost, 2),
            "profit": round(profit, 2),
            "roi": round((profit / total_cost) * 100, 2),
            "edge": round((1 - total_prob) * 100, 2)
        }

class AaveManager:
    def __init__(self):
        self.contract = w3.eth.contract(address=AAVE_POOL_V3, abi=AAVE_ABI)

    def get_data(self):
        try:
            d = self.contract.functions.getUserAccountData(WALLET_ADDRESS).call()
            return {
                "borrow_power": Decimal(d[2]) / Decimal(10**8),
                "health": Decimal(d[5]) / Decimal(1e18)
            }
        except:
            return {"borrow_power": Decimal(0), "health": Decimal(0)}

# --- TELEGRAM INTERFACE ---

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Scan Markets", callback_data='scan'),
         InlineKeyboardButton("🏦 Aave Status", callback_data='credit')],
        [InlineKeyboardButton("⚙️ Risk Settings", callback_data='settings'),
         InlineKeyboardButton("🔄 Refresh", callback_data='start_over')]
    ])

async def post_init(application):
    """Adds the Menu button to the Telegram UI"""
    await application.bot.set_my_commands([
        BotCommand("start", "Boot Terminal"),
        BotCommand("scan", "Run Arb Scanner"),
        BotCommand("credit", "Check Aave Health")
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "⚡ **HYDRA TERMINAL ONLINE**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"**Wallet:** `{WALLET_ADDRESS[:6]}...{WALLET_ADDRESS[-4:]}`\n"
        "**Network:** `Polygon Mainnet`\n\n"
        "Ready to extract value from market inefficiencies."
    )
    if update.message:
        await update.message.reply_text(text, reply_markup=main_menu_keyboard(), parse_mode='Markdown')
    else:
        await update.callback_query.edit_message_text(text, reply_markup=main_menu_keyboard(), parse_mode='Markdown')

async def handle_interaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    engine = ArbEngine()
    bank = AaveManager()

    if query.data == 'scan':
        # Simulated Market Feed (Connect to Polymarket API here)
        market_name = "Election: Candidate A vs B"
        odds_a, odds_b = 240, -220
        
        aave_data = bank.get_data()
        # Use 90% of borrow power as stake for safety
        target = aave_data['borrow_power'] * Decimal('0.9') if aave_data['borrow_power'] > 0 else 1000
        
        res = engine.analyze(odds_a, odds_b, target)
        
        if res:
            report = (
                f"🎯 **ARB DETECTED: {market_name}**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🔹 **Bet A (+{odds_a}):** `${res['stake_a']}`\n"
                f"🔹 **Bet B ({odds_b}):** `${res['stake_b']}`\n"
                f"💰 **Net Profit:** `${res['profit']}`\n"
                f"📈 **ROI:** `{res['roi']}%` | **Edge:** `{res['edge']}%`"
            )
        else:
            report = "🔎 Scanning... All markets currently efficient (P/L ≤ 1)."
        
        await query.edit_message_text(report, reply_markup=main_menu_keyboard(), parse_mode='Markdown')

    elif query.data == 'credit':
        data = bank.get_data()
        status = "✅ HEALTHY" if data['health'] > 1.5 else "⚠️ RISK"
        msg = (
            "🏦 **AAVE V3 CREDIT LINE**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"• **Available:** `${data['borrow_power']:.2f} USDC`\n"
            f"• **Health Factor:** `{data['health']:.2f}`\n"
            f"• **Status:** `{status}`"
        )
        await query.edit_message_text(msg, reply_markup=main_menu_keyboard(), parse_mode='Markdown')

    elif query.data == 'start_over':
        await start(update, context)

# --- RUNNER ---

if __name__ == '__main__':
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "YOUR_BOT_TOKEN":
        print("❌ CRITICAL: TELEGRAM_TOKEN is not set.")
        sys.exit(1)

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scan", handle_interaction))
    app.add_handler(CallbackQueryHandler(handle_interaction))

    print("🚀 Hydra Terminal is broadcasting...")
    app.run_polling()
