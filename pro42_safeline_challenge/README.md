# 剑阁县人民政府 — 长亭雷池 SafeLine v2 挑战（468 → JWT）

> 复现对象：`spider research/其他/pro50 雷池 waf` · 技术分类：`waf` `wasm` · 状态：✅ 可复现（离线 9/9；wasm 10/10；线上 200，2026-11-14）

## 站点与目标

- 站点：`http://www.cnjg.gov.cn/`（四川省广元市剑阁县人民政府）
- 加密参数：响应 468 挑战页 → `sl-session` / `sl-challenge-jwt` → `sl_jwt_session`
- 目标链路：`GET 468 → issue → calc(data) → verify → cookie 回放 200`
- 挑战服务：云端 `challenge.rivers.chaitin.cn` 或站内 `/.safeline`（双模式）

## 技术要点

- 保护类型：长亭雷池 SafeLine v2 人机挑战；本站 level 1（无感、无滑块）
- 核心算法：`calc.wasm`（911B，wasm 导出 `reset/arg/calc/ret`）把 issue 的 `data[]` 算成 `result[]`
- 服务端只强校验 `issue_id`（一次性）和 `result`；`serials`、`input_type`、UA、环境分数均不参与判定
- 44 项环境检测（WebDriver/devtools 等）仅前端展示，`score=220` 提交仍 `verified:true`
- 易错点：verify 失败时 HTTP 仍是 200，必须解析 `data.verified`

## 逆向摘要

- 入口：468 页面尾部 `SafeLineChallenge("<client_id>", {host, local, level})`
- 还原过程：
  1. `POST {challenge}/challenge/v2/api/issue`，body `{client_id, level, input_type:""}` → `{data, issue_id}`
  2. `calc(data)`：`t=6^r` 后按 `v**3` 累加，逐步 XOR 下标与值，最后按 6bit 从高位输出
  3. `POST verify`：`issue_id + result + serials:[] + client{...}` → `{jwt, verified:true}`
  4. 携带 `sl-challenge-jwt` 重新 GET → 200 + `sl_jwt_session`（1 小时）
- JS→Python：`^`/`>>` 在本题数值范围（t<2^31）与 wasm i32 等价；输出是 0~63 的数字数组

## 复现

```bash
# 仅标准库；--wasm 需 node；--live 需网络
py main.py           # 4 组 calc 向量 + 协议结构
py main.py --wasm    # +1：Node 调 calc.wasm 逐字节对拍
py main.py --live    # +1：真实 468 → 200（可选）
```

| 输入 data | 期望 result |
|------|---------|
| `[99,35,92,48,...,62,50]`（14 项） | `[17,26,51,20]` |
| `[1,2,3,4,5,6,7,8,9]` | `[11,56,44]` |
| `[75,84,25,59,...,75,89]`（22 项） | `[19,42,2,22]` |
| `[(i*37+11)%100 for i in range(40)]` | `[38,10,25,20]` |

## 验证与实测

- 离线：`py main.py` 9/9；4 组 calc 结果与 `reference/calc.wasm` 逐字节一致
- 对拍：`py main.py --wasm` 10/10（911B 原模块）
- 线上：2026-11-14 `py main.py --live` 本地模式 `468→200`（77KB）；源项目 2026-11-13 云端/本地双模式均通过
- 本仓库不保存真实 `client_id`/`issue_id`/JWT/Cookie/代理配置

## 备注

- 失效风险：`client_id` 的 `_38` 后缀可能是版本/难度标识；`calc.wasm` 与 verify 字段随 SafeLine 升级可能变化
- 坑：`issue_id` 一次性，重放返回 400；回放必须同时带 `sl-challenge-jwt` + `sl-challenge-server=<cloud|local>`，否则仍 468；云端与站内 JWT 不可混用；错误 result 仍返回 HTTP 200
- 范围：仅挑战层；雷池语义引擎仍会拦截 SQL 注入/XSS 等攻击特征，正常低频采集不受影响
- 第三方文件：`reference/calc.wasm` 版权归长亭科技 SafeLine，仅作学习研究归档
