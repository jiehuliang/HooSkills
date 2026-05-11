# 第十周学习笔记：RTP/RTCP 对比 SIP 网关 + 综合整理

**日期**：2026年5月第6周
**目标**：对比 Janus 与 SIP 网关的 RTP/RTCP 处理差异，综合整理完整转发链路

---

## 一、SFU vs SIP B2BUA 架构差异

### 1.1 角色对比

| 维度 | Janus (WebRTC SFU) | SIP 网关 (Asterisk/FreeSWITCH) |
|------|-------------------|-------------------------------|
| **信令** | JSEP/JSON（Janus API） | SIP/SDP（RFC 3261/4566） |
| **传输** | ICE + DTLS-SRTP | 纯 RTP（通常无加密）或 SDES-SRTP |
| **媒体处理** | 包级转发（无编解码） | 可能需要转码 |
| **NAT 穿透** | ICE + STUN/TURN | SIP ALG / rport / STUN |
| **SSRC 处理** | 每个 ICE handle 重写 SSRC | 通常保持原始 SSRC（或 re-INVITE 时重协商） |
| **RTCP 处理** | 修复 SSRC + 过滤 + 生成 SR/RR | 通常透明转发或终结 |

### 1.2 核心差异

**Janus（SFU）**：
```
Peer A ──(encrypted RTP)──> Janus ──(encrypted RTP, rewritten SSRC)──> Peer B
           SSRC_a                                     SSRC_j
```
- 不解密不编码（包级转发）
- 重写 RTP 头（SSRC/seq/ts）
- 处理 RTCP 反馈（NACK/PLI/REMB）
- 端到端仍然 DTLS-SRTP 加密

**SIP 网关（B2BUA）**：
```
Caller ──(RTP, SSRC_c)──> SIP GW ──(RTP, SSRC_c)──> Callee
```
- 通常不重写 SSRC（除非转码）
- RTP 不被加密（除非 SDES）
- RTCP 通常透明转发
- 可能需要转码（如 G.711 ↔ Opus）

---

## 二、RTP 转发的三种模式

### 2.1 RTP Proxy 模式（传统 SIP 网关）

```
Caller ──RTP──> SIP GW Proxy ──RTP──> Callee
                  │
                  └── 修改 IP/Port（但不修改 SSRC）
```

**特点**：
- SIP GW 在 SDP 协商中替换 `c=` 和 `m=` 为自己的地址
- RTP 包直接转发，**不修改 SSRC/seq/ts**
- 典型实现：OpenSIPS + RTPProxy / RTPEngine

### 2.2 RTP Forwarding 模式（Janus Forwarder）

```
Janus Plugin ──RTP──> janus_rtp_forwarder ──RTP──> External UDP (CDN/Monitor)
                       │
                       └── 修改 SSRC/PT 为指定值
```

**特点**：
- 绕过 WebRTC 信令，直接 UDP 转发
- 可指定目标 SSRC 和 PT
- 支持 Simulcast（自动选择子流）
- 可选 SRTP 加密

### 2.3 SFU 包转发模式（Janus ICE Handle）

```
Peer A ──SRTP──> Janus ──SRTP──> Peer B
           SSRC_a    │    SSRC_j (重写的)
                   switching context
                   NACK 缓存
                   RTCP 处理
```

**特点**：
- 包级转发，不编解码
- 重写 SSRC + seq/ts（通过 switching context）
- 维护 NACK 缓存用于重传
- 处理所有 RTCP 反馈类型
- 支持 simulcast/SVC 层选择

---

## 三、SIP 网关的 RTP 处理

### 3.1 Asterisk RTP 处理

Asterisk 使用 RTP Engine（`rtp_engine.c` / `res_rtp_asterisk.c`）：

```
Asterisk RTP 栈：
  rtp_engine.c     → 抽象 RTP 接口
  res_rtp_asterisk.c → 基于 pjnath 的 ICE/STUN 实现
  rtp.c            → 核心 RTP 处理
```

**Asterisk RTP 帧结构**：
```c
struct ast_rtp {
    int fd;                     // RTP socket
    struct ast_sockaddr addr;   // 对端地址
    unsigned int ssrc;          // 本地 SSRC
    int seqno;                  // 序列号
    int lastseqno;              // 上次收到的序列号
    // ... RX/TX 统计
};
```

### 3.2 FreeSWITCH RTP 处理

FreeSWITCH 使用 `switch_rtp`：

```c
struct switch_rtp {
    switch_socket_t *sock_input;   // RTP 输入 socket
    switch_socket_t *sock_output;  // RTP 输出 socket
    uint32_t ssrc;                  // 本地 SSRC
    uint16_t seq;                   // 序列号
    uint32_t ts;                    // 时间戳
    // ... jitter buffer, RFC2833 DTMF
};
```

**FreeSWITCH 的特点**：
- 支持 **RTP 透传模式**（Proxy Media / Bypass Media）：不经过服务器直接点对点
- 支持 **转码模式**：通过 `mod_opus` / `mod_g711` 等模块进行编解码
- 支持 **录音**：通过 `record_session` 将 RTP 流写入文件

### 3.3 与 Janus 的关键差异

| 功能 | Janus | SIP 网关 (Asterisk/FreeSWITCH) |
|------|-------|-------------------------------|
| SSRC 重写 | 必须（每个 handle 独立） | 通常保持，转码时才重写 |
| Switching Context | 有（seq/ts 连续性保证） | 无（通常不切换 SSRC） |
| NACK 处理 | SFU 自己处理重传 | 通常不支持 NACK |
| Simulcast | 内置支持（SSRC/rid 识别+层选择） | 不支持 |
| TWCC | 解析但未使用 | 不支持 |
| REMB | 支持生成和 cap | 不支持 |
| Jitter Buffer | 无（包级转发） | 有（需要排包） |
| DTMF | RFC2833 解析 | RFC2833 解析 + 生成 |
| 加密 | DTLS-SRTP（端到端） | SDES-SRTP 或无加密 |
| NAT 穿透 | ICE（libnice） | STUN + rport + ALG |

---

## 四、RTCP 处理对比

### 4.1 SIP 网关的 RTCP 处理

**传统模式**（Asterisk）：
```
Caller ──RTCP SR/RR──> Asterisk ──RTCP SR/RR──> Callee
```
- RTCP SR/RR **透明转发**（或终结在网关）
- **不修改** Report Block 中的 SSRC
- 如果做了 SSRC 重写（转码场景），需要修改 RTCP 中的 SSRC 引用

**NAT 场景**（RTPEngine）：
```
Caller (NAT内) ──RTCP──> RTPEngine (公网) ──RTCP──> Callee (NAT内)
```
- RTPEngine 在公网上终结两端的 RTP/RTCP
- 可能需要修改 RTCP 中的 `c=` 地址对应的 SSRC

### 4.2 Janus 的 RTCP 处理

**SFU 模式**：
```
Peer A ──SR/RR──> Janus ──SR/RR (fixed)──> Peer B
            NACK → Janus 自己处理重传
            PLI  → 转发给 Peer A
            REMB → Janus 自己处理/cap
            TWCC → Janus 解析/分析
```

### 4.3 SSRC 修复的对比

| 场景 | SIP 网关 | Janus |
|------|----------|-------|
| **不修改 SSRC** | RTCP 透明转发，不改 SSRC | N/A（Janus 必须重写 SSRC） |
| **修改 SSRC**（转码/重写） | 修改 SR/RR 中的 SSRC | `janus_rtcp_fix_ssrc()` 修复所有类型 |
| **Report Block 修复** | 一般不修改 | `janus_rtcp_fix_report_data()` 修复 seq/ts |

---

## 五、完整转发链路梳理

### 5.1 Janus RTP 入站处理（接收）

```
┌─────────────────────────────────────────────────────────┐
│ 1. UDP 包到达 (libnice nice_agent 回调)                  │
│    └─ nice_agent_recv() 接收 UDP 数据                   │
│                                                         │
│ 2. ICE 层 (ice.c)                                       │
│    ├─ janus_ice_cb_nice_recv() 回调                     │
│    ├─ 判断是 RTP / RTCP / STUN                          │
│    └─ 如果是 RTP → janus_ice_cb_rtp_recv()             │
│                                                         │
│ 3. SRTP 解密 (srtp.c)                                   │
│    └─ srtp_unprotect() 解密                             │
│                                                         │
│ 4. RTCP Context 更新 (rtcp.c)                           │
│    └─ janus_rtcp_process_incoming_rtp()                 │
│        ├─ 更新 max_seq_nr, seq_cycle                    │
│        ├─ 计算 jitter（RFC 3550 A.8）                   │
│        ├─ 累加 received / expected                      │
│        └─ rtp_recvd = 1（可以开始发 RR）                │
│                                                         │
│ 5. Jitter Buffer（可选）                                 │
│    └─ 处理乱序包，按 seq 排序                           │
│                                                         │
│ 6. NACK 队列处理                                         │
│    └─ 检查收到的序包是否在 NACK 缓存中                   │
│    └─ 如果是被 NACK 的包 → 标记重传已到达              │
│                                                         │
│ 7. 插件回调                                             │
│    └─ plugin->incoming_rtp(handle, packet)              │
│    └─ plugin->incoming_rtcp(handle, packet)             │
└─────────────────────────────────────────────────────────┘
```

### 5.2 Janus RTP 出站处理（发送）

```
┌─────────────────────────────────────────────────────────┐
│ 1. 插件调用                                             │
│    └─ gateway->relay_rtp(handle, video, buf, len)      │
│                                                         │
│ 2. RTP 转发入口 (ice.c)                                 │
│    └─ janus_ice_relay_rtp()                            │
│                                                         │
│ 3. Simulcast 处理 (rtp.c) — 仅视频                      │
│    └─ janus_rtp_simulcasting_context_process_rtp()     │
│        ├─ 识别 substream（SSRC/rid）                    │
│        ├─ 决定是否转发（substream 匹配）               │
│        ├─ 时间层过滤（VP8 TID / VP9 SVC / AV1 DD）    │
│        └─ 超时自动降级 + need_pli                      │
│                                                         │
│ 4. Switching Context (rtp.c)                            │
│    └─ janus_rtp_header_update()                        │
│        ├─ 检测 SSRC 变化 → 计算偏移                    │
│        ├─ 生成连续的 seq_number                         │
│        └─ 生成连续的 timestamp                          │
│                                                         │
│ 5. Skew 补偿 (rtp.c) — 可选                             │
│    └─ janus_rtp_skew_compensate_audio/video()          │
│        └─ 源时钟漂移 > 120ms → 调整偏移                │
│                                                         │
│ 6. 扩展更新                                             │
│    ├─ Abs-Send-Time 更新（用当前时间）                 │
│    └─ Transport-CC seq number 更新                     │
│                                                         │
│ 7. RTCP Context 更新（出向方向）                         │
│    └─ sent_packets_since_last_rr++                     │
│                                                         │
│ 8. NACK 缓存                                            │
│    └─ janus_ice_nack_save_packet() 缓存包到队列        │
│    └─ 清理过期的旧包（超出时间窗口）                   │
│                                                         │
│ 9. SRTP 加密 (srtp.c)                                   │
│    └─ srtp_protect() 加密                              │
│                                                         │
│ 10. UDP 发送                                            │
│     └─ nice_agent_send() 通过 libnice 发送             │
└─────────────────────────────────────────────────────────┘
```

### 5.3 与 SIP 网关转发链路对比

| 处理步骤 | Janus | SIP 网关 |
|----------|-------|----------|
| 入站 SRTP 解密 | srtp_unprotect() | 通常无（明文传输） |
| RTCP 统计更新 | process_incoming_rtp() | 网关注入统计 |
| Jitter Buffer | 可选（处理乱序） | 有（必须排序） |
| NACK 缓存 | 有（支持重传） | 无 |
| Simulcast 选择 | 有（自动/手动） | N/A |
| SSRC 重写 | 必须（切换时） | 通常不 |
| Switching Context | 有 | 无（不切换 SSRC） |
| Skew 补偿 | 有 | 通常无 |
| 出站 SRTP 加密 | srtp_protect() | 通常无（或 SDES） |

---

## 六、关键函数速查表

### RTP 相关

| 函数 | 文件:行 | 作用 |
|------|---------|------|
| `janus_is_rtp()` | rtp.c:31 | 判断是否为 RTP 包 |
| `janus_rtp_payload()` | rtp.c:38 | 获取 RTP 负载指针 |
| `janus_rtp_header_update()` | rtp.c:844 | Switching Context 更新 seq/ts |
| `janus_rtp_skew_compensate_audio()` | rtp.c:700 | 音频时钟漂移补偿 |
| `janus_rtp_skew_compensate_video()` | rtp.c:775 | 视频时钟漂移补偿 |
| `janus_rtp_simulcasting_context_process_rtp()` | rtp.c:1203 | Simulcast 包处理 |
| `janus_rtp_svc_context_process_rtp()` | rtp.h:505 | VP9 SVC 包处理 |
| `janus_rtp_header_extension_find()` | rtp.c:145 | 查找扩展 (static) |
| `janus_rtp_header_extension_parse_mid()` | rtp.c:286 | 解析 mid 扩展 |
| `janus_rtp_header_extension_parse_rid()` | rtp.c:307 | 解析 rid 扩展 |
| `janus_rtp_header_extension_set_abs_send_time()` | rtp.c:369 | 设置 abs-send-time |

### RTCP 相关

| 函数 | 文件:行 | 作用 |
|------|---------|------|
| `janus_is_rtcp()` | rtcp.c:45 | 判断是否为 RTCP 包 |
| `janus_rtcp_fix_ssrc()` | rtcp.c:542 | RTCP SSRC 修复（最长的函数） |
| `janus_rtcp_filter()` | rtcp.c:729 | RTCP 过滤 |
| `janus_rtcp_fix_report_data()` | rtcp.c:1048 | 修复 Report Block 数据 |
| `janus_rtcp_report_block()` | rtcp.c:1017 | 生成 Report Block |
| `janus_rtcp_process_incoming_rtp()` | rtcp.c:848 | RTP→RTCP context 更新 |
| `janus_rtcp_has_pli()` | rtcp.c:1178 | 检测 PLI 请求 |
| `janus_rtcp_has_fir()` | rtcp.c:1145 | 检测 FIR 请求 |
| `janus_rtcp_has_bye()` | rtcp.c:1118 | 检测 BYE 消息 |
| `janus_rtcp_get_nacks()` | rtcp.c:1209 | 解析 NACK 列表 |
| `janus_rtcp_remove_nacks()` | rtcp.c:1273 | 移除已处理的 NACK |
| `janus_rtcp_get_remb()` | rtcp.c:1328 | 获取 REMB 码率 |
| `janus_rtcp_cap_remb()` | rtcp.c:1371 | 限制 REMB 码率 |
| `janus_rtcp_pli()` | rtcp.c:1536 | 生成 PLI 包 |
| `janus_rtcp_fir()` | rtcp.c:1514 | 生成 FIR 包 |
| `janus_rtcp_nacks()` | rtcp.c:1550 | 生成 NACK 包 |
| `janus_rtcp_remb()` | rtcp.c:1464 | 生成 REMB 包 |
| `janus_rtcp_transport_wide_cc_feedback()` | rtcp.c:1594 | 生成 TWCC 反馈 |
| `janus_rtcp_context_get_rtt()` | rtcp.c:933 | 获取估计 RTT |
| `janus_rtcp_context_get_lost_all()` | rtcp.c:953 | 获取总丢包数 |
| `janus_rtcp_context_get_jitter()` | rtcp.c:987 | 获取 jitter |

---

## 七、W3-W10 综合回顾

### 7.1 Janus 信令到媒体的全链路

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 阶段 1: 连接建立（W3-4）                                                 │
│   janus.c 启动 → 加载插件 → 客户端 create session → attach plugin        │
├──────────────────────────────────────────────────────────────────────────┤
│ 阶段 2: ICE 建连（W5）                                                   │
│   libnice agent 创建 → 候选地址收集 → 交换 candidates → 连通性检查      │
│   → ICE CONNECTED → READY                                                │
├──────────────────────────────────────────────────────────────────────────┤
│ 阶段 3: DTLS-SRTP 密钥协商（W6）                                        │
│   DTLS 握手 (ClientHello→...→Finished) → 导出 SRTP 密钥 → SRTP 上下文   │
├──────────────────────────────────────────────────────────────────────────┤
│ 阶段 4: SDP 协商（W7-8）                                                 │
│   Browser offer → preparse → process_remote → anonymize → plugin        │
│   → plugin answer → merge → write → browser                             │
│   核心模式：剥离 ICE/DTLS → 插件只看媒体 → 合并 ICE/DTLS                │
├──────────────────────────────────────────────────────────────────────────┤
│ 阶段 5: 媒体传输（W9-10）                                                │
│                                                                          │
│   入站：                                                                 │
│   UDP → SRTP解密 → RTCP统计 → Jitter缓冲 → NACK处理 → plugin回调       │
│                                                                          │
│   出站：                                                                 │
│   plugin relay → Simulcast选择 → Switching Context(seq/ts)              │
│   → Skew补偿 → 扩展更新 → NACK缓存 → SRTP加密 → UDP发送                 │
│                                                                          │
│   RTCP 反馈：                                                            │
│   NACK: SFU自己重传 | PLI/FIR: 转发 | REMB: 自己处理/cap               │
│   TWCC: 解析分析 | SR/RR: 修复SSRC后转发                                │
└──────────────────────────────────────────────────────────────────────────┘
```

### 7.2 关键架构模式总结

| 模式 | 说明 | 位置 |
|------|------|------|
| **插件动态加载** | dlopen/dlsym + JANUS_PLUGIN_INIT 宏 | janus.c + plugin.h |
| **SDP 剥离与合并** | anonymize（去 ICE/DTLS）→ merge（加 ICE/DTLS） | sdp.c |
| **B2BUA SSRC 修复** | fix_ssrc / fix_report_data 保证端到端 SSRC 一致 | rtcp.c |
| **Switching Context** | 确保 seq/ts 在 SSRC 切换后仍然连续 | rtp.c |
| **NACK 缓存与重传** | SFU 级缓存最近包，收到 NACK 直接重传 | ice.c + rtcp.c |
| **RTCP 过滤** | 删除 SFU 自己处理的 RTCP 类型，只转发端到端必需的 | rtcp.c |
| **Simulcast 层选择** | SSRC/rid 识别 + keyframe 等待 + 超时降级 | rtp.c |

### 7.3 Janus vs SIP 网关最终对比

| 维度 | Janus (WebRTC SFU) | SIP B2BUA |
|------|-------------------|-----------|
| **适用场景** | WebRTC 多人会议/直播 | 传统 VoIP 电话 |
| **加密方式** | DTLS-SRTP（端到端） | 无/SDES-SRTP（逐跳） |
| **NAT 穿透** | ICE（完整实现） | STUN + 中间层 |
| **重传机制** | NACK + RTX（SFU 层面） | 无（依赖丢包隐藏） |
| **码率控制** | REMB + TWCC + GCC | 固定码率编码 |
| **流分层** | Simulcast + SVC | 无 |
| **可扩展性** | SFU 模型（线性扩展） | B2BUA 模型（转码时开销大） |
| **延迟** | 低（包级转发 ~10-50ms） | 中等（转码时 ~20-100ms） |
| **复杂性** | 高（协议栈完整） | 中等（协议栈成熟） |

---

## 八、下一步（W11-12）

**目标**：传输优化深入 — 丢包恢复

1. NACK 策略深入：重传时机选择、最大重传次数、超时设置
2. FEC 原理：XOR FEC / FlexFEC / ULP FEC
3. NACK vs FEC 场景选择
4. 动手写 demo 验证

---

**学习进度**：✅ W3-9 完成（主流程→插件架构→ICE→DTLS/SRTP→SDP→RTP→RTCP/NACK/PLI） ✅ W10 完成（SIP 网关对比+综合整理）

**当前任务**：进入 Phase 3 第 11-12 周（丢包恢复：NACK 策略+FEC 原理）→ 待创建 `week11_notes.md`
