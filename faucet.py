import os, json, requests, sys
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "faucet.env"))

COOKIE     = os.getenv("LAMBDA_AUTH_COOKIE", "")
STATE_FILE = os.path.join(os.path.dirname(__file__), "faucet_state.json")
API_URL    = "https://console-api.lambda256.io/be/v4.0/faucet/charge"

WALLETS = [
    "0x5A6874Ed748Fedd00383c0E11AeBfeb6E989e677",  # 09
    "0x8E7E0F5d39Fb2Fb0f45592F01e9495E28737F3E7",  # 10
    "0x6Cf89C5c3fB9041a914D3286A9544d2AE7821Ff6",  # 11
    "0x9F33b3DE2C80712E05CA4F525AaDcAA512D6AD67",  # 12
    "0x30065ACe6E3246ef9F41244967393Ad0509FA293",  # 13
    "0x86D33c4DbE6b14f39468aaDCdA87b036a0D6141A",  # 14
    "0x001571d73C403Bf4F56B92228Dca502f3Aeef391",  # 15
    "0x9340E246741365bE5d1F425a6fd81DeE3205A919",  # 16
    "0x9b74d2ea2D537e70412E198161b37384A256170e",  # 17
    "0xDd216D15692BC00c4D7c58bF92E4F08132489914",  # 18
    "0xDC7D224988738abB7e3147A2c403591E1FCc1690",  # 19
    "0x24b420bE218162EB93bD5cA67862bC1Df899aB96",  # 20
    "0x9e5fbA0c5C1D8Fe639F338b4568b99557744A21b",  # 21
    "0x0b9974FcB60C7312bf7130289ccE86ff2bc81dBD",  # 22
    "0x2cBdd0Cd7a8F5Ce81eA0F8bF68965117A3ae3d3f",  # 23
    "0xc621011325430a7B273C4Db794821b6AcDb29123",  # 24
    "0xb9CAce7a63632f27d566E12985E9f2c89Df32044",  # 25
    "0x2D6BcF2ea3D5be0B598eFf4644f18F23A4de7A2b",  # 26
    "0x7eBdDC1EF34750d4CFe2aF81864dAFA7Dc51362C",  # 27
    "0xd471edeF77497dc4532e5d974C7D318205F3323D",  # 28
    "0x2faa5b515F77d72C09e3eD57fdf9A5C4D2605000",  # 29
    "0x3C04F01222982d40758221304EBC9888CD176cAc",  # 30
]

def ts():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"next_index": 0, "claimed": [], "cycle": 1}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def claim(address):
    r = requests.post(API_URL,
        json={"address": address, "protocol": "giwa", "network": "sepolia"},
        cookies={"lambdaAuth": COOKIE},
        headers={"Content-Type": "application/json",
                 "Origin": "https://faucet.lambda256.io",
                 "Referer": "https://faucet.lambda256.io/giwa-sepolia"},
        timeout=30)
    return r.status_code, r.text

def main():
    if not COOKIE:
        print(f"[{ts()}] COOKIE ПУСТАЯ — обнови LAMBDA_AUTH_COOKIE в faucet.env!")
        print(f"[{ts()}] Как: зайди на https://faucet.lambda256.io → DevTools → Cookies → lambdaAuth")
        sys.exit(2)

    state = load_state()
    idx   = state["next_index"]
    cycle = state.get("cycle", 1)

    # Бесконечный цикл: когда все пройдены — начинаем сначала
    if idx >= len(WALLETS):
        print(f"[{ts()}] Цикл #{cycle} завершён! Начинаю цикл #{cycle + 1}")
        state["next_index"] = 0
        state["cycle"]      = cycle + 1
        idx   = 0
        cycle = cycle + 1
        save_state(state)

    address    = WALLETS[idx]
    wallet_num = idx + 9

    print(f"[{ts()}] Цикл #{cycle} | Кошелёк [{wallet_num:02d}] {address}")

    status, body = claim(address)

    if status == 200 and "txHash" in body:
        tx = json.loads(body)["txHash"]
        print(f"[{ts()}] OK | txHash: {tx}")
        state["claimed"].append({"cycle": cycle, "index": wallet_num,
                                 "address": address, "txHash": tx, "date": ts()})
        state["next_index"] = idx + 1
        save_state(state)

    elif "ALREADY_CLAIMED" in body or "DAILY_LIMIT" in body:
        print(f"[{ts()}] Уже взято сегодня — попробую завтра")

    elif status in (401, 403) or "Unauthorized" in body or "unauthorized" in body.lower():
        print(f"[{ts()}] КУКА УСТАРЕЛА — обнови LAMBDA_AUTH_COOKIE в faucet.env!")
        print(f"[{ts()}] Как: зайди на https://faucet.lambda256.io → Google → DevTools → Cookies → lambdaAuth")
        sys.exit(2)

    else:
        print(f"[{ts()}] Ошибка {status}: {body[:200]}")
        sys.exit(1)

if __name__ == "__main__":
    main()
