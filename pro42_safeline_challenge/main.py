# -*- coding: utf-8 -*-
"""
剑阁县人民政府 — 长亭雷池 SafeLine v2 人机挑战（468 → JWT）

用法:
    py main.py           # 离线：calc 向量 + 协议结构（标准库，无网络）
    py main.py --wasm    # 追加：Node 调 reference/calc.wasm 逐向量对拍
    py main.py --live    # 追加：对目标站点走一次 468→issue→verify→200

协议（逆向自 challenge.js / calc.js / calc.wasm）:
    GET  /                                  -> 468 + sl-session + client_id
    POST {challenge}/challenge/v2/api/issue -> {"data": [...], "issue_id": "..."}
    result = calc(data)                     # calc.wasm 等价算法
    POST {challenge}/challenge/v2/api/verify -> {"jwt": "...", "verified": true}
    GET  / + Cookie sl-challenge-jwt
           + Cookie sl-challenge-server     -> 200 + sl_jwt_session（1h）

关键事实:
    - level 1 无滑块；serials=[]、input_type="" 即可
    - verify 只强校验 issue_id（一次性）+ result；client 环境分数不参与服务端判定
    - verify 失败时 HTTP 仍为 200，必须看 data.verified
    - 云端 challenge.rivers.chaitin.cn 与站内 /.safeline 签发的 JWT 不能混用

本文件不包含任何真实 client_id / issue_id / JWT / Cookie / 代理配置。
"""
from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import Cookie, CookieJar

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WASM_JS = os.path.join(BASE_DIR, "reference", "wasm_check.mjs")

SITE_URL = "http://www.cnjg.gov.cn/"
DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36")
DEFAULT_CHALLENGE_HOST = "challenge.rivers.chaitin.cn"

# (data, expected result) — 4 组均与 calc.wasm 逐字节对拍
SAMPLE_CASES = [
    ([99, 35, 92, 48, 61, 31, 18, 43, 3, 54, 48, 22, 62, 50],
     [17, 26, 51, 20]),
    ([1, 2, 3, 4, 5, 6, 7, 8, 9], [11, 56, 44]),
    ([75, 84, 25, 59, 66, 28, 49, 58, 61, 15, 15, 36, 39, 70, 59, 99,
      60, 5, 36, 3, 75, 89], [19, 42, 2, 22]),
    ([(i * 37 + 11) % 100 for i in range(40)], [38, 10, 25, 20]),
]

CHALLENGE_HTML = (
    '<script>SafeLineChallenge("deadbeefdeadbeefdeadbeefdeadbeef_38", '
    '{host: "challenge.rivers.chaitin.cn", local: false, level: "1"})</script>'
)


# ---------------------------------------------------------------- 核心算法

def calc(data):
    """calc.wasm 的等价实现（data 为 0~99 的整数数组）。

    wasm 导出 reset/arg/calc/ret：arg 逐个写入输入，calc 计算并返回长度，
    ret 从输出栈弹出 6bit 数字。下面的算术与 JS 兼容实现逐字节一致。
    """
    t = 1
    n = sum(data)
    r = (6 + len(data) + n) % 6 + 6
    for _ in range(r):
        t *= 6
    if t < 6666:
        t *= len(data)
    if t > 0x3F940AA:
        t //= len(data)
    for idx, value in enumerate(data):
        t += value ** 3
        t ^= idx
        t ^= value + idx
    result = []
    while t > 0:
        result.insert(0, t & 63)
        t >>= 6
    return result


# ---------------------------------------------------------------- 协议结构

def parse_challenge(html: str):
    """从 468 页面提取 SafeLineChallenge(client_id, {host, local, level})。"""
    m = re.search(r'SafeLineChallenge\(\s*"([^"]+)"\s*,\s*(\{.*?\})\s*\)', html, re.S)
    if not m:
        return None
    client_id, args = m.group(1), m.group(2)
    host_m = re.search(r'host\s*:\s*"([^"]+)"', args)
    local_m = re.search(r"local\s*:\s*(true|false)", args)
    level_m = re.search(r'level\s*:\s*"?(\d+)"?', args)
    return {
        "client_id": client_id,
        "host": host_m.group(1) if host_m else DEFAULT_CHALLENGE_HOST,
        "local": bool(local_m and local_m.group(1) == "true"),
        "level": int(level_m.group(1)) if level_m else 1,
    }


def build_issue_payload(client_id: str, level: int = 1):
    return {"client_id": client_id, "level": level, "input_type": ""}


def build_verify_payload(issue_id: str, result, user_agent: str = DEFAULT_UA,
                         visitor_id: str = None):
    visitor_id = visitor_id or "".join(random.choices("0123456789abcdef", k=32))
    return {
        "issue_id": issue_id,
        "result": result,
        "serials": [],
        "input_type": "",
        "client": {
            "userAgent": user_agent,
            "platform": "Win32",
            "language": "zh-CN,zh,en",
            "vendor": "Google Inc.",
            "screen": [1920, 1080],
            "visitorId": visitor_id,
            "score": 0,
            "target": [],
        },
    }


# ---------------------------------------------------------------- 可选：wasm 对拍

def wasm_results(cases):
    """调用 reference/wasm_check.mjs，返回与 cases 对应的 result 列表。"""
    proc = subprocess.run(
        ["node", WASM_JS],
        input=json.dumps(cases),
        capture_output=True, text=True, timeout=60, cwd=BASE_DIR,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-500:])
    return json.loads(proc.stdout.strip().splitlines()[-1])


# ---------------------------------------------------------------- 可选：真实挑战

def _set_cookie(jar: CookieJar, name: str, value: str, domain: str):
    jar.set_cookie(Cookie(
        version=0, name=name, value=value, port=None, port_specified=False,
        domain=domain, domain_specified=True, domain_initial_dot=False,
        path="/", path_specified=True, secure=False, expires=None,
        discard=True, comment=None, comment_url=None,
        rest={"HttpOnly": None}, rfc2109=False,
    ))


def _http(opener, url, data=None, headers=None, timeout=20):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.status, resp.read(), resp.headers
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.headers


def _absorb_cookies(jar, headers, domain):
    for raw in headers.get_all("Set-Cookie") or []:
        m = re.match(r"\s*([^=]+)=([^;]*)", raw)
        if m:
            _set_cookie(jar, m.group(1).strip(), m.group(2).strip(), domain)


def _post_json(opener, url, payload, headers):
    status, raw, _ = _http(
        opener, url,
        data=json.dumps(payload).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
    )
    try:
        return status, json.loads(raw.decode("utf-8"))
    except ValueError:
        return status, {}


def live_check(site_url: str = SITE_URL, prefer_local: bool = True):
    """走一次完整的 468 → issue → calc → verify → 200 流程。

    返回 (status, body_len, has_session, mode)；不打印/保存任何会话值。
    """
    parts = urllib.parse.urlsplit(site_url)
    origin = f"{parts.scheme}://{parts.netloc}"
    host = parts.hostname or ""
    ua = DEFAULT_UA
    headers = {"User-Agent": ua, "Accept-Language": "zh-CN,zh;q=0.9"}

    site_jar = CookieJar()
    site = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(site_jar))
    status, body, resp_headers = _http(site, site_url, headers=headers)
    _absorb_cookies(site_jar, resp_headers, host)
    html = body.decode("utf-8", "replace")
    info = parse_challenge(html)
    if not info:
        raise RuntimeError(f"未找到 SafeLineChallenge（HTTP {status}）")

    ch = urllib.request.build_opener()
    modes = ["local", "cloud"] if prefer_local else ["cloud", "local"]
    last = None
    for mode in modes:
        base = f"{origin}/.safeline" if mode == "local" else f"https://{info['host']}"
        try:
            st, issue = _post_json(
                ch, base + "/challenge/v2/api/issue",
                build_issue_payload(info["client_id"], info["level"]), headers)
            if st == 200 and issue.get("code") == 200:
                data = issue["data"]
                result = calc(data["data"])
                st2, verify = _post_json(
                    ch, base + "/challenge/v2/api/verify",
                    build_verify_payload(data["issue_id"], result, ua), headers)
                if st2 == 200 and verify.get("code") == 200 and \
                        verify.get("data", {}).get("verified"):
                    jwt = verify["data"]["jwt"]
                    _set_cookie(site_jar, "sl-challenge-jwt", jwt, host)
                    _set_cookie(site_jar, "sl-challenge-server", mode, host)
                    status2, body2, headers2 = _http(site, site_url, headers=headers)
                    _absorb_cookies(site_jar, headers2, host)
                    has_session = any(c.name == "sl_jwt_session" for c in site_jar)
                    return status2, len(body2), has_session, mode
            last = (st, issue)
        except Exception as exc:            # noqa: BLE001 - 备用路线
            last = exc
    raise RuntimeError(f"挑战未通过: {last}")


# ---------------------------------------------------------------- 主流程

def main():
    passed = 0
    total = 0

    def check(ok, label, detail=""):
        nonlocal passed, total
        total += 1
        passed += ok
        print("[%s] %s %s" % ("PASS" if ok else "FAIL", label, detail))

    # 1. 4 组确定性 calc 向量
    for i, (data, expected) in enumerate(SAMPLE_CASES, 1):
        got = calc(data)
        check(got == expected, "calc vector #%d" % i,
              "(len %d -> %s)" % (len(data), got))

    # 2. 输出范围/确定性
    got = calc(SAMPLE_CASES[0][0])
    check(all(0 <= v <= 63 for v in got), "result digits 0..63", "(6-bit)")
    check(calc(SAMPLE_CASES[0][0]) == got, "deterministic", "(same input)")

    # 3. 挑战页解析
    info = parse_challenge(CHALLENGE_HTML)
    check(info is not None and info["client_id"].endswith("_38")
          and info["host"] == DEFAULT_CHALLENGE_HOST
          and info["level"] == 1 and info["local"] is False,
          "parse challenge", "(client_id/host/local/level)")

    # 4. issue/verify 报文结构
    issue = build_issue_payload("example_38", 1)
    verify = build_verify_payload("issue_example", [1, 2, 3], visitor_id="a" * 32)
    check(set(issue) == {"client_id", "level", "input_type"}
          and issue["input_type"] == "",
          "issue payload", "(client_id/level/input_type)")
    check(set(verify) == {"issue_id", "result", "serials", "input_type", "client"}
          and verify["serials"] == [] and verify["input_type"] == ""
          and set(verify["client"]) == {"userAgent", "platform", "language",
                                        "vendor", "screen", "visitorId",
                                        "score", "target"}
          and len(verify["client"]["visitorId"]) == 32,
          "verify payload", "(serials/input_type/client)")

    # 5. 可选：calc.wasm 对拍
    if "--wasm" in sys.argv:
        try:
            results = wasm_results([c[0] for c in SAMPLE_CASES])
            ok = results == [c[1] for c in SAMPLE_CASES]
            check(ok, "wasm cross-check", "(4 vectors, 911B module)")
        except Exception as exc:            # noqa: BLE001 - 备份路线
            check(False, "wasm cross-check", "(%s)" % exc)
    else:
        print("[SKIP] --wasm cross-check (add --wasm, needs node)")

    # 6. 可选：真实挑战（默认不执行）
    if "--live" in sys.argv:
        try:
            status, size, has_session, mode = live_check()
            check(status == 200 and has_session, "live challenge",
                  "(HTTP %d, %d bytes, %s mode)" % (status, size, mode))
        except Exception as exc:            # noqa: BLE001 - 备用路线
            check(False, "live challenge", "(%s)" % exc)
    else:
        print("[SKIP] --live challenge (add --live, needs network)")

    print("\n%d/%d passed" % (passed, total))
    if passed != total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
