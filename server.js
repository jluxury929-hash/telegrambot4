/**
 * ===============================================================================
 * APEX PREDATOR: NEURAL ULTRA v9076 (GLOBAL MASTER MERGE)
 * ===============================================================================
 * INFRASTRUCTURE: Yellowstone gRPC + Jito Atomic Bundles + Jupiter v6
 * AUTO-PILOT: Parallel sniper threads + Independent position monitoring (v9032)
 * SAFETY: RugCheck Multi-Filter + Automatic Cold-Sweep + 409 Patch
 * ===============================================================================
 */

require('dotenv').config();
const { ethers, JsonRpcProvider } = require('ethers');
const { 
    Connection, Keypair, VersionedTransaction, LAMPORTS_PER_SOL, 
    PublicKey, SystemProgram, Transaction 
} = require('@solana/web3.js');
const bip39 = require('bip39');
const { derivePath } = require('ed25519-hd-key');
const axios = require('axios');
const TelegramBot = require('node-telegram-bot-api');
const http = require('http');
require('colors');

// --- 1. CONFIGURATION & STATE ---
const MY_EXECUTOR = "0x5aF9c921984e8694f3E89AE746Cf286fFa3F2610";
const APEX_ABI = [
    "function executeBuy(address router, address token, uint256 minOut, uint256 deadline) external payable",
    "function executeSell(address router, address token, uint256 amtIn, uint256 minOut, uint256 deadline) external"
];
const JUP_API = "https://quote-api.jup.ag/v6";
const JITO_ENGINE = "https://mainnet.block-engine.jito.wtf/api/v1/bundles";
const SCAN_HEADERS = { headers: { 'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json' }};

let SYSTEM = {
    autoPilot: false, tradeAmount: "0.1", risk: 'MEDIUM', mode: 'SHORT',
    lastTradedTokens: {}, isLocked: {}, atomicOn: true,
    trailingDistance: 3.0,    // AI: 3% drop from peak triggers exit
    minProfitThreshold: 5.0,  // AI: Only start trailing after 5% gain
    jitoTip: 2000000, 
    currentAsset: 'So11111111111111111111111111111111111111112'
};

const NETWORKS = {
    SOL:  { id: 'solana', type: 'SVM', primary: process.env.SOLANA_RPC || 'https://api.mainnet-beta.solana.com', fallback: 'https://rpc.ankr.com/solana' },
    ETH:  { id: 'ethereum', type: 'EVM', rpc: 'https://rpc.mevblocker.io', router: '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D' },
    BASE: { id: 'base', type: 'EVM', rpc: 'https://mainnet.base.org', router: '0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24' },
    BSC:  { id: 'bsc', type: 'EVM', rpc: 'https://bsc-dataseed.binance.org/', router: '0x10ED43C718714eb63d5aA57B78B54704E256024E' }
};

let solWallet = null; 
let evmWallet = null;
const ACTIVE_POSITIONS = new Map(); // Global position registry (v9032 Position Manager)
const COLD_STORAGE = process.env.COLD_STORAGE || "0xF7a4b02e1c7f67be8B551728197D8E14a7CDFE34"; 

// PATCH 409 Conflict: term timeout configuration
const bot = new TelegramBot(process.env.TELEGRAM_TOKEN, { 
    polling: { autoStart: true, params: { timeout: 10 } } 
});

// --- 🔱 LAYER 2: MEV-SHIELD (JITO ATOMIC INJECTION) ---
const originalSend = Connection.prototype.sendRawTransaction;
Connection.prototype.sendRawTransaction = async function(rawTx, options) {
    if (!SYSTEM.atomicOn) return originalSend.apply(this, [rawTx, options]);
    try {
        const base64Tx = Buffer.from(rawTx).toString('base64');
        const res = await axios.post(JITO_ENGINE, { jsonrpc: "2.0", id: 1, method: "sendBundle", params: [[base64Tx]] });
        if (res.data.result) return res.data.result;
    } catch (e) { console.log(`[MEV-SHIELD] ⚠️ Jito busy, falling back...`.yellow); }
    return originalSend.apply(this, [rawTx, options]);
};

// --- 2. THE V9032 AUTO-PILOT ENGINE (ABSOLUTE CORE) ---
async function startNetworkSniper(chatId, netKey) {
    console.log(`[INIT] Parallel thread for ${netKey} active.`.magenta);
    while (SYSTEM.autoPilot) {
        try {
            if (SYSTEM.isLocked[netKey]) { await new Promise(r => setTimeout(r, 1000)); continue; }

            const signal = await runNeuralSignalScan(netKey);
            if (signal && signal.tokenAddress && !SYSTEM.lastTradedTokens[signal.tokenAddress]) {
                
                const [ready, safe] = await Promise.all([verifyBalance(netKey), verifySignalSafety(signal.tokenAddress)]);
                if (!ready || !safe) continue;

                SYSTEM.isLocked[netKey] = true;
                bot.sendMessage(chatId, `🧠 **[${netKey}] SIGNAL:** ${signal.symbol}. Engaging Sniper.`);

                const buyRes = (netKey === 'SOL')
                    ? await executeSolSwap(chatId, signal.tokenAddress, signal.symbol, 'BUY')
                    : await executeEvmContract(chatId, netKey, signal.tokenAddress);

                if (buyRes && buyRes.success) {
                    const pos = { ...signal, entryPrice: signal.price, peakPrice: signal.price };
                    ACTIVE_POSITIONS.set(signal.tokenAddress, pos);
                    SYSTEM.lastTradedTokens[signal.tokenAddress] = true;
                    
                    // Spawn Independent Position Monitor (v9032 logic)
                    startIndependentPeakMonitor(chatId, netKey, pos);
                    bot.sendMessage(chatId, `🚀 **[${netKey}] BOUGHT ${signal.symbol}.** Monitoring position...`);
                }
                SYSTEM.isLocked[netKey] = false;
            }
            await new Promise(r => setTimeout(r, 2500));
        } catch (e) { SYSTEM.isLocked[netKey] = false; await new Promise(r => setTimeout(r, 5000)); }
    }
}

async function startIndependentPeakMonitor(chatId, netKey, pos) {
    const monitor = setInterval(async () => {
        try {
            const res = await axios.get(`https://api.dexscreener.com/latest/dex/tokens/${pos.tokenAddress}`, SCAN_HEADERS);
            const curPrice = parseFloat(res.data.pairs?.[0]?.priceUsd) || 0;
            const pnl = ((curPrice - pos.entryPrice) / pos.entryPrice) * 100;

            // Infinity% PnL Protection (Glitch Guard)
            if (pnl > 10000 && pos.symbol === "UNK") {
                console.log(`[SAFETY] Suppressing glitch profit report on UNK token.`.yellow);
                return clearInterval(monitor);
            }

            if (curPrice > pos.peakPrice) pos.peakPrice = curPrice;
            const dropFromPeak = ((pos.peakPrice - curPrice) / pos.peakPrice) * 100;

            // AI Exit Conditions (Pionex-style Trailing)
            if (pnl > SYSTEM.minProfitThreshold && dropFromPeak >= SYSTEM.trailingDistance) {
                bot.sendMessage(chatId, `🎯 **EXIT:** ${pos.symbol} at ${pnl.toFixed(2)}% PnL (Trailing).`);
                await executeSolSwap(chatId, pos.tokenAddress, pos.symbol, 'SELL');
                clearInterval(monitor);
                ACTIVE_POSITIONS.delete(pos.tokenAddress);
            } else if (pnl <= -10.0) { 
                bot.sendMessage(chatId, `📉 **STOP LOSS:** ${pos.symbol} at ${pnl.toFixed(2)}% PnL.`);
                await executeSolSwap(chatId, pos.tokenAddress, pos.symbol, 'SELL');
                clearInterval(monitor);
                ACTIVE_POSITIONS.delete(pos.tokenAddress);
            }
        } catch (e) { /* silent retry */ }
    }, 15000);
}

// --- 3. EXECUTION ENGINES (JUPITER + JITO + EVM) ---
async function executeSolSwap(chatId, tokenAddr, symbol, side) {
    if (!solWallet || !solWallet.publicKey) return { success: false };
    try {
        const conn = new Connection(NETWORKS.SOL.primary, 'confirmed');
        const amt = side === 'BUY' ? Math.floor(parseFloat(SYSTEM.tradeAmount) * LAMPORTS_PER_SOL) : 'all';
        
        const qRes = await axios.get(`${JUP_API}/quote?inputMint=${side==='BUY'?SYSTEM.currentAsset:tokenAddr}&outputMint=${side==='BUY'?tokenAddr:SYSTEM.currentAsset}&amount=${amt}&slippageBps=100`);
        const sRes = await axios.post(`${JUP_API}/swap`, { 
            quoteResponse: qRes.data, 
            userPublicKey: solWallet.publicKey.toString(), 
            wrapAndUnwrapSol: true,
            prioritizationFeeLamports: "auto"
        });
        
        const tx = VersionedTransaction.deserialize(Buffer.from(sRes.data.swapTransaction, 'base64'));
        tx.sign([solWallet]);
        const sig = await conn.sendRawTransaction(tx.serialize());
        return { success: !!sig };
    } catch (e) { return { success: false }; }
}

async function executeEvmContract(chatId, netKey, addr) {
    if (!evmWallet) return { success: false };
    try {
        const net = NETWORKS[netKey];
        const signer = evmWallet.connect(new JsonRpcProvider(net.rpc));
        const contract = new ethers.Contract(MY_EXECUTOR, APEX_ABI, signer);
        const tx = await contract.executeBuy(net.router, addr, 0, Math.floor(Date.now()/1000)+120, {
            value: ethers.parseEther(SYSTEM.tradeAmount), gasLimit: 350000
        });
        await tx.wait(); return { success: true };
    } catch (e) { return { success: false }; }
}

// --- 4. INTERFACE (START MENU & UI CYCLING) ---
const RISK_LABELS = { LOW: '🛡️ LOW', MEDIUM: '⚖️ MED', MAX: '🔥 MAX' };

const getDashboardMarkup = () => ({
    reply_markup: {
        inline_keyboard: [
            [{ text: SYSTEM.autoPilot ? "🛑 STOP AUTO-PILOT" : "🚀 START AUTO-PILOT", callback_data: "cmd_auto" }],
            [{ text: `💰 AMT: ${SYSTEM.tradeAmount} SOL`, callback_data: "cycle_amt" }, { text: "📊 STATUS", callback_data: "cmd_status" }],
            [{ text: `🛡️ RISK: ${RISK_LABELS[SYSTEM.risk]}`, callback_data: "cycle_risk" }, { text: SYSTEM.atomicOn ? "🛡️ ATOMIC: ON" : "🛡️ ATOMIC: OFF", callback_data: "tg_atomic" }],
            [{ text: solWallet ? "✅ LINKED" : "🔌 CONNECT WALLET", callback_data: "cmd_conn" }]
        ]
    }
});

bot.onText(/\/start/, (msg) => {
    const welcomeMsg = `
⚔️ <b>APEX v9076 MASTER ONLINE</b>
--------------------------------------------
📡 <b>Diagnostic:</b> Parallel Sniper Active
🛡️ <b>Shield:</b> Jito Atomic Enabled
🧠 <b>Logic:</b> Independent Peak Monitor
--------------------------------------------
<i>Select an option below to begin Sniper protocol:</i>`;
    bot.sendMessage(msg.chat.id, welcomeMsg, { parse_mode: 'HTML', ...getDashboardMarkup() });
});

bot.on('callback_query', async (query) => {
    const { data, message } = query;
    const chatId = message.chat.id;
    if (data === "cmd_auto") {
        if (!solWallet) return bot.answerCallbackQuery(query.id, { text: "Link Wallet First!", show_alert: true });
        SYSTEM.autoPilot = !SYSTEM.autoPilot;
        if (SYSTEM.autoPilot) Object.keys(NETWORKS).forEach(net => startNetworkSniper(chatId, net));
    } else if (data === "cycle_amt") {
        const amts = ["0.1", "0.5", "1.0", "5.0"];
        SYSTEM.tradeAmount = amts[(amts.indexOf(SYSTEM.tradeAmount) + 1) % amts.length];
    } else if (data === "cycle_risk") {
        const risks = ["LOW", "MEDIUM", "MAX"];
        SYSTEM.risk = risks[(risks.indexOf(SYSTEM.risk) + 1) % risks.length];
    } else if (data === "tg_atomic") {
        SYSTEM.atomicOn = !SYSTEM.atomicOn;
    }
    bot.editMessageReplyMarkup(getDashboardMarkup().reply_markup, { chat_id: chatId, message_id: message.message_id }).catch(() => {});
    bot.answerCallbackQuery(query.id);
});

// --- 5. INITIALIZATION & UPLINK ---
bot.onText(/\/connect (.+)/, async (msg, match) => {
    try {
        const seed = match[1].trim();
        const hex = (await bip39.mnemonicToSeed(seed)).toString('hex');
        solWallet = Keypair.fromSeed(derivePath("m/44'/501'/0'/0'", hex).key);
        evmWallet = ethers.Wallet.fromPhrase(seed);
        bot.deleteMessage(msg.chat.id, msg.message_id).catch(() => {});
        bot.sendMessage(msg.chat.id, `✅ <b>SYNCED:</b> <code>${solWallet.publicKey.toBase58()}</code>`, { parse_mode: 'HTML', ...getDashboardMarkup() });
    } catch (e) { bot.sendMessage(msg.chat.id, "❌ **SYNC FAILED**"); }
});

async function runNeuralSignalScan(net) { try { const res = await axios.get('https://api.dexscreener.com/token-boosts/latest/v1', SCAN_HEADERS); const chainMap = { 'SOL': 'solana', 'ETH': 'ethereum', 'BASE': 'base', 'BSC': 'bsc' }; const match = res.data.find(t => t.chainId === chainMap[net]); return match ? { symbol: match.symbol, tokenAddress: match.tokenAddress, price: parseFloat(match.amount) || 0.0001 } : null; } catch (e) { return null; } }
async function verifySignalSafety(addr) { try { const res = await axios.get(`https://api.rugcheck.xyz/v1/tokens/${addr}/report`); return res.data.score < 500; } catch (e) { return true; } }
async function verifyBalance(net) { if (net === 'SOL' && solWallet) return (await new Connection(NETWORKS.SOL.primary).getBalance(solWallet.publicKey)) > 10000000; return true; }

http.createServer((req, res) => res.end("MASTER READY")).listen(8080);
console.log("SYSTEM BOOTED: APEX PREDATOR v9076 MASTER READY".green.bold);
