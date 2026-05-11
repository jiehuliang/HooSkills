# 第九周学习笔记：RTCP 反馈与重传机制（下）

**日期**：2026年5月第5-6周 周五-周日
**目标**：理解 NACK 重传、PLI/FIR 关键帧请求、REMB 码率控制、TWCC 传输反馈、SSRC 修复与过滤

---

## 一、NACK 重传机制

### 1.1 NACK 协议基础（RFC 4585 §6.2.1）

NACK（Negative ACKnowledgement）是 RTPFB（PT=205, FMT=1）类型消息，用于告知发送方哪些包丢失需要重传。

**NACK FCI（Feedback Control Information）结构**：
```
 0                   1
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|            PID (Packet ID)            |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|     BLP (Bitmask of Lost Packets)    |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

- **PID**：丢失包的 sequence number
- **BLP**：16 位位掩码，bit N=1 表示 PID+N+1 也丢失
- 一个 NACK 最多可以表示 **17 个连续的丢失包**（1 个 PID + 16 个 BLP）

### 1.2 Janus 中的 NACK 数据结构（rtcp.h:146-161）

```c
// RTCP 网络格式
typedef struct rtcp_nack {
    uint16_t pid;     // 丢失包序列号
    uint16_t blp;     // 后 16 个包的丢失位掩码
} rtcp_nack;

// Janus 内部链表格式
typedef struct janus_nack {
    uint16_t seq_no;          // 需要重传的序列号
    struct janus_nack *next;  // 链表指针
} janus_nack;
```

### 1.3 NACK 生成：janus_rtcp_nacks()（rtcp.c:1550-1592）

当 Janus 检测到丢包时，需要生成 NACK 发送给对端：

```c
int janus_rtcp_nacks(char *packet, int len, GSList *nacks) {
    // 设置 RTCP 头
    rtcp->version = 2;
    rtcp->type = RTCP_RTPFB;   // 205
    rtcp->rc = 1;              // FMT=1 (NACK)

    janus_rtcp_nack *nack = (janus_rtcp_nack *)rtcpfb->fci;
    guint16 pid = GPOINTER_TO_UINT(nacks->data);
    nack->pid = htons(pid);     // 第一个丢失的 seq
    int words = 3;

    // 遍历丢失序列号列表
    while(nacks) {
        guint16 npid = GPOINTER_TO_UINT(nacks->data);
        if(npid - pid > 16) {
            // 超出当前 PID 能表示的范围 → 新建一个 NACK 块
            words++;
            char *new_block = packet + words*4;
            nack = (janus_rtcp_nack *)new_block;
            pid = npid;
            nack->pid = htons(pid);
        } else {
            // 在 BLP 位掩码中标记
            uint16_t blp = ntohs(nack->blp);
            blp |= 1 << (npid - pid - 1);  // 设置对应位
            nack->blp = htons(blp);
        }
        nacks = nacks->next;
    }
    rtcp->length = htons(words);
    return words*4 + 4;
}
```

**关键设计**：
- 多个 NACK 块被串联在同一个 RTCP-FB 包中（通过叠加 FCI 数据）
- 每块可覆盖 17 个连续丢包，超出后自动创建新块

### 1.4 NACK 解析：janus_rtcp_get_nacks()（rtcp.c:1209-1271）

收到对端发来的 NACK 后，解析出所有需要重传的 seq_no：

```c
void janus_rtcp_get_nacks(char *packet, int len, GQueue *nacks_queue) {
    janus_rtcp_fb *rtcpfb = (janus_rtcp_fb *)rtcp;
    int nacks = ntohs(rtcp->length) - 2;  // 减去 SSRC 占用的 2 个 word

    janus_rtcp_nack *nack = NULL;
    for(i = 0; i < nacks; i++) {
        nack = (janus_rtcp_nack *)rtcpfb->fci + i;
        pid = ntohs(nack->pid);
        g_queue_push_head(nacks_queue, GUINT_TO_POINTER(pid));  // PID 自身

        blp = ntohs(nack->blp);
        for(j = 0; j < 16; j++) {
            if((blp & (1 << j)) >> j)
                g_queue_push_head(nacks_queue, GUINT_TO_POINTER(pid + j + 1));
        }
    }
}
```

### 1.5 NACK 在 Janus 中的完整流程

```
Peer A (发送者)              Janus (SFU)                Peer B (接收者)
      │                          │                          │
      │-- RTP seq=100 ──────────>│                          │
      │-- RTP seq=101 ──────────>│-- RTP seq=100 ──────────>│
      │-- RTP seq=102 ──────────>│                          │
      │                          │  [seq=101 丢失]          │-- 检测到 seq 102
      │-- RTP seq=103 ──────────>│-- RTP seq=103 ──────────>│   seq 101 缺失！
      │                          │                          │
      │                          │<-- NACK PID=101 ────────│
      │                          │                          │
      │                          │  [查找缓存的包]          │
      │                          │  找到 seq=101 的包       │
      │                          │                          │
      │                          │-- RTX seq=101 (重传) ──>│
      │                          │                          │
```

**Janus 核心在收到 NACK 后**：
1. 调用 `janus_rtcp_get_nacks()` 解析出所有需要重传的 seq_no
2. 遍历 `queued_packets`（按 seq 缓存的 RTP 包）
3. 找到对应包后调用 `janus_ice_relay_rtp()` 重新发送（标记为 RTX）
4. 调用 `janus_rtcp_remove_nacks()` 从 RTCP 中移除已处理的 NACK 块

### 1.6 NACK 重传抑制机制

```c
// rtp.h janus_rtp_packet 中的退避字段
gint64 last_retransmit;   // 上次重传时间
gint64 current_backoff;   // 当前退避时间
```

**退避策略**：同一 seq 如果短时间内被反复 NACK（对端持续未收到），Janus 会逐渐增加重传间隔，避免网络拥塞时无意义的大量重传。

---

## 二、PLI 和 FIR 关键帧请求

### 2.1 概念对比

| 类型 | RTCP PT | FMT | 含义 | 规范 |
|------|---------|-----|------|------|
| **PLI** | PSFB (206) | 1 | Picture Loss Indication | RFC 4585 |
| **FIR** | PSFB (206) | 4 | Full Intra Request | RFC 5104 |
| **FIR (legacy)** | FIR (192) | - | 旧版 FIR | RFC 2032 |

- **PLI**：告知发送端画面丢失，需要**尽快**发送关键帧
- **FIR**：要求发送端发送**完整的 IDR 关键帧**

### 2.2 PLI 检查：janus_rtcp_has_pli()（rtcp.c:1178-1207）

```c
gboolean janus_rtcp_has_pli(char *packet, int len) {
    while(rtcp) {
        if(rtcp->type == RTCP_PSFB) {
            gint fmt = rtcp->rc;
            if(fmt == 1)      // FMT=1 = PLI
                return TRUE;
        }
        // 遍历 compound packet
        rtcp = (janus_rtcp_header *)((uint32_t*)rtcp + length + 1);
    }
    return FALSE;
}
```

PLI 包**没有 FCI 数据**（FCI 长度为 0），仅通过 FMT=1 标识。

### 2.3 PLI 生成：janus_rtcp_pli()（rtcp.c:1536-1547）

```c
int janus_rtcp_pli(char *packet, int len) {
    janus_rtcp_header *rtcp = (janus_rtcp_header *)packet;
    rtcp->version = 2;
    rtcp->type = RTCP_PSFB;    // 206
    rtcp->rc = 1;              // FMT=1 (PLI)
    rtcp->length = htons((len/4)-1);  // 12/4 - 1 = 2
    return 12;                 // PLI 总长固定 12 字节
}
```

### 2.4 FIR 生成：janus_rtcp_fir()（rtcp.c:1514-1533）

```c
int janus_rtcp_fir(char *packet, int len, int *seqnr) {
    rtcp->version = 2;
    rtcp->type = RTCP_PSFB;    // 206
    rtcp->rc = 4;              // FMT=4 (FIR)

    janus_rtcp_fb_fir *fir = (janus_rtcp_fb_fir *)rtcpfb->fci;
    fir->seqnr = htonl(*seqnr << 24);  // 只使用高 8 位

    *seqnr = *seqnr + 1;       // 递增序列号
    if(*seqnr < 0 || *seqnr >= 256)
        *seqnr = 0;            // 8 位 wrap-around
    return 20;                 // FIR 总长 20 字节
}
```

**FIR 的 FCI 结构**：
```
 0                   1                   2                   3
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                            SSRC                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
| Seq nr (8)   |                  Reserved                      |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

### 2.5 在 Janus 中的使用场景

```
场景 1：Simulcast 切换时需要关键帧
  → janus_rtp_simulcasting_context 检测到需要切换
  → context->need_pli = TRUE
  → 上层代码发送 PLI 给发送端

场景 2：新观众加入 video room
  → 需要当前的关键帧以开始解码
  → VideoRoom 插件发送 PLI 给发布者

场景 3：对端检测到画面冻结
  → 浏览器发送 PLI/FIR
  → Janus 转发给媒体发送端
```

---

## 三、REMB 码率控制（RTCP REMB）

### 3.1 REMB 协议（draft-alvestrand-rmcat-remb-03）

REMB（Receiver Estimated Maximum Bitrate）用于接收端向发送端声明自己能接受的最大码率。

**RTCP 封装**：PSFB（PT=206, FMT=15），FCI 格式：
```
 0                   1                   2                   3
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|  'R'  |  'E'  |  'M'  |  'B'  | Num SSRC | Br Exp | Br Mant.|
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
| Br Mantissa (cont.)   |      SSRC #1                          |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|      SSRC #2 (opt)    |      SSRC #3 (opt)    |   ...         |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

- **bitrate** = `BrMantissa * 2^BrExp` bps
- BrMantissa 占 18 bits，BrExp 占 6 bits
- 最大表示码率：`(2^18 - 1) * 2^63 ≈ 无数值限制`

### 3.2 REMB 生成：janus_rtcp_remb() / janus_rtcp_remb_ssrcs()（rtcp.c:1463-1511）

```c
int janus_rtcp_remb_ssrcs(char *packet, int len, uint32_t bitrate, uint8_t numssrc) {
    rtcp->type = RTCP_PSFB;        // 206
    rtcp->rc = 15;                 // FMT=15 (REMB)

    janus_rtcp_fb_remb *remb = (janus_rtcp_fb_remb *)rtcpfb->fci;
    remb->id[0]='R'; remb->id[1]='E'; remb->id[2]='M'; remb->id[3]='B';

    // bitrate → brexp / brmantissa
    uint8_t newbrexp = 0;
    for(b = 0; b < 32; b++) {
        if(bitrate <= ((uint32_t)0x3FFFF << b)) {
            newbrexp = b;
            break;
        }
    }
    uint32_t newbrmantissa = bitrate >> b;

    // 写入数据
    _ptrRTCPData[0] = numssrc;    // 受影响 SSRC 数量
    _ptrRTCPData[1] = (newbrexp << 2) | ((newbrmantissa >> 16) & 0x03);
    _ptrRTCPData[2] = (newbrmantissa >> 8);
    _ptrRTCPData[3] = newbrmantissa;
}
```

### 3.3 REMB 限速：janus_rtcp_cap_remb()（rtcp.c:1371-1434）

Janus 作为 SFU，可能需要**限制**接收端请求的码率（避免超出服务端带宽限制）：

```c
int janus_rtcp_cap_remb(char *packet, int len, uint32_t bitrate) {
    // 1. 找到 REMB FCI
    // 2. 解析原始 bitrate
    // 3. 如果 > cap，计算新的 brexp/brmantissa
    // 4. 覆写 REMB 数据
    // 5. 如果 <= cap，不做修改
}
```

### 3.4 Janus 对 REMB 的处理策略

- **接收 REMB**：解析 `janus_rtcp_get_remb()` 获取对端请求的码率
- **过滤 REMB**：`janus_rtcp_filter()` 中 REMB 被直接删除（keep=FALSE），因为 Janus 自己生成 RR/SR
- **生成 REMB**：Janus 可以主动生成 REMB 限制发送端码率

---

## 四、Transport-CC 传输反馈（rtcp.c:238-340）

### 4.1 协议概述

Transport-wide Congestion Control（draft-holmer-rmcat-transport-wide-cc-extensions）：

- 发送端在每个 RTP 包中嵌入 `transport-wide sequence number`（RTP 扩展）
- 接收端周期性地回送 TWCC 反馈，报告每个包的到达时间
- 发送端据此计算网络延迟和拥塞，调整发送码率（GCC 算法）

### 4.2 TWCC 反馈包结构

```
RTPFB (PT=205, FMT=15)
  FCI:
    base_seq (16bits):   本次反馈的起始 transport seq number
    packet_status_count (16bits): 反馈包含的包数量
    reference_time (24bits): 参考时间
    fb_pkt_count (8bits): 反馈包计数
    packet_chunks:       run-length 或 status-vector 编码
    recv_deltas:          每个到达包的延迟（250us 单位）
```

### 4.3 Janus 中的 TWCC 解析：janus_rtcp_incoming_transport_cc()（rtcp.c:238-340）

```c
static void janus_rtcp_incoming_transport_cc(janus_rtcp_context *ctx,
        janus_rtcp_fb *twcc, int total) {

    // 1. 解析头部
    uint16_t base_seq = ntohs(*(uint16_t *)data);
    uint16_t status_count = ntohs(*(uint16_t *)(data+2));
    uint32_t reference = ntohl(*(uint32_t *)(data+4)) >> 8;

    // 2. 解析 packet chunks（run-length 或 status-vector）
    //    t=0: run-length → s 状态重复 length 次
    //    t=1: status-vector → ss=0 每包1bit, ss=1 每包2bit
    while(psc > 0 && total > 1) {
        // 根据 chunk 类型解析每个包的状态
        //   notreceived(0) / smalldelta(1) / largeornegativedelta(2)
    }

    // 3. 解析 recv deltas
    //    状态为 smalldelta → 1 字节 delta
    //    状态为 largeornegativedelta → 2 字节 delta
    //    delta_us = delta * 250
}
```

**当前状态**：Janus 的 TWCC 解析代码已经完整，但在 `janus_rtcp_incoming_transport_cc()` 末尾有个 TODO：
```c
/* TODO Update the context with the feedback we got */
```

这意味着 TWCC 的反馈信息目前**解析了但没有实际用于拥塞控制**——该功能交由上层应用（如 GCC 模块）使用。

---

## 五、RTCP SSRC 修复与过滤

### 5.1 为什么需要修复 SSRC？

Janus 作为 SFU（B2BUA），改变了媒体流的 SSRC：
- Peer A → Janus：SSRC=A（原始发送端 SSRC）
- Janus → Peer B：SSRC=J（Janus 重写的 SSRC）

当 Peer B 发送 RTCP SR/RR 报告 Peer A 的 SSRC 时，Janus 需要**把 SSRC 从 J 改回 A**，否则 Peer A 不认识这个 SSRC。

### 5.2 janus_rtcp_fix_ssrc()（rtcp.c:542-790）

这是 rtcp.c 中最长的函数（约 250 行），处理各种 RTCP 类型的 SSRC 修复：

```c
int janus_rtcp_fix_ssrc(ctx, packet, len, fixssrc, newssrcl, newssrcr) {
    // fixssrc=1 时修改 SSRC，fixssrc=0 时只解析
    // newssrcl: 新的发送端 SSRC（local → 写入）
    // newssrcr: 新的接收端 SSRC（receiver → 写入）

    switch(rtcp->type) {
        case RTCP_SR: {
            sr->ssrc = htonl(newssrcl);          // 修复发送者 SSRC
            if(sr->header.rc > 0)
                sr->rb[0].ssrc = htonl(newssrcr); // 修复 RB 的 SSRC
            if(ctx) janus_rtcp_incoming_sr(ctx, sr); // 更新 context
            break;
        }
        case RTCP_RR: {
            rr->ssrc = htonl(newssrcl);
            if(rr->header.rc > 0) {
                rr->rb[0].ssrc = htonl(newssrcr);
                if(ctx) janus_rtcp_incoming_rr(ctx, rr); // 更新 RTT/jitter/loss
            }
            break;
        }
        case RTCP_RTPFB: {
            // NACK, TWCC — 修复 sender SSRC 和 media SSRC
            rtcpfb->ssrc = htonl(newssrcl);     // 发送者 SSRC
            rtcpfb->media = htonl(newssrcr);    // 媒体源 SSRC
            if(rtcp->rc == 15)  // TWCC
                janus_rtcp_incoming_transport_cc(ctx, rtcpfb, total);
            break;
        }
        case RTCP_PSFB: {
            // PLI, FIR, REMB — 修复 sender SSRC 和 media SSRC
            rtcpfb->ssrc = htonl(newssrcl);
            if(rtcp->rc == 1) { /* PLI */ }
            else if(rtcp->rc == 4) { /* FIR */ }
            else if(rtcp->rc == 15) { /* REMB */ }
            break;
        }
    }
    // 支持 Compound RTCP 包：遍历所有子报文
}
```

### 5.3 RTCP 入向统计更新

在 `janus_rtcp_fix_ssrc` 中（fixssrc=0 模式），自动更新 context 统计：

#### janus_rtcp_incoming_sr()（rtcp.c:226-235）
```c
ctx->lsr_ts = janus_get_monotonic_time();   // 收到 SR 的时间
uint64_t ntp = (ntohl(sr->si.ntp_ts_msw) << 32) | ntohl(sr->si.ntp_ts_lsw);
ctx->lsr = (ntp >> 16);                     // NTP 中 32 位 = LSR
```

#### janus_rtcp_incoming_rr()（rtcp.c:402-441）
```c
// 更新远程丢包和 jitter
ctx->lost_remote = total;                    // 远端报告的累计丢包
ctx->jitter_remote = jitter;                 // 远端计算的 jitter

// 计算 RTT
uint32_t a = (uint32_t)(temp >> 16);          // 当前 NTP 中 32 位
uint32_t rtt = a - lsr - dlsr;               // RTT = 当前时间 - 上次SR时间 - 延迟

// 更新出向链路质量 (rtcp.c:355-399)
janus_rtcp_rr_update_stats(ctx, rr->rb[0]);  // 根据 NACK 数和丢包数计算质量
```

**出向链路质量计算**：
```
out_link_quality = 100 * (1 - nacks_since_last_rr / sent_packets_since_last_rr)
out_media_link_quality = 100 * (1 - newly_lost_packets / expected_packets)
```

### 5.4 janus_rtcp_filter()（rtcp.c:729-845）

**过滤**传出给对端的 RTCP 包，删除不需要的类型：

```c
char *janus_rtcp_filter(char *packet, int len, int *newlen) {
    switch(rtcp->type) {
        case RTCP_SR:         keep = TRUE; break;
        case RTCP_RR:         keep = TRUE; break;
        case RTCP_SDES:
            // 只保留有 CNAME 的 SDES
            keep = (item.type == 1); break;
        case RTCP_BYE:        keep = TRUE; break;  // 保留
        case RTCP_APP:        keep = TRUE; break;  // 保留
        case RTCP_FIR:        keep = TRUE; break;  // 保留
        case RTCP_PSFB:
            if(rc == 1) keep = TRUE;     // PLI
            // REMB (rc=15) → keep = FALSE（Janus 自己生成）
            break;
        case RTCP_RTPFB:
            if(rc == 1) keep = FALSE;     // NACK → 自己处理
            if(rc == 15) keep = FALSE;    // TWCC → 自己处理
            break;
        case RTCP_XR:          keep = FALSE; break; // Janus 自己生成 RR/SR
        default:               keep = FALSE; break;
    }
}
```

**设计哲学**：Janus 自己处理 NACK（重传）和 TWCC（拥塞控制分析），不透明转发这些反馈给远端，但保留 SR/RR/SDES/PLI/FIR 等需要端到端传递的消息。

### 5.5 janus_rtcp_fix_report_data()（rtcp.c:1048-1116）

修复 SR/RR 中的 Report Block 数据（序列号、时间戳）：

```c
// 修复 SR 的 RTP timestamp
uint32_t sr_ts = ntohl(sr->si.rtp_ts);
uint32_t fix_ts = (sr_ts - base_ts) + base_ts_prev;  // 应用 switching context 偏移
sr->si.rtp_ts = htonl(fix_ts);

// 修复 SR/RR 的 Report Block SSRC
sr->rb[0].ssrc = htonl(ssrc_local);  // 替换为 Janus 的本地 SSRC

// 修复 SR 的发送者 SSRC
sr->ssrc = htonl(ssrc_peer);         // 替换为远端知晓的 SSRC
```

---

## 六、Simulcast RTP 处理（rtp.c:1203-1430）

### 6.1 janus_rtp_simulcasting_context_process_rtp()

当收到 RTP 包时，判断该包属于哪个 simulcast substream，并决定是否转发：

```
1. 识别 substream：
   - SSRC 匹配 ssrcs[0] → substream 0
   - SSRC 匹配 ssrcs[1] → substream 1
   - SSRC 匹配 ssrcs[2] → substream 2
   - 都不匹配 → 解析 rid 扩展，匹配 rids[0..2] 并更新 ssrcs[]

2. 初始化状态：
   - 如果还没选定 substream → 等到第一个 keyframe 后选定

3. 切换检测：
   - 当前 substream != target → 等待目标层的 keyframe
   - 收到 keyframe 后切换，设置 changed_substream = TRUE

4. 超时降级：
   - 如果当前 substream > 0 且超过 drop_trigger（默认 250ms）未收到包
   → 自动降级到 substream_target_temp - 1
   → 设置 need_pli = TRUE（请求低层 keyframe）

5. 时间层过滤（VP8/VP9/AV1）：
   - VP8：解析 TID（temporal layer ID），丢弃高于 templayer 的包
   - VP9：解析 SVC info，同 VP8 逻辑
   - AV1：解析 Dependency Descriptor 中的 template temporal layer
```

### 6.2 keyframe 检测支持的 codec

```c
janus_vp8_is_keyframe(payload, plen)
janus_vp9_is_keyframe(payload, plen)
janus_h264_is_keyframe(payload, plen)
janus_av1_is_keyframe(payload, plen)
janus_h265_is_keyframe(payload, plen)
```

---

## 七、SRTP 抽象层（rtpsrtp.h）

### 7.1 libsrtp v1 vs v2 兼容

```c
#ifdef HAVE_SRTP_2
    #include <srtp2/srtp.h>
#else
    #include <srtp/srtp.h>
    // 旧版 API 别名映射
    #define srtp_err_status_t err_status_t
    #define srtp_err_status_ok err_status_ok
#endif
```

### 7.2 SRTP 密钥长度

| Profile | Master Key | Master Salt | Total |
|---------|-----------|-------------|-------|
| AES_CM_128 (SHA1_32/80) | 16 字节 | 14 字节 | 30 字节 |
| AES_GCM_128 | 16 字节 | 12 字节 | 28 字节 |
| AES_GCM_256 | 32 字节 | 12 字节 | 44 字节 |

### 7.3 SRTP Profile 枚举

```c
typedef enum janus_srtp_profile {
    JANUS_SRTP_AES128_CM_SHA1_32 = 1,   // SRTP_AES128_CM_SHA1_32
    JANUS_SRTP_AES128_CM_SHA1_80,       // SRTP_AES128_CM_SHA1_80
    JANUS_SRTP_AEAD_AES_128_GCM,        // AEAD_AES_128_GCM
    JANUS_SRTP_AEAD_AES_256_GCM         // AEAD_AES_256_GCM
} janus_srtp_profile;
```

---

## 八、综合总结

### 8.1 RTCP 反馈类型在 Janus 中的处理决策

| 反馈类型 | 接收 | 生成 | 转发 | 处理方式 |
|----------|------|------|------|----------|
| SR | 更新 LS/LSR | 定期生成 | 修复 SSRC 后转发 | `fix_ssrc` + `fix_report_data` |
| RR | 更新 RTT/loss/jitter | 定期生成 | 修复 SSRC 后转发 | `fix_ssrc` + `fix_report_data` |
| NACK | 解析 → 缓存查找 → 重传 | 检测到丢包时生成 | **不转发** | 自己处理，`filter` 中删除 |
| PLI | 转发给发送端 | 需要关键帧时生成 | 转发 | PSFB FMT=1 |
| FIR | 转发给发送端 | 需要关键帧时生成 | 转发 | PSFB FMT=4 |
| REMB | 解析码率 | 限制发送端时生成 | **不转发** | 自己处理，`filter` 中删除 |
| TWCC | 解析延迟 | （待实现） | **不转发** | 解析但 TODO 更新 context |
| XR | - | - | **不转发** | Janus 自己生成 RR/SR |

### 8.2 关键设计模式

1. **B2BUA 的 SSRC 修复**：Janus 重写 SSRC 后，必须在 RTCP 中修复回来，保证端到端的 SSRC 一致性
2. **NACK 的 SFU 处理**：不盲目转发 NACK，而是在 SFU 层面完成重传，减少端到端延迟
3. **RTCP 过滤**：删除 SFU 自己能处理的 RTCP 类型，只转发端到端必需的消息

---

## 九、下一步（W10）

**目标**：RTP/RTCP 转发对比 SIP 网关 + 综合整理

1. 对比 SIP 网关（如 Asterisk/FreeSWITCH）的 RTP 转发方式
2. RTP Proxy vs RTP Forwarding 的架构差异
3. SIP 网关如何处理 RTCP
4. 综合整理 Janus RTP/RTCP 转发的完整链路

---

**学习进度**：✅ W9 周一-周四（RTP 结构与扩展+Switching+RTCP 类型与 Context+转发链路） ✅ W9 周五-周日（NACK/PLI/REMB/TWCC/SSRC修复/过滤）

**当前任务**：进入 W10（对比 SIP 网关 + 综合整理）→ 见 `week10_notes.md`
