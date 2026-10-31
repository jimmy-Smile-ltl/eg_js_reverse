# -*- coding: utf-8 -*-
"""
BOSS直聘 __zp_stoken__ 纯算法复现（标准库，离线自验证）

链路:
    302 挑战 (seed/ts/name) -> JSVMP 生成 token -> 带上 Cookie 重放 200

    token = "523e" + "g" + base64(UTF8变体(变换链(head + X)))
    X[i] = (Y[i] + 3) ^ ord(str(key)[i % 5])
    Y    = [56] + t[k]+(k 或 2k) + ENV(186 项环境指纹)
    t    = [4] + ord("523e,") + ord(seed) + [240, ts_sec 4B, LCG()*100]

运行:
    py main.py              # 3 组固定向量 + 解码结构断言
    py main.py --gen SEED TS   # 生成一条当前时间的 token（需配合同轮 seed）

样例为 2026-08-29 线上版本 393d5208 的脱敏测试向量（seed 与时间均已过期）。
"""
import base64
import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))

_PREFIX_CHARS = [4, 53, 50, 51, 101, 44]   # [4] + ord("523e,")
_TOKEN_PREFIX = "523e" + "g"
_T_EXTRA_CONST = 240
_LCG_A, _LCG_C, _LCG_M, _LCG_DIV = 1664525, 1013904223, 2 ** 32, 2147483647

# 186 项生产环境指纹常量（沙箱固定值）
# env[113:117] 是生成时刻秒级时间戳（大端），env[151:154] 为其副本，运行时同步。
_ENV_CONST = json.load(open(os.path.join(HERE, "env_prod_const.json"), "r", encoding="utf-8"))


class LCG:
    """window.s 伪随机：s=(s*a+c)%2^32，输出 (s & 0x7FFFFFFF)/0x7FFFFFFF。"""

    def __init__(self, seed=None):
        self.s = seed if seed is not None else random.getrandbits(32)

    def next(self):
        self.s = (self.s * _LCG_A + _LCG_C) % _LCG_M
        return (self.s & _LCG_DIV) / _LCG_DIV


def utf8_2byte(chars):
    """VM 的 UTF-8 变体：<128 单字节，其余固定两字节（overlong 形式）。"""
    out = bytearray()
    for c in chars:
        if c < 128:
            out.append(c)
        else:
            out.append(0xC0 | (c >> 6))
            out.append(0x80 | (c & 63))
    return bytes(out)


def _decode_utf8_2byte(data):
    out, i = [], 0
    while i < len(data):
        b = data[i]
        if b < 0x80:
            out.append(b)
            i += 1
        else:
            out.append(((b & 0x1F) << 6) | (data[i + 1] & 0x3F))
            i += 2
    return out


def generate_token(seed, ts, lcg_seed=None, rand_fn=None, env_ts=None):
    """生成 __zp_stoken__。

    seed     : 302 挑战 URL 的 seed（44 字符 base64）
    ts       : 毫秒时间戳（东八区原始值）
    lcg_seed : 调试用固定 LCG 初始状态；None = 随机
    rand_fn  : 调试用替代 Math.random；None = 真随机
    env_ts   : 环境时间戳（秒）；None = 当前时间
    """
    rand = rand_fn or random.random
    lcg = LCG(lcg_seed)
    ts_sec = ts // 1000

    rand0_99 = int(lcg.next() * 100)

    t = list(_PREFIX_CHARS) + [ord(c) for c in seed]
    t += [_T_EXTRA_CONST,
          (ts_sec >> 24) & 0xFF, (ts_sec >> 16) & 0xFF,
          (ts_sec >> 8) & 0xFF, ts_sec & 0xFF, rand0_99]
    assert len(t) == 56, "t 长度 %d != 56（seed 应为 44 字符）" % len(t)

    y2 = [t[k] + (k if k % 2 == 0 else 2 * k) for k in range(56)]
    env = list(_ENV_CONST)
    now_sec = int(time.time()) if env_ts is None else int(env_ts)
    env[113:117] = [(now_sec >> 24) & 0xFF, (now_sec >> 16) & 0xFF,
                    (now_sec >> 8) & 0xFF, now_sec & 0xFF]
    env[151], env[152], env[153] = env[115], env[116], env[117]
    y2 += env
    assert len(y2) == 242, "Y2 长度 %d != 242（环境常量应为 186 项）" % len(y2)

    y = [56] + y2
    key = int(lcg.next() * 50000) + int(rand() * 50000)
    key_str = str(key)

    x = [(y[i] + 3) ^ ord(key_str[i % 5]) for i in range(243)]
    head = [192 + (key >> 16), (key >> 8) & 0xFF, key & 0xFF]
    payload_chars = [((((a + 12) ^ 3) + 5) ^ 1) for a in head + x]

    return _TOKEN_PREFIX + base64.b64encode(utf8_2byte(payload_chars)).decode()


def decode_token(token):
    """generate_token 的逆过程，用于结构验证（不依赖 seed/ts 原文）。"""
    assert token.startswith(_TOKEN_PREFIX), "前缀不是 523eg"
    chars = _decode_utf8_2byte(base64.b64decode(token[5:]))
    a0 = [((((p ^ 1) - 5) ^ 3) - 12) for p in chars]
    assert len(a0) == 246, "payload 长度 %d != 246" % len(a0)

    head, x = a0[:3], a0[3:]
    key = ((head[0] - 192) << 16) | (head[1] << 8) | head[2]
    key_str = str(key)
    y = [(x[i] ^ ord(key_str[i % 5])) - 3 for i in range(243)]
    assert y[0] == 56, "Y[0] 应为 56，实际 %d" % y[0]

    y2 = y[1:]
    t = [y2[k] - (k if k % 2 == 0 else 2 * k) for k in range(56)]
    assert t[:6] == _PREFIX_CHARS, "t 前缀不匹配"
    assert t[50] == _T_EXTRA_CONST, "t[50] 应为 240"
    ts_sec = (t[51] << 24) | (t[52] << 16) | (t[53] << 8) | t[54]

    env = y2[56:]
    assert len(env) == 186, "env 长度 %d != 186" % len(env)
    env_ts = (env[113] << 24) | (env[114] << 16) | (env[115] << 8) | env[116]
    assert (env[151], env[152], env[153]) == (env[115], env[116], env[117]), "时间副本未同步"

    return {
        "seed": "".join(chr(c) for c in t[6:50]),
        "ts_sec": ts_sec,
        "t55": t[55],
        "key": key,
        "env_ts": env_ts,
        "env": env,
    }


SEED = "EXAMPLE_EXPIRED_SEED_00000000000000000000000"
ENV_TS = 1788022897

# (seed, ts_ms, lcg_seed, rand_seed, env_ts, 期望 token)
# 期望值由已线上验证的 JSVMP 生产链在固定随机源下生成（2026-08-29 版本）
SAMPLE_CASES = [
    (SEED, 1781494113632, 123456789, 42, ENV_TS,
     "523egw5Icw4IeTxwTHGsVwohxwoxpeWVyXHVVZ2hpbXPDimpWZ1VaccKRaH1Zd1dwVXNde8OEc8OFfcOLesOJacK5ZcKwxLHDt2DDvsOBwrPDh8KfRDjDi8SHxYTFgsWJxYrCuMKkWsOJw5/DhMKWxYLFicOkwrTDocOKxYnFiMWJxYTFgsWJxYhAT0RAUU5HNcK0TkM1T0jDgHHDgMOBw5HDi8ODH8OGJsORf8OAJcOAc0giJRVubhMWIRwfF2QVYm5xZxUWHmIdFhxubmZvZWVxa2xxNzTDhMOwOMOCxIMyw4bDqxPDgsOcGsOOw4g0w5Vowrw3UsOHwqosMkJFQEPDh8WERUBLQkdFT04pUURDQEJCTUNOOUIxw5ZpwrU3VMOAxI4pSk1GS0dHOmdMQk1GQ05CS0RGOkJKOjlFw4DDqsOFw6pOQg=="),
    (SEED, 1781494173632, 987654321, 7, ENV_TS,
     "523egw5XDpcO8H0kfHBhqG8KLYsKIZH9iwoFYcFtkZ2VofcONaVJmW11iwo1tc1Z4U3VbcFZ/w4l9w4J2w497w49mwrppwrXEp8O0b8O6w7Bew4TCkEA9w4XEhMWLxYbFhMWAwrvCq17DhMOZw4fCncWGxYTDrsK3w5LDjsWExYLFhsWLxYbFhMWCQ0BARUdRSDnCuURAPktNw4puw4/CvcOMw4XDgBDDgifDh3zDjynDhX1LMSkQZHEcEhwWHBhgEGhxYmMQHCFxIRcWcWVibmtiYm9xZzQ7w4DDtTLDhcSMNsOHw6UQw5HDmBvDhMOLO8OZbcK2NGHDg8KrJjVRSUVNw4TFi0lFRUVISU5EJkJAQkpFUVFCRDZRLcOXb8KyOFDDhcSEJklRR0VESD5mRkVGQkJERURARzBFST40S8ODw6nDicOrREU="),
    (SEED, 1781494233632, 555555555, 2026, ENV_TS,
     "523egw5XCusKTHEkaHx1tG8KOZcKNZ39nfl1zW2VkYGt9w4xmU2lbXGXCiGpzU3tSclt5WX7Dhn3Dh3nDjnjDj2PCvWTCssSnw7Vsw7vEt8OMw4XCk0U6w4XEhcWIxYfFh8WAwr7CqF/Dh8OZw4LCmsWHxYfDrsKyw5XDj8WHxYLFg8WIxYfFh8WCRkNFQkdISzTCtkRJQUpKw4prw4zCuMOPw4XDiRPDgyTDh33DjCTDgn1OLiQTZGgfEx8WHRtlE2hoZWITHBhuHBQWaGJjcWtnZW5uZzU4w4XDsjLDhMSPN8OEw6UZw47DnRjDhMOOOMOUasK2NV7DgsKoJjROREJNw4XFiERCRURLRFFEI0VFRUpETkxFRDNOKMOUb8K3O1XDgsSEI0ZMREVFSz9pRkRJQ0VEREdFRDBERj83S8OGw6bDhMOoREQ="),
]


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "--gen":
        print(generate_token(sys.argv[2], int(sys.argv[3])))
        return

    passed = 0
    for seed, ts, lcg_seed, rand_seed, env_ts, expected in SAMPLE_CASES:
        got = generate_token(seed, ts, lcg_seed, random.Random(rand_seed).random, env_ts)
        ok = got == expected
        info = decode_token(got)
        ok = ok and info["seed"] == seed and info["ts_sec"] == ts // 1000 \
            and info["env_ts"] == env_ts and 0 <= info["t55"] < 100
        passed += ok
        print("[%s] seed=%s... ts=%d lcg=%d rand=%d"
              % ("PASS" if ok else "FAIL", seed[:12], ts, lcg_seed, rand_seed))
        print("       token(%d)=%s..." % (len(got), got[:48]))
        print("       decode: key=%d env_ts=%d t55=%d" % (info["key"], info["env_ts"], info["t55"]))
        if not ok:
            print("       expected(%d)=%s..." % (len(expected), expected[:48]))
    print("\n%d/%d 通过" % (passed, len(SAMPLE_CASES)))
    if passed != len(SAMPLE_CASES):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
