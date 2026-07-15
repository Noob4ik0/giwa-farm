import os, random, time, sys
from web3 import Web3
from eth_account import Account
from web3.middleware import ExtraDataToPOAMiddleware

sys.stdout.reconfigure(line_buffering=True)
print("🚀 GIWA Chain Farm v1 запущен!", flush=True)

RPC      = "https://sepolia-rpc.giwa.io"
CHAIN_ID = 91342

WETH_ADDR = "0x4200000000000000000000000000000000000006"  # 18 dec OP Stack predeploy
SPENDER   = WETH_ADDR

import sys as _sys; _sys.path.insert(0, '/root/bin')
from proxy_utils import load_proxies, find_working_proxy
PROXIES = load_proxies()

import os as _os
from dotenv import load_dotenv as _load_dotenv
_load_dotenv(_os.path.join(_os.path.dirname(__file__), '.env'))
_raw_keys = _os.getenv("PRIVATE_KEYS", "")
PRIVATE_KEYS = [k.strip() for k in _raw_keys.split(",") if k.strip()]

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


def make_w3(proxy_url):
    w3 = Web3(Web3.HTTPProvider(RPC, request_kwargs={
        'proxies': {'http': proxy_url, 'https': proxy_url},
        'timeout': 30,
    }))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3


def get_tx_params(w3, sender, value=0, gas=300_000):
    try:
        block    = w3.eth.get_block('latest')
        base_fee = block.get('baseFeePerGas')
        if base_fee:
            max_fee  = int(base_fee * 1.5) + w3.to_wei(0.001, 'gwei')
            priority = int(w3.to_wei(random.uniform(0.001, 0.005), 'gwei'))
            return {'from': sender, 'nonce': w3.eth.get_transaction_count(sender),
                    'maxFeePerGas': max_fee, 'maxPriorityFeePerGas': priority,
                    'chainId': CHAIN_ID, 'value': value, 'gas': gas}
    except Exception:
        pass
    return {'from': sender, 'nonce': w3.eth.get_transaction_count(sender),
            'gasPrice': int(w3.eth.gas_price * 1.3),
            'chainId': CHAIN_ID, 'value': value, 'gas': gas}


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
    reserve = int(0.003 * 1e18)
    if bal < reserve + int(0.0001 * 1e18):
        print(f"{tag} Wrap: мало ETH", flush=True); return
    amt = random.randint(int(0.0001 * 1e18), min(int(0.002 * 1e18), bal - reserve))
    c   = w3.eth.contract(WETH_ADDR, abi=WETH_ABI)
    print(f"{tag} 🔄 Wrap {amt/1e18:.5f} ETH → WETH", flush=True)
    send_tx(w3, acc, c.functions.deposit().build_transaction(
        get_tx_params(w3, acc.address, value=amt)), tag)


def act_unwrap_eth(w3, acc, tag):
    c    = w3.eth.contract(WETH_ADDR, abi=WETH_ABI)
    wbal = c.functions.balanceOf(acc.address).call()
    if wbal < int(0.00005 * 1e18):
        print(f"{tag} Unwrap: мало WETH", flush=True); return
    amt = random.randint(int(0.00005 * 1e18), min(wbal, int(0.002 * 1e18)))
    print(f"{tag} 🔄 Unwrap {amt/1e18:.5f} WETH → ETH", flush=True)
    send_tx(w3, acc, c.functions.withdraw(amt).build_transaction(
        get_tx_params(w3, acc.address)), tag)


def act_wrap_unwrap_cycle(w3, acc, tag):
    act_wrap_eth(w3, acc, tag)
    apause(90, 300)
    act_unwrap_eth(w3, acc, tag)


def act_self_transfer(w3, acc, tag):
    bal     = w3.eth.get_balance(acc.address)
    reserve = int(0.003 * 1e18)
    if bal < reserve:
        print(f"{tag} Self-transfer: мало ETH", flush=True); return
    amt = random.randint(int(0.00005 * 1e18), min(int(0.001 * 1e18), bal - reserve))
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
    if wbal < int(0.00005 * 1e18):
        print(f"{tag} WETH transfer: мало WETH, оборачиваем", flush=True)
        act_wrap_eth(w3, acc, tag)
        apause(15, 45)
        wbal = c.functions.balanceOf(acc.address).call()
        if wbal < int(0.00005 * 1e18):
            return
    amt = random.randint(int(0.00005 * 1e18), min(wbal, int(0.001 * 1e18)))
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
    for base in [0.00005, 0.00015, 0.0005]:
        bal = w3.eth.get_balance(acc.address)
        amt = int((base + random.uniform(0, base * 0.5)) * 1e18)
        if amt > bal - int(0.003 * 1e18):
            continue
        tx = {**get_tx_params(w3, acc.address, value=amt, gas=21_000), 'to': acc.address}
        print(f"{tag} 📤 Incremental {amt/1e18:.6f} ETH", flush=True)
        send_tx(w3, acc, tx, tag)
        apause(45, 120)


def act_burst_transfer(w3, acc, tag):
    count = random.randint(4, 6)
    for j in range(count):
        bal = w3.eth.get_balance(acc.address)
        amt = random.randint(int(0.00001 * 1e18), int(0.00008 * 1e18))
        if amt > bal - int(0.003 * 1e18):
            break
        tx = {**get_tx_params(w3, acc.address, value=amt, gas=21_000), 'to': acc.address}
        print(f"{tag} ⚡ Burst [{j+1}/{count}]", flush=True)
        send_tx(w3, acc, tx, tag)
        time.sleep(random.randint(8, 25))
    bal = w3.eth.get_balance(acc.address)
    big = random.randint(int(0.0005 * 1e18), int(0.002 * 1e18))
    if big < bal - int(0.003 * 1e18):
        tx = {**get_tx_params(w3, acc.address, value=big, gas=21_000), 'to': acc.address}
        print(f"{tag} ⚡ Burst final big", flush=True)
        send_tx(w3, acc, tx, tag)


def act_multi_transfer(w3, acc, tag):
    count   = random.randint(3, 5)
    reserve = int(0.003 * 1e18)
    for i in range(count):
        bal = w3.eth.get_balance(acc.address)
        amt = random.randint(int(0.00005 * 1e18), int(0.0003 * 1e18))
        if amt > bal - reserve:
            break
        tx = {**get_tx_params(w3, acc.address, value=amt, gas=21_000), 'to': acc.address}
        print(f"{tag} 📤 Multi-transfer [{i+1}/{count}] {amt/1e18:.6f} ETH", flush=True)
        send_tx(w3, acc, tx, tag)
        apause(20, 60)


def act_weth_chain(w3, acc, tag):
    """Wrap ETH → WETH self-transfer → unwrap in one action."""
    bal = w3.eth.get_balance(acc.address)
    reserve = int(0.004 * 1e18)
    if bal < reserve + int(0.0005 * 1e18):
        print(f"{tag} WETH chain: мало ETH", flush=True); return
    amt = random.randint(int(0.0005 * 1e18), min(int(0.003 * 1e18), bal - reserve))
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


ALL_ACTIONS = [
    (act_wrap_eth,           11),
    (act_unwrap_eth,          8),
    (act_wrap_unwrap_cycle,   9),
    (act_self_transfer,      10),
    (act_weth_approve_revoke, 8),
    (act_weth_self_transfer,  5),
    (act_deploy,              9),
    (act_multi_deploy,        6),
    (act_deploy_interact,     7),
    (act_incremental,         6),
    (act_burst_transfer,      4),
    (act_multi_transfer,      3),
    (act_weth_chain,          8),
    (act_triple_deploy,       5),
    (act_contract_call,       7),
]


def process_wallet(pk, proxy_url, idx):
    w3  = make_w3(proxy_url)
    acc = Account.from_key(pk if pk.startswith('0x') else '0x' + pk)
    tag = f"[{acc.address[:8]}... w{idx+1:02d}]"
    try:
        bal = w3.eth.get_balance(acc.address)
    except Exception as e:
        print(f"{tag} ❌ RPC: {e}", flush=True); return

    print(f"\n{tag} 💰 {bal/1e18:.5f} ETH", flush=True)
    if bal < int(0.003 * 1e18):
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
        pick  = random.randrange(len(pool))
        idx   = pool.pop(pick)
        proxy = PROXIES[idx % len(PROXIES)] if PROXIES else None
        try:
            process_wallet(PRIVATE_KEYS[idx], proxy, idx)
        except Exception as e:
            _msg = str(e).lower()
            if any(x in _msg for x in ["proxy","connect","timeout","reset","refused","network","ssl"]):
                _new = find_working_proxy(exclude=proxy)
                if _new and _new != proxy:
                    print(f"[wallet-{idx}] 🔄 прокси сменён → {_new.split('@')[-1]}", flush=True)
                    try:
                        process_wallet(PRIVATE_KEYS[idx], _new, idx)
                    except Exception as e2:
                        print(f"[wallet-{idx}] ❌ {e2}", flush=True)
                else:
                    print(f"[wallet-{idx}] ❌ {e}", flush=True)
            else:
                print(f"[wallet-{idx}] ❌ {e}", flush=True)
        rand_sleep(54, 120)
    print("✅ Раунд завершён.\n", flush=True)
