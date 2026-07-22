import os, random, time, sys, json
from web3 import Web3
from eth_account import Account
from web3.middleware import ExtraDataToPOAMiddleware

sys.stdout.reconfigure(line_buffering=True)
print("GIWA Chain Farm v2 запущен!", flush=True)

RPC      = "https://sepolia-rpc.giwa.io"
CHAIN_ID = 91342

WETH_ADDR         = "0x4200000000000000000000000000000000000006"
NICK_FACTORY      = "0x4e59b44847b379578588920cA78FbF26c0B4956C"
L2_MSG_PASSER     = "0x4200000000000000000000000000000000000016"
PLAYGROUND_FAUCET = "0x63CCe2b569A7bC35895ee24306c1512fefc06121"
PLAYGROUND_FEE    = int(0.001 * 1e18)

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
_raw_keys = os.getenv("PRIVATE_KEYS", "")
PRIVATE_KEYS = [k.strip() for k in _raw_keys.split(",") if k.strip()]

# Compiled contracts
_c = json.load(open(os.path.join(os.path.dirname(__file__), 'contracts.json')))
ERC20_BYTECODE        = _c['erc20']['bytecode']
ERC20_ABI             = _c['erc20']['abi']
NFT_BYTECODE          = _c['nft']['bytecode']
NFT_ABI               = _c['nft']['abi']
COUNTER_BYTECODE      = _c['counter']['bytecode']
COUNTER_ABI           = _c['counter']['abi']
EMITTER_BYTECODE      = _c['emitter']['bytecode']
EMITTER_ABI           = _c['emitter']['abi']
CREATE2F_BYTECODE     = _c['create2factory']['bytecode']
CREATE2F_ABI          = _c['create2factory']['abi']

TOKEN_NAMES = [
    ("GiwaToken", "GWT"), ("TestUSD", "TUSD"), ("FarmCoin", "FARM"),
    ("AlphaToken", "ALPHA"), ("BetaToken", "BETA"), ("NetToken", "NET"),
    ("ChainGold", "CGLD"), ("DevToken", "DEV"), ("SeedToken", "SEED"),
    ("LabCoin", "LAB"),
]

L2_MSG_PASSER_ABI = [{"name": "initiateWithdrawal", "inputs": [
    {"name": "_target", "type": "address"},
    {"name": "_gasLimit", "type": "uint256"},
    {"name": "_data", "type": "bytes"}
], "outputs": [], "type": "function", "stateMutability": "payable"}]

WETH_ABI = [
    {"name": "deposit",  "inputs": [], "outputs": [], "type": "function", "stateMutability": "payable"},
    {"name": "withdraw", "inputs": [{"name": "wad", "type": "uint256"}], "outputs": [], "type": "function", "stateMutability": "nonpayable"},
    {"name": "balanceOf","inputs": [{"name": "a", "type": "address"}],   "outputs": [{"type": "uint256"}], "type": "function", "stateMutability": "view"},
    {"name": "approve",  "inputs": [{"name": "guy", "type": "address"}, {"name": "wad", "type": "uint256"}], "outputs": [{"type": "bool"}], "type": "function", "stateMutability": "nonpayable"},
    {"name": "transfer", "inputs": [{"name": "dst", "type": "address"}, {"name": "wad", "type": "uint256"}], "outputs": [{"type": "bool"}], "type": "function", "stateMutability": "nonpayable"},
]

# Simple storage contract
DUMMY_BYTECODE = (
    "0x608060405234801561001057600080fd5b5060c0806100206000396000f3fe"
    "6080604052348015600f57600080fd5b506004361060285760003560e01c8063"
    "2e64cec114602d5780636057361d14603f575b600080fd5b60005460405190"
    "815260200160405180910390f35b604e60596004803603810190604a919060"
    "9c565b605b565b005b8060008190555050565b60008135905060968160b2565b"
    "92915050565b60006020828403121560ad5760ac60ad565b5b600060b984828"
    "50160876090565b91505092915050565b60bb8160c1565b811460c557600080"
    "fd5b50565b600081905091905056fea264697066735822122035f1b69e8af68"
    "9f7b15b0b2e6a4df0e9a8d2c7d3f4e5a6b7c8d9e0f1a2b3c464736f6c6343"
    "00081300 33"
).replace(" ", "")

# Greeting contract: stores a name, different bytecode for variety
GREETING_BYTECODE = (
    "0x6080604052348015600f57600080fd5b5060405160200160405180910390208"
    "060005560405160200160405180910390f35060d08061003b6000396000f3fe6"
    "080604052348015600f57600080fd5b506004361060285760003560e01c80632"
    "e64cec114602d5780636057361d14603f575b600080fd5b60005460405190815"
    "260200160405180910390f35b604e60596004803603810190604a919060"
    "9c565b605b565b005b8060008190555050565b60008135905060968160b2565b"
    "92915050565b60006020828403121560ad5760ac60ad565b5b600060b984828"
    "50160876090565b91505092915050565b60bb8160c1565b811460c557600080"
    "fd5b50565b600081905091905056"
).replace(" ", "")


def make_w3():
    w3 = Web3(Web3.HTTPProvider(RPC, request_kwargs={'timeout': 30}))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3


def get_tx_params(w3, sender, value=0, gas=300_000):
    gas_price = max(w3.eth.gas_price, w3.to_wei(0.001, 'gwei'))
    return {
        'from': sender,
        'nonce': w3.eth.get_transaction_count(sender),
        'gasPrice': int(gas_price * 1.3),
        'chainId': CHAIN_ID,
        'value': value,
        'gas': gas,
    }


def send_tx(w3, account, tx, tag, retries=3):
    for attempt in range(1, retries + 1):
        try:
            signed  = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
            ok = receipt.status == 1
            link = f"https://explorer-sepolia.giwa.io/tx/{tx_hash.hex()}"
            print(f"{tag} {'✅' if ok else '❌ FAIL'} | {link}", flush=True)
            return ok
        except Exception as e:
            err = str(e)
            if attempt < retries and ('nonce' in err.lower() or 'underpriced' in err.lower()):
                tx['nonce'] = w3.eth.get_transaction_count(account.address)
                time.sleep(8)
                continue
            print(f"{tag} ❌ {err[:120]}", flush=True)
            return False


def apause(a=60, b=240):
    time.sleep(random.randint(a, b))


def rand_sleep(min_m=54, max_m=120):
    d = random.randint(min_m * 60, max_m * 60)
    h, m = divmod(d // 60, 60)
    print(f"⏳ Пауза ~{h}ч {m}мин...", flush=True)
    time.sleep(d)


# ── Actions ──────────────────────────────────────────────────────────────────

def act_wrap_eth(w3, acc, tag):
    bal     = w3.eth.get_balance(acc.address)
    reserve = int(0.001 * 1e18)
    if bal < reserve + int(0.00001 * 1e18):
        print(f"{tag} Wrap: мало ETH", flush=True); return
    amt = random.randint(int(0.00001 * 1e18), min(int(0.0005 * 1e18), bal - reserve))
    c   = w3.eth.contract(WETH_ADDR, abi=WETH_ABI)
    print(f"{tag} 🔄 Wrap {amt/1e18:.5f} ETH → WETH", flush=True)
    send_tx(w3, acc, c.functions.deposit().build_transaction(
        get_tx_params(w3, acc.address, value=amt)), tag)


def act_unwrap_eth(w3, acc, tag):
    c    = w3.eth.contract(WETH_ADDR, abi=WETH_ABI)
    wbal = c.functions.balanceOf(acc.address).call()
    if wbal < int(0.000005 * 1e18):
        print(f"{tag} Unwrap: мало WETH", flush=True); return
    amt = random.randint(int(0.000005 * 1e18), min(wbal, int(0.0005 * 1e18)))
    print(f"{tag} 🔄 Unwrap {amt/1e18:.5f} WETH → ETH", flush=True)
    send_tx(w3, acc, c.functions.withdraw(amt).build_transaction(
        get_tx_params(w3, acc.address)), tag)


def act_wrap_unwrap_cycle(w3, acc, tag):
    act_wrap_eth(w3, acc, tag)
    apause(90, 300)
    act_unwrap_eth(w3, acc, tag)


def act_self_transfer(w3, acc, tag):
    bal     = w3.eth.get_balance(acc.address)
    reserve = int(0.001 * 1e18)
    if bal < reserve:
        print(f"{tag} Self-transfer: мало ETH", flush=True); return
    amt = random.randint(int(0.000001 * 1e18), min(int(0.0001 * 1e18), bal - reserve))
    tx  = {**get_tx_params(w3, acc.address, value=amt, gas=21_000), 'to': acc.address}
    print(f"{tag} 📤 Self-transfer {amt/1e18:.6f} ETH", flush=True)
    send_tx(w3, acc, tx, tag)


def act_weth_approve_revoke(w3, acc, tag):
    c   = w3.eth.contract(WETH_ADDR, abi=WETH_ABI)
    # Approve a fixed known contract (not another wallet)
    spender_alt = "0x4200000000000000000000000000000000000010"  # L2StandardBridge predeploy
    amt = random.randint(1, 100) * 10**16
    print(f"{tag} ✍️ Approve WETH {amt/1e18:.3f}", flush=True)
    send_tx(w3, acc, c.functions.approve(spender_alt, amt).build_transaction(
        get_tx_params(w3, acc.address)), tag)
    apause(45, 180)
    print(f"{tag} ✍️ Revoke WETH", flush=True)
    send_tx(w3, acc, c.functions.approve(spender_alt, 0).build_transaction(
        get_tx_params(w3, acc.address)), tag)


def act_weth_self_transfer(w3, acc, tag):
    c    = w3.eth.contract(WETH_ADDR, abi=WETH_ABI)
    wbal = c.functions.balanceOf(acc.address).call()
    if wbal < int(0.000005 * 1e18):
        print(f"{tag} WETH transfer: мало WETH, оборачиваем", flush=True)
        act_wrap_eth(w3, acc, tag)
        apause(15, 45)
        wbal = c.functions.balanceOf(acc.address).call()
        if wbal < int(0.000005 * 1e18):
            return
    amt = random.randint(int(0.000005 * 1e18), min(wbal, int(0.0001 * 1e18)))
    print(f"{tag} 📤 WETH self-transfer {amt/1e18:.5f}", flush=True)
    send_tx(w3, acc, c.functions.transfer(acc.address, amt).build_transaction(
        get_tx_params(w3, acc.address)), tag)


def act_deploy(w3, acc, tag):
    bc = random.choice([DUMMY_BYTECODE, GREETING_BYTECODE])
    print(f"{tag} 🚀 Deploy контракта", flush=True)
    send_tx(w3, acc, {'data': bc, **get_tx_params(w3, acc.address)}, tag)


def act_multi_deploy(w3, acc, tag):
    count = random.randint(2, 3)
    for i in range(count):
        bc = random.choice([DUMMY_BYTECODE, GREETING_BYTECODE])
        print(f"{tag} 🚀 Multi-deploy [{i+1}/{count}]", flush=True)
        send_tx(w3, acc, {'data': bc, **get_tx_params(w3, acc.address)}, tag)
        if i < count - 1:
            apause(45, 120)


def act_deploy_interact(w3, acc, tag):
    print(f"{tag} 🚀 Deploy+interact", flush=True)
    params  = get_tx_params(w3, acc.address)
    signed  = acc.sign_transaction({**params, 'data': DUMMY_BYTECODE})
    try:
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
        ca      = receipt.contractAddress
        if not ca:
            return
        link = f"https://explorer-sepolia.giwa.io/tx/{tx_hash.hex()}"
        print(f"{tag} ✅ Deploy | {link}", flush=True)
        apause(30, 90)
        call_data = "0x6057361d" + hex(random.randint(1, 999))[2:].zfill(64)
        send_tx(w3, acc, {**get_tx_params(w3, acc.address), 'to': ca, 'data': call_data, 'gas': 60_000}, tag)
    except Exception as e:
        print(f"{tag} ❌ deploy_interact: {str(e)[:100]}", flush=True)


def act_incremental(w3, acc, tag):
    for base in [0.000005, 0.000015, 0.00005]:
        bal = w3.eth.get_balance(acc.address)
        amt = int((base + random.uniform(0, base * 0.5)) * 1e18)
        if amt > bal - int(0.001 * 1e18):
            continue
        tx = {**get_tx_params(w3, acc.address, value=amt, gas=21_000), 'to': acc.address}
        print(f"{tag} 📤 Incremental {amt/1e18:.6f} ETH", flush=True)
        send_tx(w3, acc, tx, tag)
        apause(45, 120)


def act_burst_transfer(w3, acc, tag):
    count = random.randint(4, 6)
    for j in range(count):
        bal = w3.eth.get_balance(acc.address)
        amt = random.randint(int(0.000001 * 1e18), int(0.000008 * 1e18))
        if amt > bal - int(0.001 * 1e18):
            break
        tx = {**get_tx_params(w3, acc.address, value=amt, gas=21_000), 'to': acc.address}
        print(f"{tag} ⚡ Burst [{j+1}/{count}]", flush=True)
        send_tx(w3, acc, tx, tag)
        time.sleep(random.randint(8, 25))
    bal = w3.eth.get_balance(acc.address)
    big = random.randint(int(0.00005 * 1e18), int(0.0002 * 1e18))
    if big < bal - int(0.001 * 1e18):
        tx = {**get_tx_params(w3, acc.address, value=big, gas=21_000), 'to': acc.address}
        print(f"{tag} ⚡ Burst final big", flush=True)
        send_tx(w3, acc, tx, tag)


def act_multi_transfer(w3, acc, tag):
    count   = random.randint(3, 5)
    reserve = int(0.001 * 1e18)
    for i in range(count):
        bal = w3.eth.get_balance(acc.address)
        amt = random.randint(int(0.000005 * 1e18), int(0.00003 * 1e18))
        if amt > bal - reserve:
            break
        tx = {**get_tx_params(w3, acc.address, value=amt, gas=21_000), 'to': acc.address}
        print(f"{tag} 📤 Multi-transfer [{i+1}/{count}] {amt/1e18:.6f} ETH", flush=True)
        send_tx(w3, acc, tx, tag)
        apause(20, 60)


def act_weth_chain(w3, acc, tag):
    """Wrap ETH → WETH self-transfer → unwrap in one action."""
    bal = w3.eth.get_balance(acc.address)
    reserve = int(0.001 * 1e18)
    if bal < reserve + int(0.00005 * 1e18):
        print(f"{tag} WETH chain: мало ETH", flush=True); return
    amt = random.randint(int(0.00005 * 1e18), min(int(0.0003 * 1e18), bal - reserve))
    c = w3.eth.contract(WETH_ADDR, abi=WETH_ABI)
    print(f"{tag} 🔄 WETH chain: wrap {amt/1e18:.5f}", flush=True)
    if not send_tx(w3, acc, c.functions.deposit().build_transaction(
            get_tx_params(w3, acc.address, value=amt)), tag):
        return
    apause(30, 90)
    wbal = c.functions.balanceOf(acc.address).call()
    if wbal > 0:
        xfr = min(wbal, amt)
        print(f"{tag} 🔄 WETH self-transfer {xfr/1e18:.5f}", flush=True)
        send_tx(w3, acc, c.functions.transfer(acc.address, xfr).build_transaction(
            get_tx_params(w3, acc.address)), tag)
        apause(30, 90)
        print(f"{tag} 🔄 WETH unwrap", flush=True)
        send_tx(w3, acc, c.functions.withdraw(xfr).build_transaction(
            get_tx_params(w3, acc.address)), tag)


def act_triple_deploy(w3, acc, tag):
    """Deploy 3 different contracts in a row."""
    bytecodes = [DUMMY_BYTECODE, GREETING_BYTECODE, DUMMY_BYTECODE]
    labels = ["storage", "greeting", "storage2"]
    for i, (bc, lbl) in enumerate(zip(bytecodes, labels)):
        print(f"{tag} 🚀 Triple-deploy [{i+1}/3] {lbl}", flush=True)
        send_tx(w3, acc, {'data': bc, **get_tx_params(w3, acc.address)}, tag)
        if i < 2:
            apause(45, 120)


def act_contract_call(w3, acc, tag):
    """Deploy storage contract then call setValue."""
    print(f"{tag} 🚀 Deploy + setValue", flush=True)
    params = get_tx_params(w3, acc.address)
    signed = acc.sign_transaction({**params, 'data': DUMMY_BYTECODE})
    try:
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
        ca = receipt.contractAddress
        link = f"https://explorer-sepolia.giwa.io/tx/{tx_hash.hex()}"
        print(f"{tag} ✅ Deploy | {link}", flush=True)
        if not ca:
            return
        apause(20, 60)
        val = random.randint(1, 9999)
        call_data = "0x6057361d" + hex(val)[2:].zfill(64)
        print(f"{tag} 📝 setValue({val})", flush=True)
        send_tx(w3, acc, {**get_tx_params(w3, acc.address), 'to': ca,
                          'data': call_data, 'gas': 60_000}, tag)
    except Exception as e:
        print(f"{tag} ❌ contract_call: {str(e)[:100]}", flush=True)


def act_deploy_erc20(w3, acc, tag):
    tname, symbol = random.choice(TOKEN_NAMES)
    print(f"{tag} 🪙 Deploy ERC-20 {symbol}", flush=True)
    c = w3.eth.contract(abi=ERC20_ABI, bytecode=ERC20_BYTECODE)
    signed = acc.sign_transaction(
        c.constructor(tname, symbol).build_transaction(get_tx_params(w3, acc.address, gas=1_500_000))
    )
    try:
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
        token_addr = receipt.contractAddress
        link = f"https://explorer-sepolia.giwa.io/tx/{tx_hash.hex()}"
        print(f"{tag} {'✅' if receipt.status==1 else '❌'} ERC-20 deploy | {link}", flush=True)
        if not token_addr or receipt.status != 1:
            return
        apause(20, 60)
        token = w3.eth.contract(token_addr, abi=ERC20_ABI)
        supply = 1_000_000 * 10**18
        amt = random.randint(supply // 1000, supply // 100)
        print(f"{tag} 📤 ERC-20 transfer {amt//10**18} {symbol}", flush=True)
        send_tx(w3, acc, token.functions.transfer(acc.address, amt).build_transaction(
            get_tx_params(w3, acc.address, gas=100_000)), tag)
        apause(15, 45)
        print(f"{tag} ✍️  ERC-20 approve", flush=True)
        send_tx(w3, acc, token.functions.approve(acc.address, amt).build_transaction(
            get_tx_params(w3, acc.address, gas=100_000)), tag)
        apause(10, 30)
        print(f"{tag} 📤 ERC-20 transferFrom", flush=True)
        send_tx(w3, acc, token.functions.transferFrom(acc.address, acc.address, amt // 2).build_transaction(
            get_tx_params(w3, acc.address, gas=120_000)), tag)
    except Exception as e:
        print(f"{tag} ❌ erc20: {str(e)[:100]}", flush=True)


def act_deploy_nft(w3, acc, tag):
    print(f"{tag} 🖼️  Deploy NFT + mint", flush=True)
    c = w3.eth.contract(abi=NFT_ABI, bytecode=NFT_BYTECODE)
    signed = acc.sign_transaction(
        c.constructor().build_transaction(get_tx_params(w3, acc.address, gas=1_500_000))
    )
    try:
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
        nft_addr = receipt.contractAddress
        link = f"https://explorer-sepolia.giwa.io/tx/{tx_hash.hex()}"
        print(f"{tag} {'✅' if receipt.status==1 else '❌'} NFT deploy | {link}", flush=True)
        if not nft_addr or receipt.status != 1:
            return
        nft = w3.eth.contract(nft_addr, abi=NFT_ABI)
        count = random.randint(1, 3)
        for i in range(count):
            apause(15, 40)
            print(f"{tag} 🎨 Mint NFT #{i}", flush=True)
            send_tx(w3, acc, nft.functions.mint(acc.address).build_transaction(
                get_tx_params(w3, acc.address, gas=100_000)), tag)
        apause(15, 40)
        print(f"{tag} 🔄 Transfer NFT #0", flush=True)
        send_tx(w3, acc, nft.functions.transferFrom(acc.address, acc.address, 0).build_transaction(
            get_tx_params(w3, acc.address, gas=100_000)), tag)
    except Exception as e:
        print(f"{tag} ❌ nft: {str(e)[:100]}", flush=True)


def act_counter_spam(w3, acc, tag):
    print(f"{tag} 🔢 Deploy Counter", flush=True)
    c = w3.eth.contract(abi=COUNTER_ABI, bytecode=COUNTER_BYTECODE)
    signed = acc.sign_transaction(
        c.constructor().build_transaction(get_tx_params(w3, acc.address, gas=300_000))
    )
    try:
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
        ca = receipt.contractAddress
        link = f"https://explorer-sepolia.giwa.io/tx/{tx_hash.hex()}"
        print(f"{tag} {'✅' if receipt.status==1 else '❌'} Counter | {link}", flush=True)
        if not ca or receipt.status != 1:
            return
        counter = w3.eth.contract(ca, abi=COUNTER_ABI)
        n = random.randint(4, 9)
        for i in range(n):
            apause(8, 25)
            print(f"{tag} ➕ increment [{i+1}/{n}]", flush=True)
            send_tx(w3, acc, counter.functions.increment().build_transaction(
                get_tx_params(w3, acc.address, gas=60_000)), tag)
        if random.random() < 0.4:
            apause(10, 30)
            print(f"{tag} 🔄 reset()", flush=True)
            send_tx(w3, acc, counter.functions.reset().build_transaction(
                get_tx_params(w3, acc.address, gas=60_000)), tag)
    except Exception as e:
        print(f"{tag} ❌ counter: {str(e)[:100]}", flush=True)


def act_event_emit(w3, acc, tag):
    print(f"{tag} 📡 Deploy EventEmitter", flush=True)
    c = w3.eth.contract(abi=EMITTER_ABI, bytecode=EMITTER_BYTECODE)
    signed = acc.sign_transaction(
        c.constructor().build_transaction(get_tx_params(w3, acc.address, gas=300_000))
    )
    try:
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
        ca = receipt.contractAddress
        link = f"https://explorer-sepolia.giwa.io/tx/{tx_hash.hex()}"
        print(f"{tag} {'✅' if receipt.status==1 else '❌'} Emitter | {link}", flush=True)
        if not ca or receipt.status != 1:
            return
        emitter = w3.eth.contract(ca, abi=EMITTER_ABI)
        n = random.randint(3, 6)
        for i in range(n):
            apause(8, 20)
            action = random.randint(1, 10)
            value  = random.randint(1, 10000)
            print(f"{tag} 📡 emit_activity({action}, {value})", flush=True)
            send_tx(w3, acc, emitter.functions.emit_activity(action, value).build_transaction(
                get_tx_params(w3, acc.address, gas=60_000)), tag)
        apause(8, 20)
        data = random.randbytes(32)
        print(f"{tag} 📡 ping()", flush=True)
        send_tx(w3, acc, emitter.functions.ping(data).build_transaction(
            get_tx_params(w3, acc.address, gas=60_000)), tag)
    except Exception as e:
        print(f"{tag} ❌ emitter: {str(e)[:100]}", flush=True)


def act_op_withdrawal(w3, acc, tag):
    print(f"{tag} 🌉 OP: initiateWithdrawal", flush=True)
    c = w3.eth.contract(L2_MSG_PASSER, abi=L2_MSG_PASSER_ABI)
    send_tx(w3, acc, c.functions.initiateWithdrawal(
        acc.address, 21_000, b''
    ).build_transaction(get_tx_params(w3, acc.address, gas=100_000)), tag)


def act_playground_claim(w3, acc, tag):
    bal = w3.eth.get_balance(acc.address)
    if bal < PLAYGROUND_FEE + int(0.001 * 1e18):
        print(f"{tag} 🎮 Playground: мало ETH для fee 0.001", flush=True)
        return
    # Simulate — reverts если интервал 30 дней не прошёл
    try:
        w3.eth.call({
            'to': PLAYGROUND_FAUCET,
            'data': '0xb19e5904',
            'from': acc.address,
            'value': PLAYGROUND_FEE,
        })
    except Exception:
        print(f"{tag} 🎮 Playground: интервал не прошёл (30 дней)", flush=True)
        return
    print(f"{tag} 🎮 Playground EAS claim (fee 0.001 ETH)", flush=True)
    tx = {
        **get_tx_params(w3, acc.address, value=PLAYGROUND_FEE, gas=250_000),
        'to': PLAYGROUND_FAUCET,
        'data': '0xb19e5904',
    }
    send_tx(w3, acc, tx, tag)


def act_create2_deploy(w3, acc, tag):
    count = random.randint(2, 4)
    bytecode_raw = bytes.fromhex(DUMMY_BYTECODE[2:])
    for i in range(count):
        salt = random.randint(1, 2**128).to_bytes(32, 'big')
        calldata = salt + bytecode_raw
        tx = {**get_tx_params(w3, acc.address, gas=300_000),
              'to': NICK_FACTORY, 'data': calldata}
        print(f"{tag} 🔧 CREATE2 [{i+1}/{count}]", flush=True)
        send_tx(w3, acc, tx, tag)
        if i < count - 1:
            apause(10, 30)


ALL_ACTIONS = [
    (act_wrap_eth,           10),
    (act_unwrap_eth,          7),
    (act_wrap_unwrap_cycle,   8),
    (act_self_transfer,       9),
    (act_weth_approve_revoke, 7),
    (act_weth_self_transfer,  5),
    (act_deploy,              8),
    (act_multi_deploy,        5),
    (act_deploy_interact,     6),
    (act_incremental,         5),
    (act_burst_transfer,      4),
    (act_multi_transfer,      3),
    (act_weth_chain,          7),
    (act_triple_deploy,       4),
    (act_contract_call,       6),
    # новые активности
    (act_deploy_erc20,        9),
    (act_deploy_nft,          8),
    (act_counter_spam,        7),
    (act_event_emit,          6),
    (act_op_withdrawal,       5),
    (act_create2_deploy,      6),
    (act_playground_claim,   10),  # GIWA Playground EAS (30 дней интервал, 0.001 ETH fee)
]


def process_wallet(pk, idx):
    w3  = make_w3()
    acc = Account.from_key(pk if pk.startswith('0x') else '0x' + pk)
    tag = f"[{acc.address[:8]}... w{idx+1:02d}]"
    try:
        bal = w3.eth.get_balance(acc.address)
    except Exception as e:
        print(f"{tag} ❌ RPC: {e}", flush=True); return

    print(f"\n{tag} 💰 {bal/1e18:.5f} ETH", flush=True)
    if bal < int(0.001 * 1e18):
        print(f"{tag} ⚠️ Мало баланса, пропуск", flush=True); return

    fns, weights = zip(*ALL_ACTIONS)
    chosen = random.choices(fns, weights=weights, k=random.randint(3, 5))
    for i, fn in enumerate(chosen):
        try:
            fn(w3, acc, tag)
        except Exception as e:
            print(f"{tag} ❌ {fn.__name__}: {str(e)[:100]}", flush=True)
        if i < len(chosen) - 1:
            apause(90, 420)
    print(f"{tag} ✅ Готово", flush=True)


print(f"✅ {len(PRIVATE_KEYS)} кошельков | Chain ID: {CHAIN_ID}", flush=True)
print("🔄 Запуск...\n", flush=True)

while True:
    pool = list(range(len(PRIVATE_KEYS)))
    while pool:
        pick = random.randrange(len(pool))
        idx  = pool.pop(pick)
        try:
            process_wallet(PRIVATE_KEYS[idx], idx)
        except Exception as e:
            print(f"[wallet-{idx}] ❌ {e}", flush=True)
        rand_sleep(54, 120)
    print("✅ Раунд завершён.\n", flush=True)
