# 第十一周学习笔记：NACK 策略深入

**日期**：2026年6月第1-2周
**目标**：深入理解 Janus NACK 队列管理、重传退避策略、RTX 包处理、及作为接收方的 NACK 生成逻辑

---

## 一、NACK 在 Janus 中的两个视角

Janus 作为 SFU 同时扮演两个角色：

```
视角 1：Janus 作为接收方（入站路径）
  Peer A → Janus
  Janus 检测丢包 → 生成 NACK → 发给 Peer A

视角 2：Janus 作为发送方（出站路径）
  Peer B → Janus（NACK）→ Janus 查缓存 → 重传 RTP 包 → Peer B
```

两种视角的策略完全不同，下面分别展开。

---

## 二、Janus 作为发送方：NACK 缓存与重传

### 2.1 缓存数据结构（ice.h:589-609）

每个 `janus_ice_peerconnection_medium` 中有两个容器：

```c
GQueue *retransmit_buffer;       // 按时间排序的 RTP 包队列（FIFO）
GHashTable *retransmit_seqs;     // seq_no → janus_rtp_packet* 的哈希表（O(1) 查找）
```

缓存的包结构（rtp.h:61-68）：

```c
typedef struct janus_rtp_packet {
    char *data;               // SRTP 加密后的 RTP 包数据
    gint length;              // 包长度
    gint64 created;           // 入缓存的时间（单调时钟，微秒）
    gint64 last_retransmit;   // 上次重传的时间
    gint64 current_backoff;   // 当前退避时间
    janus_plugin_rtp_extensions extensions;
} janus_rtp_packet;
```

**为什么同时用 GQueue 和 GHashTable？**

- `GQueue`：按时间顺序插入，方便从头部淘汰过期包（FIFO）
- `GHashTable`：收到 NACK 时按 seq_no 直接定位，O(1) 查找

这是一种经典的双索引缓存设计。

### 2.2 包入缓存时机（ice.c:4917-5035）

出站路径中，Janus 转发 RTP 包后，将其缓存以备重传：

**路径 A：视频 + RFC4588 RTX 模式（ice.c:4917-4945）**

```
原始 RTP 包 → 在 SRTP 加密前缓存 → 再加密后发给对端

缓存时：原始 seq_no 被前置到 payload 的前 2 字节
  原始包: [RTP header][payload]
  缓存包: [RTP header][2字节OSN][payload]    ← OSN = Original Sequence Number

之后收到 NACK 重传时，用 RTX SSRC 和 RTX PT 伪造新头，OSN 供接收方还原
```

**路径 B：普通模式（音频，或未协商 RTX 的视频）（ice.c:5009-5035）**

```
原始 RTP 包 → SRTP 加密 → 发给对端 → 加密后的包直接缓存

缓存时：
  p->created = janus_get_monotonic_time();
  p->last_retransmit = 0;     // 尚未重传
  p->current_backoff = 0;     // 退避从 0 开始
```

### 2.3 缓存清理（ice.c:679-704）

```c
static void janus_cleanup_nack_buffer(gint64 now, janus_ice_peerconnection *pc,
    gboolean force, gboolean keyframe) {

    while(medium->retransmit_buffer) {
        janus_rtp_packet *p = g_queue_peek_head(medium->retransmit_buffer);
        // 超时判断：当前时间 - 创建时间 > nack_queue_ms * 1000 微秒
        if(!force && (now - p->created < (gint64)medium->nack_queue_ms * 1000))
            break;    // 还没过期，停止清理
        // 过期了，从双索引中删除
        g_queue_pop_head(medium->retransmit_buffer);
        g_hash_table_remove(medium->retransmit_seqs, GUINT_TO_POINTER(seq));
        janus_rtp_packet_free(p);
    }
}
```

**触发时机**：
1. 定期清理：出站流量处理中周期性调用
2. 关键帧请求时：`janus_cleanup_nack_buffer(0, pc, FALSE, TRUE)` — 旧帧的包已无重传价值
3. 强制清理：连接断开时 `force=TRUE`

### 2.4 NACK 队列大小动态调整（ice.c:3141-3154）

`nack_queue_ms` 不是固定值，根据 RTT 动态调整：

```c
// 收到 RR 后，解析 RTT
uint16_t nack_queue_ms = medium_rtt + 100;  // 基础值 = RTT + 100ms

if(nack_queue_ms > DEFAULT_MAX_NACK_QUEUE)        // 上限 1000ms
    nack_queue_ms = DEFAULT_MAX_NACK_QUEUE;
else if(nack_queue_ms < min_nack_queue)           // 下限 200ms（默认）
    nack_queue_ms = min_nack_queue;

// 指数移动平均平滑（7/8 权重给旧值）
uint16_t mavg = rtt ? ((7*medium->nack_queue_ms + nack_queue_ms)/8) : nack_queue_ms;
// 再次 clamp
medium->nack_queue_ms = mavg;
```

**设计逻辑**：

```
为什么是 RTT + 100ms？

  Peer B 丢了 seq=102
       │
       ├── [网络延迟 RTT/2] → Janus 收到 NACK
       ├── 查找缓存，重传
       └── [网络延迟 RTT/2] → Peer B 收到重传

  从丢包到收到重传最短需要 ≈ 1 个 RTT
  加上 NACK 可能在 RTCP 定时器中等一小段时间
  所以 RTT + 100ms 是"重传包应该仍有效的最保守窗口"

超过这个窗口的包，即使重传对端也来不及用，不如释放内存
```

**配置来源**：

| 方式 | 说明 |
|------|------|
| 命令行 `--min-nack-queue` | 设置 `min_nack_queue` 下限 |
| 配置文件 `min_nack_queue` | `[media]` 段 |
| Admin API `set_min_nack_queue` | 运行时修改 |
| 默认值 | 200ms |

---

## 三、NACK 重传退避策略（ice.c:3169-3248）

### 3.1 核心常量

```c
#define DEFAULT_MIN_NACK_QUEUE   200       // NACK 队列下限 200ms
#define DEFAULT_MAX_NACK_QUEUE   1000      // NACK 队列上限 1000ms
#define MAX_NACK_IGNORE          1000000   // 最大退避 1,000,000us = 1s
#define MIN_NACK_IGNORE          40000     // 初始退避 40,000us = 40ms
```

### 3.2 处理流程

收到对端发来的 NACK 后，Janus 逐个处理请求重传的 seq_no：

```
收到 NACK 中的 seq_no 列表
  │
  ├─ 对每个 seq_no:
  │    │
  │    ├─ g_hash_table_lookup(retransmit_seqs, seq_no)
  │    │    └─ 未找到 → 包已过期被清理，跳过
  │    │
  │    ├─ 检查退避条件：
  │    │    if(last_retransmit > 0 && now - last_retransmit < current_backoff)
  │    │    → 距上次重传还不够久，跳过
  │    │
  │    ├─ 执行重传：
  │    │    last_retransmit = now
  │    │    更新退避：
  │    │      if(current_backoff == 0)
  │    │          current_backoff = 40ms        ← 第一次重传后
  │    │      else
  │    │          current_backoff *= 2          ← 指数退避
  │    │          if(current_backoff > 1s)
  │    │              current_backoff = 1s      ← 上限 1s
  │    │
  │    └─ 发送重传包（两种模式见下文）
  │
  └─ 从 RTCP 中移除已处理的 NACK（janus_rtcp_remove_nacks）
```

### 3.3 退避时间线示例

```
seq=102 的包被缓存

T=0ms     缓存该包（current_backoff=0, last_retransmit=0）
T=50ms    收到 NACK for seq=102
          → last_retransmit=0，不触发退避，立即重传
          → last_retransmit=50ms, current_backoff=40ms

T=80ms    又收到 NACK for seq=102
          → now-last_retransmit = 30ms < 40ms → 跳过

T=110ms   又收到 NACK for seq=102
          → now-last_retransmit = 60ms > 40ms → 重传
          → current_backoff = 80ms

T=150ms   又收到 NACK for seq=102
          → now-last_retransmit = 40ms < 80ms → 跳过

T=210ms   又收到 NACK for seq=102
          → now-last_retransmit = 100ms > 80ms → 重传
          → current_backoff = 160ms

...以此类推，退避时间：40→80→160→320→640→1000(cap)→1000...
```

### 3.4 为什么没有"最大重传次数"？

Janus **没有**对单个包设置最大重传次数限制。它依赖两个天然的上限：

1. **缓存超时**：包在 `nack_queue_ms` 后被清理，之后 NACK 找不到包就自动停止
2. **指数退避**：退避从 40ms 增长到 1s，重传频率越来越低，对带宽的影响趋近于零

这种设计避免了复杂的状态管理（每个包维护一个重传计数器），同时保证了"如果对端持续没收到，总会偶尔再试一次"。

---

## 四、重传包的两种发送模式

### 4.1 非 RTX 模式（同一 SSRC 重传）

```
收到 seq=102 的 NACK
  → 直接从 retransmit_seqs 找到缓存的包（已 SRTP 加密）
  → 直接发送（pkt->encrypted = TRUE，跳过加密）

特点：
  - 包的 SSRC、PT、seq 都不变
  - 接收方通过时间戳或 seq 重复检测来识别重传包
  - 简单但有歧义：接收方统计时需要区分首次传输和重传
```

### 4.2 RFC4588 RTX 模式（独立 SSRC 重传）

```
收到 seq=102 的 NACK
  → 找到缓存的原始包
  → 重写 RTP 头：
      payload_type = rtx_payload_type       （如 96→97）
      ssrc        = ssrc_rtx               （如 1000→1001）
      seq_number  = rtx_seq_number++       （独立递增计数器）
  → payload 前插入 2 字节 OSN（Original Sequence Number = 102）
  → 重新 SRTP 加密后发送

接收方收到 RTX 包后：
  → 识别 RTX SSRC → 还原 PT、SSRC、seq → 从 OSN 恢复原始 seq
  → 明确知道这是重传包，统计为 retransmitted
```

**RTX 包结构对比**：

```
原始包:
┌──────────┬──────────────────────┐
│ RTP 头   │   Payload            │
│ PT=96    │   (视频数据)          │
│ SSRC=1k  │                      │
│ seq=102  │                      │
└──────────┴──────────────────────┘

RTX 重传包:
┌──────────┬──────┬──────────────┐
│ RTP 头   │ OSN  │  Payload     │
│ PT=97    │ 102  │  (视频数据)   │
│ SSRC=1k1 │(2字节)│              │
│ seq=5k   │      │              │
└──────────┴──────┴──────────────┘
```

### 4.3 两种模式的统计差异

源码 rtcp.c:848-930 中 `janus_rtcp_process_incoming_rtp()` 的逻辑：

| 场景 | 计数方式 |
|------|----------|
| 非 RTX，乱序到达，时间差 > 120ms | `retransmitted++` |
| 非 RTX，乱序到达，时间差 ≤ 120ms | `received++`（误判为正常乱序） |
| RTX SSRC 到达 | `retransmitted++`（明确标记） |

这就是 RTX 模式的优势：统计精确，不会把重传包误算为正常包。

---

## 五、Janus 作为接收方：NACK 生成

### 5.1 丢包检测数据结构（ice.h:330-343）

```c
typedef struct janus_seq_info {
    gint64 ts;                       // 状态变更的时间戳
    guint16 seq;                     // 序列号
    guint16 state;                   // 当前状态
    struct janus_seq_info *next;
    struct janus_seq_info *prev;
} janus_seq_info;
```

状态枚举：

```c
enum {
    SEQ_MISSING,    // 检测到缺失
    SEQ_NACKED,     // 已发第一次 NACK，等待重传
    SEQ_GIVEUP,     // 已发第二次 NACK，放弃
    SEQ_RECVED      // 正常收到
};
```

### 5.2 丢包检测逻辑（ice.c:2984-3046）

```
收到 RTP 包 seq=N
  │
  ├─ 如果 N == expected_seq → 正常，标记 SEQ_RECVED
  │
  ├─ 如果 N > expected_seq → 有间隔，中间的包丢了
  │    ├─ 对 expected_seq ~ N-1 的每个 seq：
  │    │    创建 janus_seq_info，state=SEQ_MISSING, ts=当前时间
  │    └─ 更新 expected_seq = N+1
  │
  └─ 如果 N < expected_seq → 乱序到达
       └─ 在列表中找到该 seq，更新 state=SEQ_RECVED
```

### 5.3 NACK 生成时机（ice.c:707-708）

核心常量：

```c
#define SEQ_MISSING_WAIT   12000    // 12ms — 检测到缺失后等多久发第一次 NACK
#define SEQ_NACKED_WAIT   155000    // 155ms — 第一次 NACK 后等多久发第二次
```

状态转换与 NACK 生成：

```
SEQ_MISSING
  │
  ├─ 缺失持续 > 12ms → 发第一次 NACK → 转为 SEQ_NACKED
  │
  │  （其间如果包到了 → 转为 SEQ_RECVED，不发 NACK）
  │
SEQ_NACKED
  │
  ├─ 仍缺失 > 155ms（从首次检测算起）→ 发第二次 NACK → 转为 SEQ_GIVEUP
  │
  │  （其间如果重传包到了 → 转为 SEQ_RECVED）
  │
SEQ_GIVEUP
  │
  └─ 不再发 NACK，放弃该包
```

用时间线表示：

```
T=0ms      检测到 seq=102 缺失，标记 SEQ_MISSING
T=12ms     仍缺 → 发 NACK(PID=102)，标记 SEQ_NACKED
T=~50ms    重传到达 → 标记 SEQ_RECVED ✓

或者没有到达：
T=0ms      检测到 seq=102 缺失
T=12ms     发第一次 NACK
T=167ms    仍缺 → 发第二次 NACK，标记 SEQ_GIVEUP
T=167ms+   不再为 seq=102 发 NACK
```

### 5.4 为什么要等 12ms？

```
收到 seq=103, 104, 105
缺失 seq=102

情况 A：seq=102 只是乱序，马上就到
  → 如果立即发 NACK，白白浪费带宽
  → 等 12ms，如果到了就不用发

情况 B：seq=102 真丢了
  → 12ms 相比一帧间隔（33ms@30fps）足够短
  → 不会显著增加恢复延迟
```

12ms 是"乱序容忍"和"恢复速度"之间的折中值。

### 5.5 为什么只重试一次就放弃？

```
如果两次 NACK（间隔 155ms）后对端还没收到重传包：

  可能性 1：网络严重拥塞或断连，重传也传不过去
  可能性 2：包已不在对端的 NACK 缓存中（过期被清理）
  可能性 3：丢包率极高，重传包本身也丢了

  → 继续请求重传徒劳无益
  → 不如等下一个关键帧（通过 PLI 请求）
  → 或依赖 FEC 恢复（如果有的话）
```

### 5.6 RTX 重复包检测（ice.c:2779-2804）

当 Janus 收到 RTX 重传包时，需要判断是不是重复包：

```c
// rtx_nacked 是一个 GHashTable，key=seq, value=状态
// 状态 0: 未记录
// 状态 1: 已 NACK，首次收到重传
// 状态 2: 已收到过重传（重复）

if(state == 1) {
    // 首次收到重传，标记为 2
    g_hash_table_replace(medium->rtx_nacked[vindex],
        GUINT_TO_POINTER(seq), GINT_TO_POINTER(2));
} else if(state == 2) {
    // 重复的重传包，丢弃
    return;
} else if(state == 0 && rtx == 1) {
    // 未经 NACK 请求的 RTX 包（可能是对端自发重传），丢弃
    return;
}
```

清理机制：每个 NACK 过的 seq 在 5 秒后自动从 `rtx_nacked` 中移除。

---

## 六、关键帧请求时的 NACK 优化（ice.c:4908-4913）

```c
/* If we're sending a keyframe, clean up the NACK buffer:
 * there's no point in keeping old packets around, as we're
 * starting a new decode cycle anyway */
janus_cleanup_nack_buffer(0, pc, FALSE, TRUE);
```

**设计原理**：当 Janus 向对端发送关键帧时，旧帧的所有包都不再需要重传——解码器会从新关键帧重新开始解码。提前清理缓存可以释放内存，同时防止后续收到过期 NACK 时做无意义的重传。

---

## 七、NACK 相关配置参数汇总

| 参数 | 默认值 | 范围 | 来源 | 说明 |
|------|--------|------|------|------|
| `min_nack_queue` | 200ms | 0-1000ms | 命令行/配置文件 | NACK 缓存下限 |
| `nack_queue_ms` | 动态 | 200-1000ms | RTT 自适应 | 实际缓存超时 |
| `MIN_NACK_IGNORE` | 40ms | 固定 | 源码常量 | 重传退避起始值 |
| `MAX_NACK_IGNORE` | 1000ms | 固定 | 源码常量 | 重传退避上限 |
| `SEQ_MISSING_WAIT` | 12ms | 固定 | 源码常量 | 首次 NACK 等待 |
| `SEQ_NACKED_WAIT` | 155ms | 固定 | 源码常量 | 二次 NACK 等待后放弃 |
| `rtx_nacked` 清理 | 5s | 固定 | 源码常量 | RTX 包记录过期 |

---

## 八、NACK 在 Janus 中的完整时序图

```
Peer A (发布者)            Janus (SFU)              Peer B (订阅者)
     │                         │                         │
     │── RTP seq=100 ─────────>│── RTP seq=100 ─────────>│
     │── RTP seq=101 ─────────>│── RTP seq=101 ─────────>│
     │── RTP seq=102 ─────────>│    [seq=102 丢失]       │ 收到 seq=103
     │── RTP seq=103 ─────────>│── RTP seq=103 ─────────>│ 发现 seq=102 缺失
     │                         │                         │
     │                         │                         │ 等待 12ms...
     │                         │<── NACK PID=102 ────────│
     │                         │                         │
     │                    查找缓存 seq=102               │
     │                    找到 → 重传                    │
     │                         │── RTX seq=102 ──────────>│
     │                         │                         │
     │                         │                         │ 如果又丢失：
     │                         │                         │ 再等 155ms
     │                         │<── NACK PID=102 ────────│
     │                         │── RTX seq=102 ──────────>│
     │                         │                         │
     │                         │                         │ 如果还丢失：
     │                         │                         │ GIVEUP，不再 NACK
     │                         │                         │ 等下一个关键帧
```

---

## 九、下一步（W12）

**目标**：FEC 原理与 NACK vs FEC 场景选择

1. FEC 基本原理：XOR 纠删码
2. ULPFEC（RFC 5109）与 FlexFEC（RFC 8627）
3. Opus In-band FEC 机制
4. Janus 对 FEC 的处理策略（SDP 剥离 + 插件层 Opus FEC）
5. NACK vs FEC 场景选择决策框架
6. 动手 demo 设计思路

---

**学习进度**：✅ W3-8 完成（Janus 源码核心） ✅ W9-10 完成（RTP/RTCP 转发+对比整理） ✅ W11 完成（NACK 策略深入：缓存管理+退避+RTX+接收侧 NACK 生成）
**当前任务**：进入 W12（FEC 原理 + NACK vs FEC 场景选择）
