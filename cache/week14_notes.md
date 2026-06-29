# 第十四周学习笔记：拥塞控制（下）— Janus 实现分析与 BBR 对比

**日期**：2026年6月第6周  
**目标**：分析 Janus 的实际拥塞控制处理链路、REMB 策略、slowlink 检测，对比 BBR 算法，形成拥塞控制综合认知

---

## 一、Janus 拥塞控制全景

### 1.1 核心结论：Janus 不做拥塞控制

Janus 的 TWCC 处理中有一个关键 TODO：

```c
/* rtcp.c:338 — janus_rtcp_incoming_transport_cc() 末尾 */
/* TODO Update the context with the feedback we got */
```

解析完 TWCC 反馈后，所有数据**直接丢弃**，没有更新任何带宽估计或码率控制上下文。

```
Janus 的 TWCC 数据流：

对端              Janus
  │                 │
  │── TWCC RTP 扩展 ──→ 写入 transport_seq          ✅ 已实现
  │── TWCC RTCP 反馈 ──→ 解析 run-length chunks      ✅ 已实现
  │                    → 解析 recv deltas             ✅ 已实现
  │                    → 更新带宽估计                  ❌ TODO
  │                    → 调整发送码率                  ❌ TODO
  │                    → 触发 AIMD                    ❌ 未实现
```

### 1.2 Janus 的拥塞控制策略

```
┌─────────────────────────────────────────────────────────────┐
│                    Janus 拥塞控制策略                         │
│                                                             │
│  1. SDP 协商时：启用 NACK + TWCC + REMB                      │
│     → 对端浏览器知道 Janus 支持这些功能                        │
│     → 浏览器会发送 REMB、TWCC、NACK 给 Janus                   │
│                                                             │
│  2. 接收端类行为：Janus 作为接收方                             │
│     → 检测丢包 → 生成 NACK → 请求对端重传                     │
│     → 收集 TWCC 到达时间 → 生成 TWCC 反馈 → 发给对端          │
│     → 从对端的 SR/RR 获得带宽反馈（不做进一步处理）              │
│                                                             │
│  3. 发送端类行为：Janus 作为发送方                             │
│     → 收到对端发来的 NACK → 查缓存 → 重传                     │
│     → 收到对端发来的 REMB → 解析并存储（remb_bitrate）         │
│     → 收到对端发来的 TWCC → 已解析但丢弃（TODO）              │
│     → 插件可选择性地对发布者发送 REMB 来限制码率               │
│                                                             │
│  4. 带宽管理：不做自适应                                      │
│     → 不由 Janus 核心控制发布者的码率                         │
│     → 插件层通过 REMB 可选地限制发布者码率                     │
│     → 没有动态的 GCC/BBR 实现                                │
└─────────────────────────────────────────────────────────────┘
```

为何 Janus 不实现 GCC？

```
1. Janus 是 SFU，不是终结点
   → 包级转发，不解码
   → 无法直接感知视频编码质量和码率的变化

2. 带宽管理在插件层更灵活
   → VideoRoom 可以通过 REMB 告诉发布者"限速"
   → Streaming 可以跟踪所有订阅者的最低 REMB
   → 不同的插件可以有不同的策略

3. 浏览器端的 GCC 更高效
   → 浏览器就在 GCC 算法的发送端
   → 通过 SDP 协商让浏览器启用 TWCC/REMB
   → Janus 只需透明转发或策略性限速
```

实际效果是：

```
                     REMB(上限5Mbps)
浏览器 A(发布者) ───────────────── Janus(VideoRoom)
                           │   带宽足够 → 转发
                           │   带宽不足 → 浏览器侧有 GCC 降码率
                           │
                           │   REMB(订阅者带宽受限)
                           └── 浏览器 B(订阅者), RTT 大的弱网
```

### 1.3 Janus 为什么还要收集 TWCC？

```
Janus 作为接收方（向对端发送 TWCC 反馈）：

  对端(发送方) ──RTP──→  Janus 收集到达时间
                          │
                          └── TWCC 反馈 → 对端浏览器
                                          │
                              浏览器 GCC 根据延迟梯度调整发送码率
                                          │
                              浏览器降码率（如果过载）
                                          │
                              发送码率降低 → Janus 接收压力降低

虽然 Janus 自己不用 TWCC，但 TWCC 让对端浏览器的 GCC 起作用
→ 间接形成了闭环
```

---

## 二、Janus TWCC 完整链路

### 2.1 TWCC 协商（SDP 层）

```c
/* janus.c:3270-3286 — merge 阶段添加全局属性 */
if(handle->do_transport_wide_cc) {
    janus_sdp_attribute *a = janus_sdp_attribute_create("extmap",
        "%d %s", handle->transport_wide_cc_ext_id,
        "http://www.ietf.org/id/draft-holmer-rmcat-transport-wide-cc-extensions-01");
    janus_sdp_add_attribute(anon, a);
}
```

SDP 中会携带 `a=extmap:<id> http://...transport-wide-cc-extensions-01` 属性，告知浏览器启用 TWCC。

### 2.2 出站写入 transport-seq（ice.c:3958-3968）

```c
if(pc->do_transport_wide_cc) {
    pc->transport_wide_cc_out_seq_num++;
    janus_rtp_header_extension_set_transport_wide_cc(
        buf, plen, pc->transport_wide_cc_out_seq_num);
}
```

**每个从 Janus 发出的 RTP 包都带一个单调递增的 transport_seq**。这个序列号是所有流的**全局共享计数器**（不区分音视频，不区分 SSRC）。

### 2.3 入站收集到达时间（ice.c:2751-2777）

```c
if(pc->do_transport_wide_cc) {
    // 解析 RTP 扩展中的 transport-seq
    janus_rtp_header_extension_parse_transport_wide_cc(
        buf, plen, pc->transport_wide_cc_ext_id, &transport_seq_num);

    // 处理 16 位 sequence number 回绕
    if(transport_seq_num < 0x0FFF && last_transport_seq > 0xF000)
        transport_wide_cc_cycles++;

    // 计算扩展后的 32 位逻辑序号
    seq = transport_wide_cc_cycles << 16 | transport_seq_num;

    // 记录到达时间（微秒）
    janus_rtcp_transport_wide_cc_stats *stat = g_malloc(sizeof(*stat));
    stat->transport_seq_num = seq;
    stat->timestamp = janus_get_monotonic_time();

    // 加入接收列表
    pc->transport_wide_received_seq_nums = 
        g_slist_prepend(pc->transport_wide_received_seq_nums, stat);
}
```

### 2.4 生成 TWCC 反馈包（ice.c:4151-4276）

Janus 定期将收集到的包到达记录组装成 TWCC 反馈发送给对端：

```c
static void janus_ice_outgoing_transport_wide_cc_feedback(
    janus_ice_handle *handle) {

    // 1. 对到达统计信息排序
    transport_wide_received_seq_nums = 
        g_slist_sort(pc->transport_wide_received_seq_nums, 
            janus_rtp_transport_wide_cc_stats_sort);

    // 2. 将原始列表拆分为 400 个一批的批次
    //    检查丢失的 seq → 填入 timestamp=0
    //    存在的 seq → 填入记录的到达 timestamp

    // 3. 为每批生成一个 TWCC RTCP 数据包
    janus_rtcp_transport_wide_cc_feedback(buf, bufsize,
        ssrc, media, feedback_packet_count, batch_queue);

    // 4. 通过 janus_ice_relay_rtcp 发送
    janus_ice_relay_rtcp_internal(handle, ...);
}
```

**为什么是 400 个一批？** 一个 TWCC 反馈包的大小有限，400 个包的到达状态大约是 50-100 字节，在 MTU 限制内。

### 2.5 反馈周期配置（ice.c:598-611）

```c
#define DEFAULT_TWCC_PERIOD  200  // 默认 200ms

// 如果是 1000ms，则和 RTCP 定时器合并
// 否则使用独立的定时器
```

TWCC 反馈周期默认 **200ms**。如果设置 1000ms，则会和常规的 RTCP 1s 定时器合并发送。

### 2.6 解析 TWCC 反馈（rtcp.c:238-340）

```c
static void janus_rtcp_incoming_transport_cc(
    janus_rtcp_context *ctx, janus_rtcp_fb *twcc, int total) {

    // 1. 解析头部
    uint16_t base_seq = ntohs(*(uint16_t *)data);
    uint16_t status_count = ntohs(*(uint16_t *)(data+2));
    uint32_t reference = ntohl(*(uint32_t *)(data+4)) >> 8;

    // 2. 遍历每个 packet chunk
    while(psc > 0 && total > 1) {
        if(chunk_type == 0) {
            // Run-Length: 状态重复 length 次
        } else {
            // Status Vector: 14 个包状态 * 1bit
            // 或 7 个包状态 * 2bit
        }
    }

    // 3. 解析 recv delta
    // smalldelta: 1 字节，单位 250μs
    // largeornegativedelta: 2 字节

    /* TODO Update the context with the feedback we got */
}
```

---

## 三、Janus REMB 处理策略

### 3.1 ICE 核心层（ice.c:3158-3160）

```c
// 从收到的 RTCP 中解析 REMB
uint32_t bitrate = janus_rtcp_get_remb(buf, len);
if(bitrate > 0) {
    pc->remb_bitrate = bitrate;   // 存储最新 REMB
}
```

**核心层只存储最新的 REMB 值，不做任何决策。**

### 3.2 VideoRoom 插件的 REMB 策略（janus_videoroom.c:8931-8958）

```
VideoRoom 向发布者发送 REMB 的策略：

1. 启动渐变期（remb_startup = 4 步）
   每收到一个 RTP 包，发送 REMB = bitrate / remb_startup
   然后 remb_startup--
   
   目标比特率 = 4 Mbps
   第 1 个 RTP 包后 → REMB: 1 Mbps
   第 2 个 RTP 包后 → REMB: 1.33 Mbps（4/3）
   第 3 个 RTP 包后 → REMB: 2 Mbps（4/2）
   第 4 个 RTP 包后 → REMB: 4 Mbps（4/1）

   为什么？→ 避免启动时瞬时全速输出，渐进恢复到让客户端
   
2. 稳定期（每 5 秒一次）
   如果自上次 REMB 发送过去了 5 秒：
   → 再次发送 REMB = publisher->bitrate
   → 更新 remb_latest = 当前时间
```

**生产者 REMB 发送代码**：

```c
/* janus_videoroom.c:8931 */
if(session->media_rid[0] == NULL) {
    uint32_t bitrate = publisher->bitrate;
    if(bitrate == 0) {
        /* 无限制 */
    } else if(publisher->remb_latest == 0 && publisher->remb_startup > 0) {
        /* 启动阶段：渐进发送 */
        bitrate = bitrate / publisher->remb_startup;
        publisher->remb_startup--;
    } else if(janus_get_monotonic_time() - publisher->remb_latest < G_USEC_PER_SEC * 5) {
        /* 5 秒内已发送过，跳过 */
        return;
    }
    publisher->remb_latest = janus_get_monotonic_time();
    gateway->send_remb(session->handle, bitrate);
}
```

### 3.3 VideoRoom 忽略订阅者的 REMB

```c
/* janus_videoroom.c:9043-9046 — 收到订阅者 REMB */
uint32_t bitrate = janus_rtcp_get_remb(buf, len);
if(bitrate > 0) {
    /* FIXME 我们收到了订阅者的 REMB，应该做点什么吗？ */
}
```

**这是被忽略的**。订阅者的带宽反馈不会影响 VideoRoom 的转发策略。

### 3.4 Streaming 插件（唯一真正使用 REMB 的插件）

```c
/* janus_streaming.c:5946-5951 — 跟踪所有订阅者的最低 REMB */
uint32_t remb = janus_rtcp_get_remb(buf, len);
if(remb > 0 && remb < source->lowest_bitrate) {
    source->lowest_bitrate = remb;   // 记录最低值
}

/* janus_streaming.c:9925-9930 — 每 1 秒发送 REMB 给源 */
if(source->lowest_bitrate > 0 && 
    janus_get_monotonic_time() - source->remb_latest >= G_USEC_PER_SEC) {
    janus_streaming_rtcp_remb_send(source, source->lowest_bitrate);
    source->lowest_bitrate = 0;   // 重置
    source->remb_latest = janus_get_monotonic_time();
}
```

**Streaming 插件的策略**：始终向源发送所有订阅者中**最低**的 REMB 值。

```
源 = 直播发送方

订阅者 A: REMB=5Mbps  (低端手机)        Streaming 插件
订阅者 B: REMB=10Mbps (桌面)     →   向源发送 REMB=5Mbps
                                      (取最低值，保证最差订阅者不卡)
```

### 3.5 EchoTest 插件（固定码率覆盖）

```c
/* janus_echotest.c:720-726 */
uint32_t bitrate = janus_rtcp_get_remb(packet->buffer, packet->length);
if(bitrate > 0) {
    session->peer_bitrate = bitrate;
    gateway->send_remb(handle, 
        session->bitrate ? session->bitrate : 10000000);  // 默认 10Mbps
}
```

**EchoTest 的策略**：不论订阅者报告什么，都回复一个**远高于实际需求**的码率（默认 10Mbps），即"无限速"。

### 3.6 REMB 策略对比

| 插件 | 向发布者发 REMB？ | 频率 | 策略 |
|------|------------------|------|------|
| VideoRoom | ✅ 是 | 启动期每包 + 稳定期 5s | 房间配置比特率 |
| VideoRoom | ❌ 忽略 | N/A | 不处理订阅者的 REMB |
| Streaming | ✅ 是 | 每 1s | 所有订阅者的最低比特率 |
| EchoTest | ✅ 是 | 每收到 REMB | 固定 10Mbps（无限制） |
| AudioBridge | ❌ 无 | N/A | 纯音频，不处理 REMB |

---

## 四、Slowlink 检测机制（ice.c:1975-2019）

Janus 提供了一种简单弱网检测机制，不涉及码率控制，但可以通知应用层。

### 4.1 配置

```c
#define DEFAULT_SLOWLINK_THRESHOLD  2   // 默认连续丢包报告 > 2 次触发
static int slowlink_threshold = DEFAULT_SLOWLINK_THRESHOLD;
```

### 4.2 检测逻辑

```c
/* ice.c:1975-2019 — 每当收到 RTCP RR 时统计丢包 */
if(pc->slow_link_count > slowlink_threshold) {
    /* 恢复：丢包率下降，计数清零 */
    if(pc->slow_link_count > 0)
        pc->slow_link_count--;
} else {
    /* 触发 slowlink 事件 */
    pc->slow_link_count++;
    if(pc->slow_link_count > slowlink_threshold) {
        pc->slow_link_count = 0;
        /* 通知上层：发生 slowlink */
        janus_ice_notify_slow_link(handle, medium->media,
            pc->nack_sent_count, pc->lost_packets_since_last_rr);
    }
}
```

### 4.3 Slowlink 的事件通知

```c
janus_ice_notify_slow_link(handle, mid, nacks_sent, lost_packets);
```

上层（插件或客户端 API）会收到一个 `slowlink` 事件，包含：

```json
{
    "janus": "slowlink",
    "session_id": 123456,
    "sender": 789012,
    "media": "video",
    "nacks-sent": 15,
    "lost-packets": 8
}
```

### 4.4 Slowlink 的用途

```
Slowlink 检测 → 通知上层 → 应用层决策：

  VideoRoom 场景：
    收到 slowlink 事件 → 管理员可以手动降低房间比特率
    或自动触发：向发布者发送更低的 REMB

  自定义场景：
    接到 slowlink → 降级到低分辨率（如 720p → 480p）
    或静音音频（降低带宽消耗）

  Janus 本身不做任何自动反应
  它只是一个通知机制
```

---

## 五、BBR 算法原理与对比

### 5.1 BBR 简介

BBR（Bottleneck Bandwidth and Round-trip propagation time）由 Google 在 2016 年提出（TCP BBR），核心思路是**直接测量瓶颈带宽和 RTT**，而不是通过丢包或延迟梯度推断。

### 5.2 BBR 核心概念

```
BBR 的两个关键测量值：

1. BtlBw（Bottleneck Bandwidth）— 瓶颈带宽
   测量方式：一段时间内的最大分组交付速率
   计算公式：delivery_rate = 分组大小 / ACK 到达间隔
   取 10 轮（round）内的最大值

2. RTprop（Round-Trip propagation time）— 最小 RTT
   测量方式：10 秒内观察到的最小 RTT（排除排队延迟）
   实际等于未拥塞时的纯传播延迟
```

### 5.3 BBR 的状态机

```
          ┌─────────────────────────────┐
          │                             │
          ▼                             │
    ┌──────────┐    ┌──────────┐    ┌────┴──────┐
    │ Startup  │───▶│  Drain   │───▶│ Steady    │
    │ (呈指数  │    │ (排空队  │    │ State     │
    │  增长)   │    │  列)     │    │ ┌──┐ ┌──┐ │
    └──────────┘    └──────────┘    │ │BW│ │RTT│ │
                                    │ │Probe│Probe│
          ┌──────────┐              │ └──┘ └──┘ │
          │  Probe   │◀─────────────└─────┬─────┘
          │  RTT     │                    │
          └──────────┘           (周期性探测)
```

**Startup 阶段**：类似 TCP 慢启动，每轮速率乘以 2（Pacing Gain = 2/ln2 ≈ 2.885），找到瓶颈带宽后退出。

**Drain 阶段**：Startup 结束时队列积压，Pacing Gain < 1 排空队列。

**Steady State（BW Probe）**：Pacing Gain 在 1.25 和 0.75 之间交替，寻找新的瓶颈带宽上限。

**Probe RTT**：10 秒后减低发送速率，测量最小 RTT（更新 RTprop）。

### 5.4 BBR 的 Pacing Gain 策略

```
BBR 通过 Pacing Gain 控制系统行为：

  pacing_rate = BtlBw * pacing_gain

  增益       阶段
  ─────────────────────
  2.885      Startup（指数增长）
  1.0        Drain（排空阶段）
  1.25       BW Probe 上升（探测更多带宽）
  0.75       BW Probe 下降（排空队列）
  1.0        Steady 稳定期
  1.0        然后 RTT Probe（维持速率）
  0.9        然后 RTT Probe（降低队列）
  1.0        然后恢复

  典型的一段 BW Probe 周期（约 8 rounds）：
  1.25, 1.25, 1.25, 0.75, 1.0, 1.0, 1.0, 1.0
  → 增长 25%，探测到队列增长后降回 75% 排空
  → 净增长 + (1.25×0.75 - 1) ≈ 没有净增长但更新了 BtlBw
```

### 5.5 BBR vs GCC 对比

```
┌──────────────────────────────────────────────────────────────────────┐
│               BBR（TCP BBR/WebRTC BBR）                              │
│  ┌────────────────────┐    ┌─────────────────────┐                   │
│  │ 测量：BtlBw (带宽)  │    │ 测量：RTprop (RTT)   │                   │
│  │ 方法：最大分组交付率 │    │ 方法：10s 内最小 RTT │                   │
│  └────────┬───────────┘    └──────────┬──────────┘                   │
│           │                           │                              │
│           └──────────┬────────────────┘                              │
│                      ▼                                               │
│            pacing_rate = BtlBw * pacing_gain                          │
│                                                                      │
│  不依赖丢包、不依赖延迟梯度                                             │
│  直接测量容量，适合大带宽长距离链路                                      │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│            GCC（WebRTC GCC）                                         │
│  ┌────────────────────┐    ┌─────────────────────┐                   │
│  │ 测量：延迟梯度趋势   │    │ 测量：丢包率          │                   │
│  │ 方法：Trendline/KF │    │ 方法：RR fraction     │                   │
│  └────────┬───────────┘    └──────────┬──────────┘                   │
│           │                           │                              │
│           ▼                           ▼                              │
│  基于延迟控制器(快)       基于丢包控制器(慢)                          │
│       │                        │                                     │
│       └──────────┬─────────────┘                                     │
│                  ▼                                                   │
│         final_rate = min(A_delay, A_loss)                            │
│                                                                      │
│  依赖延迟梯度作为早期信号                                              │
│  丢包作为兜底                                                         │
└──────────────────────────────────────────────────────────────────────┘
```

| 维度 | GCC | BBR |
|------|-----|-----|
| **测量基础** | 延迟梯度 + 丢包率 | 最大交付率 + 最小 RTT |
| **拥塞信号** | 延迟增长（提前） | 带宽饱和（实际） |
| **控制方式** | AIMD | Pacing Gain |
| **对手的友好性** | TCP 友好 | 对 CUBIC 不太友好 |
| **适用场景** | WebRTC 实时通信 | TCP 长流/CDN |
| **响应速度** | 快（ms 级检测延迟增长） | 中等（需几 RTT 测量带宽） |
| **RTT 敏感度** | 高 RTT 时加性加慢 | RTT 影响较小 |
| **丢包容忍性** | 低丢包（<2%）正常 | 高丢包（>5%）仍有效 |
| **实现复杂度** | 高（卡尔曼滤波/Trendline） | 中等（速率测量） |
| **WebRTC 应用** | 主流（WebRTC 内置） | 实验性（WebRTC BBR draft） |

### 5.6 实时通信领域为什么选择 GCC 而非 BBR？

```
1. 延迟敏感
   GCC 的延迟梯度可以在丢包发生前 100ms 就检测到拥塞信号
   BBR 依赖带宽测量，需要几个 RTT 才能确认

2. 带宽波动大
   视频码率随场景变化剧烈（静态画面 ↔ 激烈运动）
   BBR 的 Startup 阶段容易误判瓶颈带宽

3. 与 REMB 配合好
   GCC 输出目标码率 → 编码器按码率编码
   BBR 输出 pacing_rate → 用于控制包发送节奏
   WebRTC 需要"码率控制"而非"包发送速率控制"

4. 生态成熟
   主流浏览器都实现了 GCC
   WebRTC BBR 还是草案阶段
```

### 5.7 GCC 在实际系统中的局限性

```
1. 延迟梯度误判
   WiFi 切换 → 延迟突然增加 → GCC 误判为拥塞 → 错误降码率

2. 编码器码率波动
   编码器输出是帧级别的，不是平滑的比特流
   包间间隔波动 → 延迟梯度计算噪声大

3. 对端时钟不精确
   GCC 假设发送端时间戳和接收端时间戳在同一时间轴
   实际系统中时钟漂移可能导致误判

4. 缓存陷阱（Bufferbloat）
   大缓冲区延迟会掩盖丢包
   GCC 的延迟检测可能反应不够及时
```

---

## 六、拥塞控制综合决策框架

### 6.1 RTC 系统层面的拥塞控制分层

```
应用层（插件/房间配置）
  ├─ VideoRoom bitrate = 2Mbps         ← 人工配置的码率上限
  ├─ Streaming lowest_bitrate tracking ← 自动跟踪最差订阅者
  └─ admin API set bitrate             ← 运行时调整

信令层（SDP 限制）
  ├─ b=AS:2000 (Chrome)                ← Session Bandwidth
  └─ b=TIAS:2000000 (Firefox)          ← Transport Independent

传输层（浏览器 GCC）
  ├─ Delay-based Controller (Trendline)
  ├─ Loss-based Controller (fraction_lost)
  └─ REMB → Janus → REMB(可能 cap)
                                            
媒体层（编码器配置）
  ├─ target_bitrate = min(REMB, room_bitrate)
  └─ 编码器按 target_bitrate 输出

发送节奏
  └─ Pacing: 将码率均匀分配到包间隔
     → 避免突发发送导致的短期拥塞
```

### 6.2 Janus 缺少的拥塞控制环节

```
                 现有功能              缺失功能
                 ─────────────────────────────────────────
  发送节奏        ❌ 无 pacer          pacer 可能需要

  入站码率控制    ❌ 无                接收端码率反馈 → GCC
  出站码率控制    ❌ 无                发送端码率调整
  
  延迟梯度计算    ❌ TODO              已解析 TWCC 但丢弃
  带宽估计        ❌ 无                从 TWCC 计算带宽

  Simulcast 切换   ✅ 基于 REMB         基于实际带宽的自动层选择
                 （固定阈值）               （实时带宽估计）
```

### 6.3 如果需要为 Janus 添加拥塞控制

```c
/* 理论上的实现路径 */
// 1. 在 janus_rtcp_incoming_transport_cc() 中实现 Trendline 滤波器
struct trendline {
    double window[20];        // 延迟梯度滑动窗口
    double slope;              // 线性回归斜率
    double threshold;          // 自适应阈值 gamma
    enum state;                // Overuse/Underuse/Normal
};

// 2. 实现 AIMD 速率控制器
struct rate_controller {
    uint32_t rate_delay;       // 基于延迟的码率估计 A_s
    uint32_t rate_loss;        // 基于丢包的码率估计 A_r
    uint32_t final_rate;       // min(A_s, A_r)
    int overuse_counter;       // 过载计数器
};

// 3. 将估计的码率传递给插件
janus_ice_notify_bandwidth_estimation(handle, estimated_bitrate);

// 4. 插件（如 VideoRoom）据此调整 REMB 发送给发布者
gateway->send_remb(handle, estimated_bitrate);
```

---

## 七、W13-14 综合总结

### 7.1 拥塞控制技术栈

```
        ┌───────────────────────────────────────────────┐
        │              拥塞控制技术栈                      │
        ├───────────────────────────────────────────────┤
        │                                               │
        │  ~~~~ 应用层（人工干预） ~~~~~~~~~~~~~~~~~~~    │
        │  视频模式切换、码率手动设定、SDP b=AS:          │
        │                                               │
        │  ──── 传输层（自动算法） ───────────────────    │
        │  GCC(AIMD)   BBR(模型)   SCReAM(SBD检测)      │
        │                                               │
        │  ──── 反馈信号 ────────────────────────────    │
        │  TWCC(到达时间)  REMB(接收端码率)              │
        │  RR fraction_lost(丢包率)  NACK(丢包信息)     │
        │                                               │
        │  ──── 恢复措施 ────────────────────────────    │
        │  NACK 重传    FEC 纠错    Simulcast 层切换     │
        │  PLI 关键帧请求    SVC 分层丢弃                │
        │                                               │
        └───────────────────────────────────────────────┘
```

### 7.2 Janus 在拥塞控制中的角色

```
作为 SFU，Janus 的拥塞控制策略是"透传+策略性限速"

透传：
  TWCC RTP 扩展写入 ✅       TWCC 反馈生成 ✅
  TWCC 反馈解析 ✅(但丢弃)    NACK 重传 ✅
  REMB 转发/生成 ✅           SR/RR SSRC 修复 ✅

策略性限速：
  VideoRoom 启动期 REMB 渐变 ✅
  Streaming 最低 REMB 跟踪 ✅
  SDP b=AS: 限制 ✅

缺失：
  Bandwidth estimation ❌
  Delay-gradient AIMD ❌
  Dynamic simulcast ❌
```

### 7.3 关键函数速查

| 函数 | 文件:行 | 作用 |
|------|---------|------|
| `janus_rtcp_incoming_transport_cc()` | rtcp.c:238-340 | 解析 TWCC 反馈包（TODO 开头） |
| `janus_ice_outgoing_transport_wide_cc_feedback()` | ice.c:4151-4276 | 生成 TWCC 反馈并发送 |
| `janus_rtcp_get_remb()` | rtcp.c:1328 | 解析 REMB 消息获取码率值 |
| `janus_rtcp_cap_remb()` | rtcp.c:1372 | 限制 REMB 码率上限 |
| `janus_rtcp_remb()` / `janus_rtcp_remb_ssrcs()` | rtcp.c:1464 | 生成 REMB 消息 |
| `janus_ice_send_remb()` | ice.c:5198 | ICE 层发送 REMB |
| `janus_plugin_send_remb()` | janus.c:4288 | 插件 API 发送 REMB |
| 向发布者发送 REMB | videoroom.c:8931 | VideoRoom 启动期/周期性码率限制 |
| 订阅者 REMB 忽略 | videoroom.c:9043 | VideoRoom 忽略订阅者 REMB |
| 最低 REMB 跟踪 | streaming.c:5946 | Streaming 跟踪最差订阅者 |
| slowlink 检测 | ice.c:1975 | 基于丢包的弱网事件通知 |
| transport-seq 写入 | ice.c:3958 | RTP 包写入 transport_wide_cc_seq |

---

## 八、下一步（W15-16）

**目标**：Jitter Buffer 深入

1. 自适应延迟算法
2. 帧排序和帧丢弃策略
3. 音频 3A（AEC/ANS/AGC）原理了解
4. C++ 性能：移动语义/内存池

---

**学习进度**：✅ W3-12 ✅ W13 完成（GCC 算法+Transport-CC+Overuse Detector） ✅ W14 完成（Janus 拥塞控制+BBR 对比）
**当前任务**：进入 W15-16（Jitter Buffer 自适应+音频 3A）
