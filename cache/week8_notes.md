# 第八周学习笔记：SDP 处理深入（代码路径追踪）

**日期**：2026年5月第5周  
**目标**：追踪 SDP 完整代码路径，理解 process_local、merge、anonymize 的具体实现，剖析 Unified Plan 兼容性

---

## 一、完整 SDP 处理流程：两种场景

Janus 中有两条完全对称的 SDP 处理路径，取决于谁发起 Offer。

### 场景 A：浏览器发起 Offer → 插件返回 Answer

```
Client (Browser)                    Janus Core                       ICE/DTLS              Plugin
      │                                │                               │                     │
      │-- JSEP Offer (含 ICE/DTLS) --> │                               │                     │
      │                                │-- janus_sdp_preparse()       │                     │
      │                                │   (检查 m-line 数量+DTLS role)│                     │
      │                                │-- janus_sdp_process_remote() │                     │
      │                                │   (提取远端 fingerprint/     │-- 设置 ICE credentials │
      │                                │    ice-ufrag/pwd, 解析 SSRC │-- 设置远端 candidates  │
      │                                │    方向, 检查 simulcast 等)  │                     │
      │                                │-- janus_sdp_anonymize()      │                     │
      │                                │   (剥离 ICE/DTLS/transport)  │                     │
      │                                │-- janus_sdp_write()          │                     │
      │                                │   (结构体→剥离后 SDP 字符串)  │                     │
      │                                │                               │                     │
      │                                │-- [JSEP 剥离后的 offer] ---------> handle_message  │
      │                                │                               │                     │
      │                                │                               │  <--- push_event    │
      │                                │                               │  + [剥离后的 answer] │
      │                                │                               │                     │
      │                                │-- janus_sdp_anonymize()      │                     │
      │                                │   (剥离插件的 answer 的 transport)│                  │
      │                                │-- janus_sdp_merge()          │                     │
      │                                │   (重新添加 ICE/DTLS 信息)    │                     │
      │                                │   → 公网 IP，fingerprint，    │                     │
      │                                │     ice-ufrag/pwd，candidates │                     │
      │                                │-- janus_sdp_write()          │                     │
      │                                │   (生成完整 SDP answer 字符串) │                     │
      │<-- JSEP Answer (含 ICE/DTLS) --│                               │                     │
```

### 场景 B：插件发起 Offer → 浏览器返回 Answer

```
Plugin                              Janus Core                       ICE/DTLS           Client (Browser)
  │                                    │                               │                     │
  │-- push_event + [SDP offer] ------> │                               │                     │
  │                                    │-- janus_sdp_preparse()       │                     │
  │                                    │-- janus_sdp_process_local()  │                     │
  │                                    │   (创建 medium 实例，         │                     │
  │                                    │    提取 mid/msid/clock_rate) │                     │
  │                                    │-- janus_ice_setup_local()    │                     │
  │                                    │   (创建 libnice agent+stream)│                     │
  │                                    │                               │                     │
  │                                    │   ← 等待 candidates-done    │                     │
  │                                    │                               │                     │
  │                                    │-- janus_sdp_anonymize()      │                     │
  │                                    │   (剥离 ICE/DTLS)            │                     │
  │                                    │-- janus_sdp_merge()          │                     │
  │                                    │   (合并 ICE/DTLS 信息)       │                     │
  │                                    │                               │                     │
  │<-- JSEP Offer (含 ICE/DTLS) ------│                               │                     │
  │                                    │                               │                     │
  │                                    │     (浏览器返回 Answer)       │                     │
  │-- [JSEP Answer] ----------------->│                               │                     │
  │                                    │-- janus_sdp_preparse()       │                     │
  │                                    │-- janus_sdp_process_remote() │                     │
  │                                    │-- janus_sdp_anonymize()      │                     │
  │                                    │   → 剥离后传给插件           │                     │
```

---

## 二、janus_sdp_process_local 深入（sdp.c:757）

**调用时机**：插件发起 Offer 时，处理插件传来的 SDP，创建本地 medium 实例。

### 代码流程

```
janus_sdp_process_local(ice_handle, remote_sdp, update)
  │
  ├─ 遍历每个 m-line
  │    │
  │    ├─ g_hash_table_lookup(pc->media, m->index)
  │    │    └─ 不存在 → janus_ice_peerconnection_medium_create() 创建
  │    │
  │    ├─ 提取 mid：存储到 medium->mid，建立 media_bymid 哈希表
  │    │    └─ 核心会移除 mid attribute（稍后 merge 时重新添加）
  │    │
  │    ├─ 提取 msid：解析 "msid" 和 "mstid"
  │    │    └─ 同样移除 msid attribute（merge 时重建）
  │    │
  │    ├─ 解析 rtpmap：记录 clock_rate 到 medium->clock_rates
  │    │
  │    ├─ 若 m-line 为 INACTIVE：
  │    │    └─ 重置 local SSRC = 0，清空 RTCP context
  │    │
  │    └─ 若 m-line 非 INACTIVE 且 ssrc == 0：
  │         └─ janus_random_uint32() 生成 SSRC
  │         └─ 可选：生成 rtx SSRC（RFC4588）
  │         └─ 插入 media_byssrc 哈希表
```

**关键特性**：
- **SSRC 生成**：插件不自建 SSRC，核心统一分配
- **mid/msid 剥离**：从 SDP 中移除，merge 时由核心重新添加（确保一致性）
- **clock_rate 记录**：从 rtpmap 中提取，供后续 RTP 时间戳计算

---

## 三、janus_sdp_anonymize 深入（sdp.c:1315）

### 移除的内容（两组）

**全局属性（7 项）**：
```
ice-ufrag, ice-pwd, ice-options, fingerprint,
group, msid-semantic, extmap-allow-mixed, rtcp-rsize
```

**m-line 级属性（16 项）**：
```
ice-ufrag, ice-pwd, ice-options, crypto, fingerprint,
setup, connection, group, msid-semantic, rid, simulcast,
rtcp, rtcp-mux, rtcp-rsize, candidate, end-of-candidates,
ssrc, ssrc-group, sctpmap, sctp-port, max-message-size
```

### 地址匿名化
- `o=` 地址 → `1.1.1.1`
- `c=` 地址 → `1.1.1.1`
- `m=` 端口 → `9`（音频/视频）或 `0`（禁用）

### 额外的清理
- **加密 RTP 扩展**：移除所有含 `urn:ietf:params:rtp-hdrext:encrypt` 的 extmap
- **不支持的 payload type**：移除 `red/90000`、`ulpfec/90000`、`flexfec-03/90000`、`rtx/90000`（插件不需要关心 FEC/RTX 的 payload type）

### 保留的信息
插件最终看到的是"纯媒体"SDP：codec 列表（rtpmap/fmtp）、ssrc（保留？不，ssrc 也被移除了）、msid、mid、extmap（非加密）、媒体方向等。

> **注意**：anonymize 也会移除 ssrc 和 ssrc-group！这意味着插件收到的 SDP **不包含** SSRC 信息。插件的 answer 中 SSRC 由核心在 merge 时统一添加。

---

## 四、janus_sdp_merge 深入（sdp.c:1456）

### 添加的内容

```
janus_sdp_merge(ice_handle, anon, offer)
  │
  ├─ 1. 全局属性（放在最前面）
  │    ├─ a=group:BUNDLE <mid1> <mid2> ...
  │    ├─ a=ice-options:trickle
  │    ├─ a=fingerprint:sha-256 <本地 DTLS 证书指纹>
  │    ├─ a=extmap-allow-mixed
  │    ├─ a=msid-semantic: WMS *
  │    └─ (可选) a=ice-lite（ICE Lite 模式）
  │
  ├─ 2. 遍历每个 m-line
  │    │
  │    ├─ 覆盖 proto → handle->rtp_profile ("UDP/TLS/RTP/SAVPF")
  │    ├─ 设置 c= 地址 → janus_get_public_ip()
  │    ├─ 添加 a=mid:<medium->mid>
  │    │
  │    ├─ 方向处理
  │    │    └─ port == 0 → direction = INACTIVE, ssrc = 0
  │    │    └─ 根据 direction 设置 medium->send/recv
  │    │
  │    ├─ RFC4588 RTX 处理
  │    │    └─ 添加 rtx/90000 的 rtpmap 和 fmtp apt= 属性
  │    │
  │    ├─ DataChannel 处理
  │    │    └─ 旧格式：a=sctpmap:5000 webrtc-datachannel 16
  │    │    └─ 新格式：a=sctp-port:5000
  │    │
  │    ├─ Audio/Video 属性
  │    │    └─ a=rtcp-mux
  │    │
  │    ├─ ICE/DTLS 属性
  │    │    ├─ a=ice-ufrag:<从 libnice 获取>
  │    │    ├─ a=ice-pwd:<从 libnice 获取>
  │    │    ├─ a=ice-options:trickle
  │    │    └─ a=setup:<actpass/client/server>（根据 offer/answer 角色）
  │    │
  │    ├─ SSRC 和 MSID
  │    │    ├─ (可选) a=ssrc-group:FID <ssrc> <ssrc_rtx>
  │    │    ├─ a=msid:<medium->msid> <medium->mstid>
  │    │    └─ a=ssrc:<ssrc> cname:janus
  │    │
  │    ├─ Simulcast rid 属性
  │    │    └─ a=rid:... recv + a=simulcast:recv ...
  │    │
  │    └─ Candidates（half-trickle 模式）
  │         ├─ janus_ice_candidates_to_sdp() 添加候选地址
  │         └─ a=end-of-candidates
  │
  └─ janus_sdp_write() → 返回完整 SDP 字符串
```

### key design decision: 先后顺序

属性添加有严格的**先后顺序**：
1. **先 `g_list_insert_before(first, ...)`**：BUNDLE、fingerprint 等全局属性插入到已有列表前面
2. **后 `g_list_append`**：SSRC、msid、simulcast 等追加到末尾

这是因为浏览器（尤其是 Chrome）对 SDP 属性顺序敏感：ICE ufrag/pwd 和 fingerprint 必须在 SSRC 之前。

---

## 五、Unified Plan vs Plan B 兼容性

### 在 Janus 代码中的体现

Janus 核心**不区分** Unified Plan 和 Plan B，它对两种格式都兼容。关键点：

| 机制 | Plan B | Unified Plan |
|------|--------|-------------|
| 多流表示 | 一个 m-line 多个 SSRC | 每个流自己的 m-line |
| SSRC 解析 | `janus_sdp_parse_ssrc()` 逐个解析 | 同上 |
| SSRC 分组 | `ssrc-group:SIM` 标识 simulcast | 较少用 |
| m-line 数量 | 固定（audio + video + data） | 动态（可能多个 video m-line） |
| msid | 可选 | 必须（标识每个 track） |
| mid | 必须（BUNDLE 分组） | 必须 |

### Janus 的兼容方式

```c
/* sdp.c:518-558 - SSRC 解析逻辑同时支持两种格式 */
// 1. 解析 ssrc-group:SIM（Plan B simulcast 分组）
// 2. 解析 ssrc-group:FID（RFC4588 rtx 分组）
// 3. 解析单个 ssrc 属性

/* sdp.c:471-509 - rid 和 simulcast 属性（Unified Plan simulcast） */
// 1. 解析 a=rid:... send（Chrome/Firefox 的 rid）
// 2. 解析 a=simulcast:...（新旧语法兼容）
// 3. 检测 disabled rid（~ 前缀）
```

### 实际差别

- **Plan B**：`a=ssrc:12345 cname:...` 在同一个 m-line 中出现多次
- **Unified Plan**：每个 m-line 只有一个 SSRC，但可能有多个 m-line
- **Janus 处理**：两者都走同一套代码——遍历 m-line，查找 ssrc 和 ssrc-group 属性
- **对插件的影响**：插件拿到 anonymize 后的 SDP 时，**ssrc 已被移除**，插件不需要关心底层的 SSRC 格式差异

### BUNDLE 处理

```c
/* janus_sdp_merge() 中 BUNDLE 分组创建 */
g_snprintf(buffer, sizeof(buffer), "BUNDLE");
while(temp) {
    janus_sdp_mline *m = (janus_sdp_mline *)temp->data;
    medium = g_hash_table_lookup(pc->media, GINT_TO_POINTER(m->index));
    if(medium && m->port > 0) {
        g_snprintf(buffer_part, sizeof(buffer_part), " %s", medium->mid);
        janus_strlcat(buffer, buffer_part, sizeof(buffer));
    }
}
// 输出: a=group:BUNDLE audio video
```

- 所有 port > 0 的 m-line 被 BUNDLE 在一起
- port == 0 的 m-line 被排除在 BUNDLE 之外（被拒绝的媒体）

---

## 六、RFC4588 RTX 处理

Janus 默认启用 RFC4588（重传 payload type 协商）。

### 处理流程

```
浏览器的 SDP 中 a=fmtp:... apt=...
  → janus_sdp_process_remote()
    → 解析 fmtp apt= 找到 rtx_ptype → ptype 映射
    → 存储到 pc->rtx_payload_types（全局）和 medium->rtx_payload_types

插件返回 answer 后
  → janus_sdp_merge()
    → 检查 medium->do_nacks && RFC4588 flag
    → 为每个 codec payload type 添加对应的 rtx payload type
    → 添加 a=rtpmap:<rtx_pt> rtx/90000
    → 添加 a=fmtp:<rtx_pt> apt=<orig_pt>
    → 添加 a=ssrc-group:FID <ssrc> <ssrc_rtx>
```

### 关键标志

```c
/* janus.c:3817 */
janus_flags_set(&ice_handle->webrtc_flags, JANUS_ICE_HANDLE_WEBRTC_RFC4588_RTX);

/* sdp.c:735-746 - 如果对端未协商 rtx，关闭 */
if(!rtx) {
    janus_flags_clear(&handle->webrtc_flags, JANUS_ICE_HANDLE_WEBRTC_RFC4588_RTX);
    // 遍历所有 medium，清除 rtx_ssrc
}
```

---

## 七、SDP 在各组件间的数据流动图

```
        ┌──────────────────────────────────────────────┐
        │               Client (Browser)                │
        │   SDP = media + ice-ufrag/pwd + fingerprint  │
        │          + candidates + setup                │
        └──────────┬───────────────────────┬────────────┘
                   │  JSEP Offer           │  JSEP Answer
                   ▼                       ▲
        ┌──────────────────────────────────────────────────┐
        │                 janus.c (核心主循环)               │
        │                                                  │
        │  ┌───────┐   ┌──────────────┐   ┌───────────┐   │
        │  │preparse│──▶│process_remote│──▶│ anony-    │   │
        │  │       │   │ (ICE/DTLS)   │   │ mize     │   │
        │  └───────┘   └──────────────┘   └─────┬─────┘   │
        │                                       │         │
        │                              stripped SDP        │
        │                                       │         │
        │  ┌────────────────────────────────────▼──────┐  │
        │  │         Plugin (如 echotest)               │  │
        │  │    handle_message() + stripped SDP         │  │
        │  └────────────────────────────────────▲──────┘  │
        │                                       │         │
        │  ┌───────┐   ┌──────────────┐   ┌─────┴─────┐   │
        │  │preparse│◀──│process_local │◀──│ anony-    │   │
        │  │       │   │ (medium创建)  │   │ mize     │   │
        │  └───────┘   └──────────────┘   └─────┬─────┘   │
        │                                       │         │
        │  ┌────────────────────────────────────▼──────┐  │
        │  │            janus_sdp_merge()               │  │
        │  │  → group BUNDLE → fingerprint → ice-ufrag  │  │
        │  │  → ice-pwd → setup → rtcp-mux → msid      │  │
        │  │  → ssrc → candidate → end-of-candidates    │  │
        │  └────────────────────────────────────▲──────┘  │
        │                                       │         │
        └───────────────────────────────────────┼─────────┘
                                                │
        ┌───────────────────────────────────────▼─────────┐
        │           janus_sdp_write()                      │
        │    结构体 janus_sdp → SDP 字符串                 │
        └─────────────────────────────────────────────────┘
```

---

## 八、对比：Browser→Plugin vs Plugin→Browser 流程差异

| 步骤 | Browser Offer → Plugin Answer | Plugin Offer → Browser Answer |
|------|------------------------------|------------------------------|
| ICE 设置 | `process_remote` 时通过 `janus_ice_setup_local(handle, offer=TRUE)` | `janus_plugin_handle_sdp` 中 `janus_ice_setup_local(handle, FALSE)` |
| DTLS 角色 | `process_remote` 从 a=setup 决定 | 固定 `JANUS_DTLS_ROLE_ACTPASS`（插件 offer 时） |
| medium 创建 | `process_remote` 中创建 | `process_local` 中创建 |
| SSRC 分配 | 对端 SSRC → `medium->ssrc_peer[]` | 本地 SSRC → `medium->ssrc = janus_random_uint32()` |
| candidates 设置 | `process_remote` 中 `janus_sdp_parse_candidate` | merge 时 `janus_ice_candidates_to_sdp` |
| 等待 candidates | 不需要（浏览器已有） | 需要等待 `ice_handle->cdone` 回调 |

---

## 九、关键代码路径总结

| 函数 | 位置 | 行数 | 作用 |
|------|------|------|------|
| `janus_sdp_preparse` | sdp.c:33 | ~120 | SDP 格式校验 + m-line 计数 + DTLS role 解析 |
| `janus_sdp_process_remote` | sdp.c:146 | ~610 | 处理浏览器 SDP：提取 ICE/DTLS/SSRC/candidates/方向 |
| `janus_sdp_process_local` | sdp.c:757 | ~160 | 处理插件 SDP：创建 medium + 分配 SSRC |
| `janus_sdp_anonymize` | sdp.c:1315 | ~140 | 剥离 transport 属性，匿名化地址 |
| `janus_sdp_merge` | sdp.c:1456 | ~300 | 合并 transport 信息，生成完整 SDP |
| `janus_sdp_parse_candidate` | sdp.c:963 | ~350 | 解析 ICE candidate 字符串 |
| `janus_sdp_parse_ssrc` | sdp.c 后续 | - | 解析 SSRC 属性 |
| `janus_sdp_parse_ssrc_group` | sdp.c 后续 | - | 解析 SSRC 分组（FID/SIM） |
| `janus_plugin_handle_sdp` | janus.c:3757 | ~470 | 插件→浏览器的 SDP 处理入口（preparse → process_local → anonymize → merge） |

---

## 十、下一步（W9-10）

**目标**：RTP/RTCP 转发机制

1. `rtp.c` / `rtcp.c` 源码分析
2. `janus_plugin_relay_rtp` → `janus_ice_relay_rtp` 的转发路径
3. NACK 重传机制
4. PLI 请求处理
5. 对比 SIP 网关的 RTP/RTCP 处理

---

**学习进度**：✅ W7 完成（SDP 结构体+解析/生成+Offer/Answer+anonymize/merge） ✅ W8 完成（完整代码路径+process_local+merge 实现+Unified Plan 兼容）
**当前任务**：进入 W9-10（RTP/RTCP 转发）
