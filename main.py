import os
import sys
import logging
from decimal import Decimal, getcontext
from web3 import Web3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler

# --- INITIALIZATION ---
getcontext().prec = 10
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# SECURITY: Fetching from environment
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
RPC_URL = os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com")
RAW_WALLET = os.getenv("USER_WALLET_ADDRESS")

# VALIDATION: Ensuring the wallet is real and formatted correctly
if not RAW_WALLET or not Web3.is_address(RAW_WALLET):
    print("❌ FATAL: USER_WALLET_ADDRESS is invalid or not set in environment!")
    sys.exit(1)

WALLET_ADDRESS = Web3.to_checksum_address(RAW_WALLET)

# AAVE V3 Polygon Smart Contract Addresses
AAVE_POOL_V3 = "0x7937d4799803Fb3ad9212d7164cc9B1aB96048a1"
AAVE_ABI = [{"inputs":[{"internalType":"address","name":"user","type":"address"}],"name":"getUserAccountData","outputs":[{"internalType":"uint256","name":"totalCollateralBase","type":"uint256"},{"internalType":"uint256","name":"totalDebtBase","type":"uint256"},{"internalType":"uint256","name":"availableBorrowsBase","type":"uint256"},{"internalType":"uint256","name":"currentLiquidationThreshold","type":"uint256"},{"internalType":"uint256","name":"ltv","type":"uint256"},{"internalType":"uint256","name":"healthFactor","type":"uint256"}],"stateMutability":"view","type":"function"}]

w3 = Web3(Web3.HTTPProvider(RPC_URL))

# --- CORE LOGIC ---

class ArbEngine:
    @staticmethod
    def get_implied_prob(odds):
        odds = Decimal(str(odds))
        return Decimal(100) / (odds + 100) if odds > 0 else abs(odds) / (abs(odds) + 100)

    def analyze(self, odds_a, odds_b, target_payout):
        prob_a, prob_b = self.get_implied_prob(odds_a), self.get_implied_prob(odds_b)
        total_prob = prob_a + prob_b
        
        if total_prob >= 1.0: return None # Guarantee P/L > 1

        stake_a = Decimal(target_payout) * prob_a
        stake_b = Decimal(target_payout) * prob_b
        total_cost = stake_a + stake_b
        profit = Decimal(target_payout) - total_cost
        
        return {
            "stake_a": round(stake_a, 2), "stake_b": round(stake_b, 2),
            "total_cost": round(total_cost, 2), "profit": round(profit, 2),
            "roi": round((profit / total_cost) * 100, 2)
        }

class AaveManager:
    def __init__(self):
        self.contract = w3.eth.contract(address=AAVE_POOL_V3, abi=AAVE_ABI)

    def get_user_status(self):
        try:
            d = self.contract.functions.getUserAccountData(WALLET_ADDRESS).call()
            # Aave Base currency is 8 decimals
            return {
                "borrow_power": Decimal(d[2]) / Decimal(10**8), 
                "health": Decimal(d[5]) / Decimal(1e18)
            }
        except Exception as e:
            logging.error(f"RPC Error: {e}")
            return {"borrow_power": Decimal(0), "health": Decimal(0)}

# --- UI CONTROLLER ---

def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Scan Live Arb", callback_data='scan')],
        [InlineKeyboardButton("🏦 Aave Credit Line", callback_data='credit')],
        [InlineKeyboardButton("🔄 Refresh Dashboard", callback_data='home')]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "⚡ **HYDRA ARBITRAGE TERMINAL**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🛠️ **ACTIVE WALLET:** `{WALLET_ADDRESS}`\n"
        "📡 **NETWORK:** `Polygon POS`\n"
        "⚖️ **LOGIC:** `CREDIT-LINE LEVERAGE`"
    )
    if update.message:
        await update.message.reply_text(text, reply_markup=main_kb(), parse_mode='Markdown')
    else:
        await update.callback_query.edit_message_text(text, reply_markup=main_kb(), parse_mode='Markdown')

async def interaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    bank = AaveManager()
    engine = ArbEngine()

    if query.data == 'home':
        await start(update, context)

    elif query.data == 'credit':
        data = bank.get_user_status()
        status = "🟢 HEALTHY" if data['health'] > 1.5 else "⚠️ RISK"
        msg = (
            "🏦 **YOUR AAVE V3 POSITION**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 **Limit:** `${data['borrow_power']:.2f} USDC`\n"
            f"🛡️ **Health:** `{data['health']:.2f}`\n"
            f"🚦 **Status:** {status}"
        )
        await query.edit_message_text(msg, reply_markup=main_kb(), parse_mode='Markdown')

    elif query.data == 'scan':
        # REAL-TIME CHECK: Use your actual Aave borrow power for the calculation
        data = bank.get_user_status()
        max_stake = data['borrow_power'] if data['borrow_power'] > 10 else 1000
        
        # Example Odds (Replace with real Market API feed)
        res = engine.analyze(240, -220, max_stake)
        
        if res:
            msg = (
                "🎯 **ARBITRAGE OPPORTUNITY**\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ **Bet A (+240):** `${res['stake_a']}`\n"
                f"✅ **Bet B (-220):** `${res['stake_b']}`\n"
                f"💰 **Total Profit:** `${res['profit']}`\n"
                f"📈 **Leveraged ROI:** `{res['roi']}%`"
            )
        else:
            msg = "🔎 Scanning... Markets are efficient (P/L ≤ 1)."
        
        await query.edit_message_text(msg, reply_markup=main_kb(), parse_mode='Markdown')

# --- MAIN ---

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(interaction))
    print(f"🚀 Hydra Terminal connected to {WALLET_ADDRESS}")
    app.run_polling()
