# 第十三周学习笔记：拥塞控制（上）— GCC 算法原理

**日期**：2026年6月第5周  
**目标**：理解 Google Congestion Control（GCC）算法的双控制器架构、Transport-CC 反馈机制、overuse detector 的工作原理

---

## 一、拥塞控制概述

### 1.1 为什么需要拥塞控制？

RTP 通过 UDP 传输，没有 TCP 的 AIMD（加性增乘性减）拥塞控制。如果不加控制：

```
发送方以 10Mbps 发送 → 网络瓶颈 2Mbps → 路由器开始丢包
  → 丢包率飙升 → 重传更多（NACK）→ 更多流量 → 更严重拥塞
  → 最终：质量崩溃（视频卡死、音频断裂）
```

拥塞控制的目标：**动态调整发送码率，在不过载网络的前提下最大化质量。**

### 1.2 WebRTC 拥塞控制演进

| 阶段 | 算法 | 基础 | 时间 |
|------|------|------|------|
| 早期 | REMB + GCC v1 | 丢包率 + 单向延迟梯度 | ~2013 |
| 现在 | TWCC + GCC v2 | Transport-CC 精确反馈 | ~2017+ |
| 新趋势 | SBD + SCReAM | 共享瓶颈检测 | 实验性 |

**当前 WebRTC 主流是 GCC v2：基于 Transport-CC 的双控制器架构。**

---

## 二、GCC 总体架构

### 2.1 双控制器设计

```
                   接收端收到的 RTP 包
                          │
                          ▼
                 ┌─────────────────┐
                 │  Arrival-Time   │          基于延迟的控制器
                 │    Filter       │        (Delay-based Controller)
                 │  (Kalman Filter │
                 │   / Trendline)  │
                 └────────┬────────┘
                          │ overuse / underuse / normal 状态
                          ▼
                 ┌─────────────────┐
                 │    Overuse      │
                 │    Detector     │
                 └────────┬────────┘
                          │ 状态变化
                          ▼
                 ┌─────────────────┐
                 │    Rate Control │────────── A_s（基于延迟的码率）
                 │  (AIMD Rate     │
                 │   Controller)   │
                 └────────┬────────┘
                          │
          ┌───────────────┴───────────────┐
          │                               │
          ▼                               ▼
  ┌─────────────────┐           ┌─────────────────┐
  │  Loss-based     │           │  REMB Receiver  │
  │  Controller     │           │  Estimated BW   │
  │  (丢包率 > 2%   │           │  = max(A_s, A_r)│
  │   → 降码率)     │           │  (或 min)       │
  └────────┬────────┘           └────────┬────────┘
           │                             │
           └──────────────┬──────────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │  最终目标码率 A  │
                 │  = min(A_received│
                 │  , A_loss)       │
                 └─────────────────┘
```

### 2.2 两个控制器分工

| 控制器 | 输入 | 检测目标 | 响应速度 | 作用 |
|--------|------|---------|---------|------|
| **基于延迟** | 包到达间隔的延迟梯度 | 网络排队延迟增加（即将拥塞的信号） | 快（几百 ms） | 在丢包发生前就降码率 |
| **基于丢包** | RTCP RR 中的丢包率 | 已发生的丢包 | 慢（几秒） | 兜底保护，确认拥塞时大幅降码率 |

**核心设计思想**：延迟是**前瞻指标**，丢包是**确认指标**。延迟梯度上升意味着队列在增长，拥塞即将发生；丢包意味着已经拥塞。

---

## 三、基于延迟的控制器

### 3.1 关键概念：单向延迟梯度（One-way Delay Gradient）

GCC 不测量绝对延迟（需要时钟同步），而是测量**相对延迟变化**：

```
包 i 的到达时间差  = t_i - t_(i-1)     （接收端的到达时间间隔）
包 i 的发送时间差  = T_i - T_(i-1)     （发送端的时间戳间隔）

单向延迟变化 d(i) = (t_i - t_(i-1)) - (T_i - T_(i-1))
                  = 实际到达间隔 - 预期到达间隔

如果 d(i) > 0 → 网络延迟增加 → 队列在增长（拥塞信号）
如果 d(i) < 0 → 网络延迟减少 → 队列在排空（未拥塞）
```

**实际传输中的示意**：

```
瓶颈带宽 = 2 Mbps，发送方速度变化：

阶段 1：发送码率 < 2 Mbps → 无排队
  包的时间间隔无变化，d(i) ≈ 0

阶段 2：发送码率 > 2 Mbps → 队列开始增长
  接收端看到间隔逐渐拉长，d(i) 持续 > 0
  
阶段 3：发送码率降回 < 2 Mbps → 队列排空
  接收端看到间隔缩短，d(i) 持续 < 0
```

### 3.2 到达时间滤波器（Arrival-Time Filter）

WebRTC 中有两种实现：

**GCC v1 — Kalman Filter（RFC 原文）**：

```
状态变量：θ_i = [1 / C_i, m_i]^T
  C_i = 链路容量估计
  m_i = 噪声项（排队延迟变化）

观测值：d(i) = 到达时间差 - 发送时间差

卡尔曼滤波器：
  预测：θ_hat(i) = θ_hat(i-1)    （状态不变假设）
  更新：θ_hat(i) = θ_hat(i-1) + K(i) * (d(i) - H * θ_hat(i-1))
  其中 K(i) 是卡尔曼增益

输出：m_i = 排队延迟变化估计
```

**GCC v2 — Trendline Filter（Chrome 当前实现）**：

```
简化思路：对延迟梯度做滑动窗口线性回归

1. 累积延迟：
   acc_delay(i) = Σ d(k), k = i-window_len+1 ... i

2. 对 [index, acc_delay] 做最小二乘线性拟合：
   斜率 = trend = Σ((t - t_mean) * (d - d_mean)) / Σ(t - t_mean)²

   trend > 0 → 延迟在增长 → overuse 趋势
   trend < 0 → 延迟在减小 → underuse 趋势
```

Trendline 比 Kalman Filter 计算量更小，实际效果接近。

### 3.3 Overuse Detector

```
输入：m(i)（排队延迟估计）或 trend（趋势斜率）
                                      ┌──────────────────────┐
m(i) ──→ 阈值比较 ──→ 状态机 ──→ overuse/underuse/normal
                                      └──────────────────────┘
```

**状态机（RFC 原文）**：

```
          ┌─────────────────────────────────────────────────┐
          │                                                 │
          │      m(i) > gamma(i) 且 持续一段时间              │
          │     ──────────────────────────────────→  Overuse │
          │                                                 │
          │      m(i) < -gamma(i) 且 持续一段时间             │
          │     ──────────────────────────────────→ Underuse │
          │                                                 │
          │      |m(i)| <= gamma(i)                          │
          │     ──────────────────────────────────→  Normal  │
          │                                                 │
          └─────────────────────────────────────────────────┘
```

**自适应阈值 gamma(i)**：

```
gamma(i) = gamma(i-1) + k_delta * t(i)    当 |m(i)| > gamma(i-1)
gamma(i) = gamma(i-1) - k_delta * t(i)    当 |m(i)| <= gamma(i-1)
gamma(i) 被钳位在 [6ms, 600ms] 范围内
```

gamma 越大越不容易触发 overuse（更稳定但响应慢）；gamma 越小越敏感（响应快但可能误判）。

**初始值**：gamma(0) = 12.5ms

### 3.4 AIMD 速率控制器

当 Overuse Detector 输出状态变化后，速率控制器按 AIMD 调整码率：

```
状态变化 → 操作
──────────────────────────────────────────
Overuse  → A_s(i) = A_s(i-1) * (1 - 0.5*(overuse_counter - 1))
           overuse_counter = overuse_counter + 1
           加性加 → 切换为乘性减

Underuse → A_s(i) = target_rate + 1.5 * s_(i-1)  (目标码率略高于接收码率)
           overuse_counter = 0

Normal   → A_s(i) = A_s(i-1) + 1.5 * s_(i-1) / RTT²
           乘性减 → 切换为加性加
           overuse_counter = 0
```

**AIMD 控制律可视化**：

```
码率
  ↑
  │  _______
  │ /  加性加(正常)  ↘ 乘性减(过载)  _______ 加性加(正常)
  │/                                   /
  │                                   /
  │                              ↘ 乘性减
  │
  └────────────────────────────────────────────────────→ 时间
      ↑           ↑                  ↑
    正常    检测到 overuse     正常
```

### 3.5 加性加 / 乘性减 参数为什么这样设定？

```
加性加速率：1.5 * s_(i-1) / RTT²
  → RTT 越大，加性加越慢（保守）
  → RTT 越小，加性加越快（激进）

乘性减比例：0.5（-50%）
  → 一旦检测到过载，立即大幅降码率
  → 快速缓解拥塞
```

这是符合 TCP 友好（TCP-friendly）原则的设计。

---

## 四、基于丢包的控制器

### 4.1 丢包率计算

从 RTCP RR 的 Report Block 中获取：

```c
// fraction_lost 是 8 位定点数（0-255）
uint32_t fraction = (ntohl(rb->flcnpl) >> 24) & 0xFF;
double loss_rate = fraction / 255.0 * 100;  // 转换为百分比
```

### 4.2 丢包阈值决策

```
接收到的丢包率（fraction_lost）对码率的影响：

  loss_rate > 10%  → A_r = A_r * (1 - 0.5 * loss_rate)  激进降码率
  2% < loss_rate ≤ 10% → A_r = A_r * (1 - 0.5*(loss_rate - 0.02))
  loss_rate ≤ 2%  → A_r = A_r * 1.05 (稍微增加) 或维持
```

**2% 是经验阈值**：低于 2% 的丢包对视频质量影响有限，网络可能只是偶尔抖动，不必降码率。

### 4.3 丢包控制器的定位

```
基于延迟的控制器（快速）：
  ──→ 在队列刚建立但还未丢包时已经降码率
    
基于丢包的控制器（慢速）：
  ──→ 兜底机制，防止延迟控制器失效或误判
    
两者之间：
  A_r 是延迟控制器提供的码率上限
  final_rate = min(A_r, A_loss)
```

---

## 五、Transport-CC 反馈机制

### 5.1 为什么需要 Transport-CC？

GCC v1 使用 REMB + 基于 RTP 时间戳的延迟估计。这个方案有两个问题：

```
问题 1：RTP 时间戳不单调
  → Simulcast 切换时 SSRC 变化，RTP 时间戳跳变
  → 延迟估计完全混乱

问题 2：REMB 只能表示"期望码率"
  → 需要接收端自己估计带宽
  → 发送端看到的 REMB 是处理过后的值

Transport-CC 方案：
  1. 引入独立、单调递增的 transport-wide 序列号
  2. 报告每个包的到达时间（精确到 250μs 单位）
  3. 发送端自行计算延迟梯度，不需要依赖接收端估计
```

### 5.2 Transport-CC 扩展（RTP 头部）

```
RTP 包：
┌───────────────────────────────────┐
│  RTP Header                       │
│  ├─ seq_number (媒体层)           │  ← 可能有跳变
│  ├─ SSRC                          │
│  ├─ timestamp                     │
│  └─ Extensions:                   │
│       └─ a=extmap:5 http://...    │
│           transport-wide-cc-01    │
│           └─ transport_seq (2B)   │  ← 单调递增，不受 SSRC 切换影响
└───────────────────────────────────┘
```

**关键属性**：transport_seq 是**所有 SSRC 共享**的计数器。

```
audio SSRC=1000: transport_seq = 1, 2, 3, ...
video SSRC=2000: transport_seq = 4, 5, 6, ...
audio SSRC=1000: transport_seq = 7, 8, 9, ...
→ 接收端只需要一个全局的到达时间表即可
→ 不需要区分 SSRC
```

### 5.3 TWCC 反馈包格式（RTPFB, FMT=15）

```
RTCP Header (8 bytes)
  version = 2, type = 205, fmt = 15
  length = ...

FCI:
  base_seq        (2 bytes)  本次反馈的起始 transport seq
  status_count    (2 bytes)  报告的包数量
  reference_time  (3 bytes)  参考时间（64ms 为单位）
  fb_pkt_count    (1 byte)   反馈包计数

  packet chunks (变长):
    ┌── chunk 类型 ────┐
    │ t=0: Run-Length  │  重复的状态编码, 适合长连丢包
    │   |status(1bit)  │
    │   |run_len(13bit)│
    │ t=1: Status      │  状态向量, 适合随机丢包
    │   |ss=0: 每包1bit│
    │   |ss=1: 每包2bit│
    └──────────────────┘

  recv deltas (变长):
    smalldelta (1 byte): 到达延迟增量，单位 250μs，范围 0~63.75ms
    largeornegativedelta (2 bytes): 更大延迟或负值
```

**Run-Length 编码示例**：

```
连续 17 个包状态为 "not received"（丢包）：
  Run-Length Chunk:
    t=0 (1bit: run-length type)
    symbol=00 (2bits: 00=not received)
    run_length=16 (13bits: 表示 17 个[差值索引])

Status Vector Chunk（每包 1 位）：
  以 14 个包为一组，每个包用 1 bit 表示
  0=not received, 1=small delta
```

### 5.4 GCC v2 利用 TWCC 的完整流程

```
发送端：
  每个 RTP 输出时写入单调递增的 transport_seq
  → Janus: transport_wide_cc_out_seq_num++

接收端：
  记录每个 transport_seq 的到达时间
  定期生成 TWCC 反馈包
  → base_seq: 最先到达的包
  → 每个包的状态 + 到达延迟（相对于 reference_time）

发送端收到 TWCC 反馈：
  1. 将到达时间转换为单向延迟梯度
     d(i) = (t_i - t_(i-1)) - (T_i - T_(i-1))   ← 用 transport_seq 替代 RTP ts
     
  2. 输入 Trendline 滤波器计算斜率

  3. 斜率 > 阈值 → overuse → 降码率
```

### 5.5 TWCC vs RTP 时间戳延迟估计

```
场景：Simulcast 从高清流切换到低清流
  SSRC 变化，RTP timestamp 从 90000 跳到 60000
  → RTP 时间戳延迟估计完全失效（大的负跳变）

TWCC transport_seq: 1, 2, 3, 4, 5, 6, ...
  → 完全不受影响，单调递增
  → 延迟梯度计算准确
```

---

## 六、GCC 参数汇总

| 参数 | 默认值 | 说明 |
|------|--------|------|
| gamma(0) | 12.5ms | Overuse 阈值初始值 |
| gamma 范围 | [6ms, 600ms] | 自适应阈值钳位范围 |
| k_delta | 0.01 | 阈值自适应速率 |
| overuse 加性加 | 1.5*s/RTT² | 正常状态码率增长速率 |
| overuse 乘性减 | ×0.5 | 过载状态降码率比例 |
| 丢包阈值 | 2% | 丢包法启动降码率的阈值 |
| Trendline 窗口 | 20 个包 | 滑动窗口大小 |
| TWCC 反馈周期 | 200ms | 默认每 200ms 发送一次反馈 |
| TWCC 精度 | 250μs | recv_delta 单位 |

---

## 七、关键代码路径总览

| 组件 | 作用 | Janus 状态 |
|------|------|-----------|
| transport-seq 写入 | 在 RTP 扩展中写入单调递增 seq | ✅ 实现（ice.c:3958-3968） |
| 到达时间记录 | 记录每个包的到达时间和 transport_seq | ✅ 实现（ice.c:2751-2777） |
| TWCC 反馈生成 | 生成 RTCP 反馈包发送给发送端 | ✅ 实现（ice.c:4151-4276） |
| TWCC 反馈解析 | 解析 TWCC 反馈数据 | ✅ 实现（rtcp.c:238-340） |
| **延迟梯度计算** | **从到达时间计算延迟变化** | **❌ TODO（rtcp.c:338）** |
| **Trendline/Kalman** | **滤波和斜率估计** | **❌ 未实现** |
| **Overuse Detector** | **状态机检测** | **❌ 未实现** |
| **AIMD 速率控制器** | **根据状态调整发送码率** | **❌ 未实现** |

---

## 八、下一步（W14）

**目标**：Janus 拥塞控制实际实现分析 + BBR 对比

1. Janus 的 TWCC 集成（解析、生成、TODO）
2. Janus 的 REMB 处理策略（VideoRoom/Streaming 插件）
3. slowlink 检测机制
4. Janus 不做 GCC 的架构原因
5. BBR 基本原理对比
6. 拥塞控制综合决策框架

---

**学习进度**：✅ W3-10 ✅ W11-12 ✅ W13 完成（GCC 算法原理+Transport-CC+Overuse Detector）
**当前任务**：进入 W14（Janus 拥塞控制分析 + BBR 对比）
