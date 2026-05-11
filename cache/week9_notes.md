# 第九周学习笔记：RTP/RTCP 转发机制（上）

**日期**：2026年5月第5-6周
**目标**：理解 RTP 包结构、RTP 扩展解析、RTP 转发链路、RTCP 包类型与处理

---

## 一、RTP 协议基础回顾

### 1.1 RTP 是什么？

**RTP**（Real-time Transport Protocol，RFC 3550）用于实时传输音视频数据。运行在 UDP 之上，提供序列号、时间戳、SSRC 等机制来支持接收端的排序、去重和同步。

### 1.2 RTP 固定头结构（12 字节）

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|V=2|P|X|  CC   |M|     PT      |       sequence number         |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                           timestamp                           |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|           synchronization source (SSRC) identifier            |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|            contributing source (CSRC) identifiers             |
|                             ...                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

| 字段 | 位宽 | 含义 |
|------|------|------|
| V | 2 | 版本号，固定为 2 |
| P | 1 | 填充标志，末尾有填充字节 |
| X | 1 | 扩展标志，头后有扩展 |
| CC | 4 | CSRC 计数 |
| M | 1 | 标记位（视频帧边界等） |
| PT | 7 | 负载类型（如 111=Opus, 96=VP8） |
| seq_number | 16 | 序列号，每发一个包+1 |
| timestamp | 32 | 采样时间戳 |
| SSRC | 32 | 同步源标识符 |

---

## 二、Janus 中的 RTP 实现（rtp.h / rtp.c）

### 2.1 文件概览

| 文件 | 行数 | 作用 |
|------|------|------|
| `rtp.h` | 510 行 | RTP 头定义、扩展类型常量、codec 枚举、switching/simulcast/SVC context |
| `rtp.c` | 1773 行 | RTP 头解析、扩展查找/解析/设置、switching context、skew 补偿、simulcast 处理 |
| `rtcp.h` | 542 行 | RTCP 包类型定义、结构体（SR/RR/NACK/FIR/PLI/REMB/TWCC）、context |
| `rtcp.c` | 1914 行 | RTCP 解析、fix_ssrc、filter、NACK 生成/解析、REMB 生成/cap、PLI/FIR 生成 |
| `rtpfwd.h` | 139 行 | RTP forwarder（将 RTP 流转发到外部 UDP 地址） |
| `rtpsrtp.h` | 68 行 | SRTP 抽象层（兼容 libsrtp 1.x 和 2.x） |

### 2.2 janus_rtp_header（rtp.h:36-58）

Janus 定义了与 RFC 3550 完全一致的 RTP 头，**大小端兼容**：

```c
typedef struct rtp_header {
#if __BYTE_ORDER == __BIG_ENDIAN
    uint16_t version:2;       // V=2
    uint16_t padding:1;       // P
    uint16_t extension:1;     // X
    uint16_t csrccount:4;     // CC
    uint16_t markerbit:1;     // M
    uint16_t type:7;          // PT
#elif __BYTE_ORDER == __LITTLE_ENDIAN
    // 字段顺序相反（位域在内存中的布局不同）
    uint16_t csrccount:4;
    uint16_t extension:1;
    uint16_t padding:1;
    uint16_t version:2;
    uint16_t type:7;
    uint16_t markerbit:1;
#endif
    uint16_t seq_number;
    uint32_t timestamp;
    uint32_t ssrc;
    uint32_t csrc[0];         // 可变长 CSRC 列表
} rtp_header;
```

**关键点**：
- 使用 `#if __BYTE_ORDER` 条件编译处理大小端差异
- CSRC 是**柔性数组**（`csrc[0]`），实际长度由 CC 字段决定
- 所有多字节字段使用**网络字节序**（大端），读取时需要 `ntohs/ntohl`

### 2.3 janus_rtp_packet（rtp.h:61-68）

Janus 在对端重传时使用的包缓存结构：

```c
typedef struct janus_rtp_packet {
    char *data;                          // RTP 包原始数据
    gint length;                         // 数据长度
    gint64 created;                      // 创建时间（monotonic time）
    gint64 last_retransmit;              // 最后一次重传时间
    gint64 current_backoff;              // 当前退避时间
    janus_plugin_rtp_extensions extensions;  // 扩展信息
} janus_rtp_packet;
```

这个结构用于 NACK 触发的重传：核心缓存最近发送的 RTP 包，当收到 NACK 时直接从缓存中取出重传。

### 2.4 RTP 头扩展结构（rtp.h:71-74）

```c
typedef struct janus_rtp_header_extension {
    uint16_t type;       // 扩展类型标识（0xBEDE=1字节头 / 0x1000=2字节头）
    uint16_t length;     // 扩展数据长度（以 4 字节为单位）
} janus_rtp_header_extension;
```

**两种扩展格式**：
- **0xBEDE**（One-Byte Header）：每个扩展元素 1 字节 ID（高4位）+ 1 字节长度（低4位）
- **0x1000**（Two-Byte Header）：每个扩展元素 1 字节 ID + 1 字节长度，支持更大的 ID 和数据

### 2.5 核心辅助函数

#### janus_is_rtp() — 快速判断是否为 RTP 包
```c
gboolean janus_is_rtp(char *buf, guint len) {
    if (len < 12)
        return FALSE;
    janus_rtp_header *header = (janus_rtp_header *)buf;
    return ((header->type < 64) || (header->type >= 96));
}
```
**逻辑**：PT 在 0-63（静态）或 96-127（动态）范围，64-95 留给 RTCP。

#### janus_rtp_payload() — 获取 RTP 负载指针

跳过 12 字节固定头 → 跳过 CSRC（CC×4 字节）→ 跳过头扩展（如果有）→ 返回负载起始位置。

```c
char *janus_rtp_payload(char *buf, int len, int *plen) {
    janus_rtp_header *rtp = (janus_rtp_header *)buf;
    int hlen = 12;                              // 固定头
    if(rtp->csrccount)
        hlen += rtp->csrccount * 4;             // CSRC
    if(rtp->extension) {
        janus_rtp_header_extension *ext = (janus_rtp_header_extension *)(buf+hlen);
        int extlen = ntohs(ext->length) * 4;     // 扩展长度
        hlen += 4 + extlen;
    }
    if(plen)
        *plen = len - hlen;
    return buf + hlen;
}
```

---

## 三、RTP 扩展的解析（rtp.c:145-510）

### 3.1 扩展查找核心函数

`janus_rtp_header_extension_find()` 是内部静态函数，被所有扩展解析函数调用。它遍历 1-Byte 和 2-Byte 扩展，找到指定 ID 的扩展数据。

```c
// 1-Byte 扩展遍历逻辑
while(i < extlen) {
    extid = (uint8_t)buf[hlen+i] >> 4;   // 高4位 = 扩展ID
    if(extid == 0xF) break;              // 0xF = 保留/结束
    else if(extid == 0x0) { i++; continue; } // 0x0 = 填充
    *idlen = ((uint8_t)buf[hlen+i] & 0xF) + 1; // 低4位+1 = 数据长度
    i++;
    if(extid == id && ((i+*idlen) <= extlen)) {
        // 找到了！
    }
    i += *idlen;
}
```

### 3.2 Janus 支持的 RTP 扩展类型

| 常量名 | URI | 用途 |
|--------|-----|------|
| `JANUS_RTP_EXTMAP_AUDIO_LEVEL` | `urn:ietf:params:rtp-hdrext:ssrc-audio-level` | 音频电平 |
| `JANUS_RTP_EXTMAP_TOFFSET` | `urn:ietf:params:rtp-hdrext:toffset` | 时间偏移 |
| `JANUS_RTP_EXTMAP_ABS_SEND_TIME` | `http://www.webrtc.org/experiments/rtp-hdrext/abs-send-time` | 绝对发送时间 |
| `JANUS_RTP_EXTMAP_ABS_CAPTURE_TIME` | `http://www.webrtc.org/experiments/rtp-hdrext/abs-capture-time` | 绝对采集时间 |
| `JANUS_RTP_EXTMAP_VIDEO_ORIENTATION` | `urn:3gpp:video-orientation` | 视频方向 |
| `JANUS_RTP_EXTMAP_TRANSPORT_WIDE_CC` | `http://www.ietf.org/id/draft-holmer-rmcat-transport-wide-cc-extensions-01` | Transport-CC |
| `JANUS_RTP_EXTMAP_PLAYOUT_DELAY` | `http://www.webrtc.org/experiments/rtp-hdrext/playout-delay` | 播放延迟 |
| `JANUS_RTP_EXTMAP_MID` | `urn:ietf:params:rtp-hdrext:sdes:mid` | Media ID（BUNDLE） |
| `JANUS_RTP_EXTMAP_RID` | `urn:ietf:params:rtp-hdrext:sdes:rtp-stream-id` | RTP Stream ID（simulcast） |
| `JANUS_RTP_EXTMAP_REPAIRED_RID` | `urn:ietf:params:rtp-hdrext:sdes:repaired-rtp-stream-id` | 修复流 ID（RTX） |
| `JANUS_RTP_EXTMAP_DEPENDENCY_DESC` | `...dependency-descriptor...` | AV1 依赖描述 |
| `JANUS_RTP_EXTMAP_VIDEO_LAYERS` | `...video-layers-allocation00` | 视频层分配 |

### 3.3 关键扩展解析函数

| 函数 | 作用 |
|------|------|
| `janus_rtp_header_extension_parse_audio_level()` | 解析音频电平（VAD + level dBov） |
| `janus_rtp_header_extension_parse_video_orientation()` | 解析视频旋转/翻转（C/F/R1/R0） |
| `janus_rtp_header_extension_parse_mid()` | 解析 mid（用于 BUNDLE demux） |
| `janus_rtp_header_extension_parse_rid()` | 解析 rid（用于 simulcast 识别） |
| `janus_rtp_header_extension_parse_abs_send_time()` | 解析 abs-send-time（24位，用于 GCC） |
| `janus_rtp_header_extension_set_abs_send_time()` | **设置** abs-send-time（转发前更新） |
| `janus_rtp_header_extension_parse_transport_wide_cc()` | 解析 transport-wide seq number |
| `janus_rtp_header_extension_set_transport_wide_cc()` | **设置** transport-wide seq number |
| `janus_rtp_header_extension_replace_id()` | 替换扩展 ID（RTX 时 rid→repaired-rid） |

---

## 四、RTP Switching Context（rtp.h:308-315）

Janus 作为 SFU 转发 RTP 包时，可能会切换 SSRC（如 simulcast 切换），需要保证序列号和时间戳的**连续性**。

### 4.1 结构体

```c
typedef struct janus_rtp_switching_context {
    uint32_t last_ssrc, last_ts, base_ts, base_ts_prev, prev_ts, target_ts, start_ts;
    uint16_t last_seq, prev_seq, base_seq, base_seq_prev;
    gboolean ts_reset, seq_reset, new_ssrc;
    gint16 seq_offset;
    gint32 prev_delay, active_delay, ts_offset;
    gint64 last_time, reference_time, start_time, evaluating_start_time;
} janus_rtp_switching_context;
```

### 4.2 janus_rtp_header_update() 核心逻辑（rtp.c:844-902）

每次转发 RTP 包前调用，确保 seq/timestamp 连续递增：

```c
void janus_rtp_header_update(header, context, video, step) {
    uint32_t ssrc = ntohl(header->ssrc);
    uint32_t timestamp = ntohl(header->timestamp);
    uint16_t seq = ntohs(header->seq_number);

    // 1. 检测 SSRC 变化 → 标记 ts_reset = seq_reset = TRUE
    if(ssrc != context->last_ssrc) {
        context->last_ssrc = ssrc;
        context->ts_reset = TRUE;
        context->seq_reset = TRUE;
    }

    // 2. 时间戳重置：计算时间差偏移
    if(context->ts_reset) {
        context->base_ts_prev = context->last_ts;
        context->base_ts = timestamp;
        gint64 time_diff = janus_get_monotonic_time() - context->last_time;
        int khz = video ? 90 : 48;  // 视频 90kHz，音频 48kHz
        time_diff = (time_diff * khz) / 1000;
        context->base_ts_prev += (guint32)time_diff;
    }

    // 3. 序列号重置：记录基准 seq
    if(context->seq_reset) {
        context->base_seq_prev = context->last_seq;
        context->base_seq = seq;
    }

    // 4. 计算连续的 ts 和 seq
    context->last_ts = (timestamp - context->base_ts) + context->base_ts_prev;
    context->last_seq = (seq - context->base_seq) + context->base_seq_prev + 1;

    // 5. 写回 RTP 头
    header->timestamp = htonl(context->last_ts);
    header->seq_number = htons(context->last_seq);
    context->last_time = janus_get_monotonic_time();
}
```

**为什么需要 switching context？**
- 接收端（浏览器）期望 seq 和 timestamp **单调递增**
- 当 SFU 切换 SSRC（如从高清流切换到低清流），新 SSRC 的 seq/ts 可能从任意值开始
- Switching context 重新计算连续的 seq/ts，避免浏览器检测到跳变

### 4.3 RTP Skew 补偿（rtp.c:700-842）

当音视频源时钟频率漂移时，需要补偿时间戳偏移，避免缓冲区溢出或欠载。

```c
janus_rtp_skew_compensate_audio(header, context, now)
janus_rtp_skew_compensate_video(header, context, now)
```

**核心思路**：
- 比较实际到达时间与预期到达时间的差异
- 如果超过阈值（audio 120ms, video 120ms），调整 ts_offset 和 seq_offset
- 源**变慢**（offset > skew_th）：增加 ts_offset，跳跃 seq（skip packets）
- 源**变快**（offset < -skew_th）：减少 ts_offset，减少 seq

---

## 五、Janus 支持的 Codec（rtp.h:122-149 / rtp.c:983-1137）

### 5.1 音频 Codec 及 Payload Type

| Codec | 枚举 | PT | 时钟频率 |
|-------|------|-----|---------|
| Opus | `JANUS_AUDIOCODEC_OPUS` | 111 | 48000 Hz |
| MultiOpus | `JANUS_AUDIOCODEC_MULTIOPUS` | 111 | 48000 Hz |
| OpusRED | `JANUS_AUDIOCODEC_OPUSRED` | 120 | 48000 Hz |
| PCMU | `JANUS_AUDIOCODEC_PCMU` | 0 | 8000 Hz |
| PCMA | `JANUS_AUDIOCODEC_PCMA` | 8 | 8000 Hz |
| G.722 | `JANUS_AUDIOCODEC_G722` | 9 | 8000 Hz |
| ISAC 32K | `JANUS_AUDIOCODEC_ISAC_32K` | 104 | 32000 Hz |
| ISAC 16K | `JANUS_AUDIOCODEC_ISAC_16K` | 103 | 16000 Hz |
| L16 48K | `JANUS_AUDIOCODEC_L16_48K` | 105 | 48000 Hz |
| L16 16K | `JANUS_AUDIOCODEC_L16_16K` | 106 | 16000 Hz |

### 5.2 视频 Codec 及 Payload Type

| Codec | 枚举 | PT | 时钟频率 |
|-------|------|-----|---------|
| VP8 | `JANUS_VIDEOCODEC_VP8` | 96 | 90000 Hz |
| VP9 | `JANUS_VIDEOCODEC_VP9` | 101 | 90000 Hz |
| H.264 | `JANUS_VIDEOCODEC_H264` | 107 | 90000 Hz |
| AV1 | `JANUS_VIDEOCODEC_AV1` | 98 | 90000 Hz |
| H.265 | `JANUS_VIDEOCODEC_H265` | 100 | 90000 Hz |

**关键点**：
- 音频默认 48kHz（Opus），G.711/G.722 为 8kHz
- 视频统一 90kHz 时钟
- `janus_audiocodec_from_name()` / `janus_videocodec_from_name()` 用于 SDP 解析时字符串→枚举转换

---

## 六、RTCP 协议基础

### 6.1 RTCP 包类型（rtcp.h:31-41）

```c
typedef enum {
    RTCP_FIR   = 192,  // Full Intra Request（已废弃，但兼容）
    RTCP_SR    = 200,  // Sender Report
    RTCP_RR    = 201,  // Receiver Report
    RTCP_SDES  = 202,  // Source Description（CNAME）
    RTCP_BYE   = 203,  // Goodbye
    RTCP_APP   = 204,  // Application-defined
    RTCP_RTPFB = 205,  // RTP Feedback（NACK, TWCC）
    RTCP_PSFB  = 206,  // Payload-Specific Feedback（PLI, FIR, REMB）
    RTCP_XR    = 207,  // Extended Reports
} rtcp_type;
```

### 6.2 RTCP 通用头（8 字节）

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|V=2|P|    RC   |      PT       |          length               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

- **RC**（5 bits）：Report Count，SR/RR 中表示 Report Block 数量，FB 中表示 FMT
- **length**：RTCP 包长度（以 4 字节为单位，**不包含第一个 word**），即 `length = (总字节数/4) - 1`

### 6.3 关键 RTCP 结构体

#### Sender Report（rtcp.h:87-94）
```c
typedef struct rtcp_sr {
    rtcp_header header;        // PT=200, RC=report block 数量
    uint32_t ssrc;             // 发送者 SSRC
    sender_info si;            // NTP 时间戳 + RTP 时间戳 + 发包计数 + 字节计数
    report_block rb[1];        // 可变数量的 Report Block
} rtcp_sr;
```

#### Receiver Report（rtcp.h:97-103）
```c
typedef struct rtcp_rr {
    rtcp_header header;        // PT=201
    uint32_t ssrc;             // 发送者 SSRC
    report_block rb[1];        // 可变数量的 Report Block
} rtcp_rr;
```

#### Report Block（rtcp.h:75-84）
```c
typedef struct report_block {
    uint32_t ssrc;             // 被报告的 SSRC
    uint32_t flcnpl;           // fraction lost(8) + cumulative packets lost(24)
    uint32_t ehsnr;            // extended highest sequence number received
    uint32_t jitter;           // interarrival jitter
    uint32_t lsr;              // last SR timestamp
    uint32_t delay;            // delay since last SR (DLSR)
} report_block;
```

---

## 七、janus_rtcp_context 状态机（rtcp.h:228-287）

每个媒体流维护一个 RTCP context，跟踪所有统计信息：

```c
typedef struct rtcp_context {
    // 收包状态
    uint8_t rtp_recvd:1;
    uint32_t rtp_last_inorder_ts;
    int64_t rtp_last_inorder_time;

    // 序列号
    uint16_t max_seq_nr;
    uint16_t seq_cycle;       // 序列号回绕次数
    uint16_t base_seq;

    // Jitter 计算（RFC 3550 A.8）
    int64_t transit;
    double jitter, jitter_remote;
    uint32_t tb;              // 时钟频率（如 48000/90000）

    // RTT 计算
    uint32_t lsr;             // Last SR (NTP 中 32 bits)
    int64_t lsr_ts;           // LS 收到时的 monotonic time

    // 丢包统计（RFC 3550 A.3）
    uint32_t received, received_prior;
    uint32_t expected, expected_prior;
    int32_t lost, lost_remote;
    uint32_t retransmitted, retransmitted_prior;

    // 链路质量
    double in_link_quality;          // 入向链路质量（物理丢包）
    double in_media_link_quality;    // 入向媒体质量（含重传后）
    double out_link_quality;         // 出向链路质量
    double out_media_link_quality;   // 出向媒体质量
} rtcp_context;
```

---

## 八、RTCP 核心处理函数

### 8.1 janus_rtcp_process_incoming_rtp()（rtcp.c:848-930）

**每次收到 RTP 包时调用**，更新 RTCP context：

```
1. 更新时钟频率（tb）
2. 获取 seq_number
3. 判断是否为首包 → 初始化 base_seq
4. 序包判断：
   - 非 RTX + 序包：received++, max_seq_nr更新, expected更新, jitter更新
   - 非 RTX + 乱序（有 RTX channel）：received++（算作正常到达）
   - 非 RTX + 乱序（无 RTX channel + 有NACK）：判断是否重传（时间戳倒退>120ms）
   - RTX 包：retransmitted++
5. rtp_recvd = 1 → 可以开始发送 RR
```

**乱序/重传检测逻辑**：
```c
// 无 RTX channel 但支持 NACK 时，判断是否为重传
int32_t rtp_diff = ntohl(rtp->timestamp) - ctx->rtp_last_inorder_ts;
int64_t ms_diff = ((int64_t)abs(rtp_diff) * 1000) / ctx->tb;
if (ms_diff > 120)   // 时间戳倒退超过 120ms → 重传
    ctx->retransmitted++;
else
    ctx->received++;
```

### 8.2 janus_rtcp_report_block()（rtcp.c:1017-1046）

**生成 Report Block** 用于 SR/RR：

```c
int janus_rtcp_report_block(ctx, rb) {
    rb->jitter = htonl((uint32_t)ctx->jitter);
    rb->ehsnr = htonl((ctx->seq_cycle << 16) + ctx->max_seq_nr);
    // 计算累计丢包
    uint32_t expected_interval = ctx->expected - ctx->expected_prior;
    uint32_t received_interval = ctx->received - ctx->received_prior;
    int32_t lost_interval = expected_interval - received_interval;
    ctx->lost += lost_interval;
    // 计算 fraction lost (丢包率)
    rb->flcnpl = htonl(reported_lost | reported_fraction);
    // 设置 LSR 和 DLSR（用于 RTT 计算）
    rb->lsr = htonl(ctx->lsr);
    rb->delay = htonl(((now - ctx->lsr_ts) << 16) / 1000000);
    // 更新 prior 值
    ctx->expected_prior = ctx->expected;
    ctx->received_prior = ctx->received;
}
```

### 8.3 链路质量估算（rtcp.c:993-1015）

```c
// 入向链路质量（物理丢包，不含重传）
link_lost = expected_interval - received_interval;
link_q = 100.0 - (100.0 * link_lost / expected_interval);

// 入向媒体质量（含重传后）
media_lost = expected_interval - (received_interval + retransmitted_interval);
media_link_q = 100.0 - (100.0 * media_lost / expected_interval);
```

两次估计值通过**一阶低通滤波器**平滑：`filtered = 0.667 * last + 0.333 * new`

---

## 九、RTP 转发链路：从插件到网络

### 9.1 转发流程图

```
Plugin                         Janus Core                          Network
  │                                │                                  │
  │-- gateway->relay_rtp() ------->│                                  │
  │   (handle, video, buf, len)    │                                  │
  │                                │-- janus_ice_relay_rtp()         │
  │                                │   ├─ SRTP encrypt (send)        │
  │                                │   ├─ janus_rtp_header_update()  │
  │                                │   │   (switching context)       │
  │                                │   ├─ RTCP context update        │
  │                                │   │   (process_incoming_rtp)    │
  │                                │   ├─ Abs-Send-Time update       │
  │                                │   └─ Transport-CC update        │
  │                                │                                  │
  │                                │-- nice_agent_send() ──────────> │
  │                                │   (libnice UDP send)            │
  │                                │                                  │
  │                                │  [可选] 缓存包到 NACK 队列      │
  │                                │   janus_ice_nack_save_packet()  │
```

### 9.2 关键函数

| 函数 | 位置 | 作用 |
|------|------|------|
| `gateway->relay_rtp()` | plugin.h (callback) | 插件调用，请求转发 RTP |
| `janus_ice_relay_rtp()` | ice.c | 核心 RTP 转发入口 |
| `janus_rtp_header_update()` | rtp.c:844 | 保证 seq/ts 连续性 |
| `janus_rtcp_process_incoming_rtp()` | rtcp.c:848 | 更新 RTCP 统计 |
| `nice_agent_send()` | libnice | 实际 UDP 发送 |

### 9.3 RTP Forwarder 机制（rtpfwd.h）

Janus 还有一种**纯转发**机制——将 RTP 流直接转发到外部 UDP 地址，不经过 WebRTC 信令：

```c
typedef struct janus_rtp_forwarder {
    void *source;               // 所有者指针
    uint32_t stream_id;         // 流 ID
    int udp_fd;                 // 发送 socket
    gboolean is_video, is_data; // 流类型
    uint32_t ssrc;              // 要写入的 SSRC
    int payload_type;           // 要写入的 PT
    struct sockaddr_in serv_addr; // 目标地址
    janus_rtp_switching_context rtp_context;   // Switching context
    janus_rtp_simulcasting_context sim_context; // Simulcast 处理
    gboolean is_srtp;           // 是否 SRTP 加密
    srtp_t srtp_ctx;            // SRTP 上下文
    void (*rtcp_callback)(...); // RTCP 回调
} janus_rtp_forwarder;
```

**使用场景**：
- 将 Janus 中的流转发到 CDN/录制服务器
- 监控和分析用途
- 大规模部署的分层转发

### 9.4 接收方向的 RTP 处理

```
Network                          Janus Core                        Plugin
  │                                  │                                │
  │-- UDP packet ──────────────────>│                                │
  │   (nice_agent recv callback)     │                                │
  │                                  │-- janus_ice_cb_rtp_recv()     │
  │                                  │   ├─ SRTP decrypt             │
  │                                  │   ├─ RTCP context update      │
  │                                  │   ├─ jitter buffer handling   │
  │                                  │   └─ NACK queue handling      │
  │                                  │                                │
  │                                  │-- plugin->incoming_rtp() ---->│
  │                                  │   (handle, packet)            │
  │                                  │                                │
  │                                  │   (插件处理，如 echotest)     │
  │                                  │   → gateway->relay_rtp() ────>│
```

---

## 十、学习总结

### 10.1 关键概念回顾

1. **RTP 固定头**：12 字节，关键字段为 sequence_number（16bit）、timestamp（32bit）、SSRC（32bit）
2. **RTP 扩展**：1-Byte Header（0xBEDE）和 2-Byte Header（0x1000），Janus 支持 12 种扩展类型
3. **Switching Context**：解决 SSRC 切换时 seq/ts 连续性问题，每次转发前调用 `janus_rtp_header_update()`
4. **RTCP Context**：跟踪收发包统计、jitter、RTT、丢包、链路质量
5. **RTP Forwarder**：绕过信令直接转发 RTP 到外部 UDP 地址
6. **Codec 映射**：PT 111=Opus, 96=VP8, 101=VP9, 107=H264, 98=AV1, 100=H265

### 10.2 思考问题

1. **Janus 为什么要修改转发的 RTP 头？** — 因为作为 SFU，可能切换 SSRC（如 simulcast），需要保证 seq/ts 在接收端单调递增
2. **jitter 是如何计算的？** — RFC 3550 A.8：`J(i) = J(i-1) + (|D(i-1,i)| - J(i-1))/16`，其中 `D = 到达时间差 - RTP 时间戳差`
3. **链路质量和媒体质量有什么区别？** — 链路质量只看物理丢包，媒体质量还考虑重传恢复

---

## 十一、下一步（W9 后半周 + W10）

**目标**：NACK 重传、PLI 请求、RTCP 过滤与 Fix、对比 SIP 网关

1. NACK 的生成（`janus_rtcp_nacks()`）和解析（`janus_rtcp_get_nacks()`）
2. PLI/FIR 请求生成
3. `janus_rtcp_fix_ssrc()` 和 `janus_rtcp_filter()` — RTCP 包的 SSRC 修复和过滤
4. REMB 的生成与 cap
5. Transport-CC 反馈解析
6. Simulcast RTP 处理
7. 对比 SIP 网关的 RTP/RTCP 处理

---

**学习进度**：✅ W3-8 完成（主流程+插件架构+ICE+DTLS/SRTP+SDP） ✅ W9 周一-周四（RTP 结构与扩展+Switching Context+RTCP 类型与 Context+转发链路）

**当前任务**：继续 W9 周五-周日（NACK/PLI/REMB/TWCC）→ 见 `week9_part2_notes.md`
