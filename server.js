const express = require('express');
const bip39 = require('bip39');
const { derivePath } = require('ed25519-hd-key');
const { Keypair } = require('@solana/web3.js');
const bs58 = require('bs58');

const app = express();
app.use(express.json());

app.post('/derive', async (req, res) => {
    const { mnemonic } = req.body;

    if (!mnemonic || !bip39.validateMnemonic(mnemonic)) {
        return res.status(400).json({ error: "Invalid seed phrase" });
    }

    try {
        // 1. Convert mnemonic to seed buffer
        const seed = await bip39.mnemonicToSeed(mnemonic);

        // 2. Define the derivation path (Standard Solana path)
        const path = "m/44'/501'/0'/0'";

        // 3. Derive the seed for the specific path
        const derivedSeed = derivePath(path, seed.toString('hex')).key;

        // 4. Create the Keypair
        const keypair = Keypair.fromSeed(derivedSeed);

        res.json({
            address: keypair.publicKey.toBase58(),
            privateKey: bs58.encode(keypair.secretKey),
            derivationPath: path,
            message: "Keep this private key safe and delete this log!"
        });
    } catch (err) {
        res.status(500).json({ error: "Derivation failed", details: err.message });
    }
});

const PORT = 3000;
app.listen(PORT, () => {
    console.log(`Server running on http://localhost:${PORT}`);
    console.log(`To use: Send a POST request to /derive with { "mnemonic": "your words here" }`);
});
