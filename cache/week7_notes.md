# 第七周学习笔记：SDP 协商

**日期**：2026年5月第5周  
**目标**：理解 SDP 格式、Offer/Answer 模型、Janus 中的 SDP 处理

---

## 一、Janus 中的 SDP 核心结构体

### 1.1 文件分布

| 文件 | 行数 | 作用 |
|------|------|------|
| `sdp-utils.h` | 438 行 | SDP 核心结构体定义（janus_sdp、m-line、attribute） |
| `sdp-utils.c` | 2353 行 | SDP 解析/生成（字符串 ↔ 结构体） |
| `sdp.h` | 105 行 | SDP 处理函数声明 |
| `sdp.c` | 1755 行 | SDP 剥离/合并/处理 |

### 1.2 janus_sdp（`sdp-utils.h:26`）

```c
typedef struct janus_sdp {
    int version;              // v= (版本号)
    char *o_name;             // o= username
    guint64 o_sessid;         // o= session id
    guint64 o_version;        // o= version
    gboolean o_ipv4;          // o= address type
    char *o_addr;             // o= address
    char *s_name;             // s= session name
    guint64 t_start;          // t= start time
    guint64 t_stop;           // t= stop time
    gboolean c_ipv4;          // c= address type
    char *c_addr;             // c= connection address
    GList *attributes;        // 全局 a= 属性列表
    GList *m_lines;           // m= 媒体行列表
    volatile gint destroyed;
    janus_refcount ref;
} janus_sdp;
```

### 1.3 janus_sdp_mline（`sdp-utils.h:131`）

```c
typedef struct janus_sdp_mline {
    int index;                 // 媒体行在 SDP 中的索引
    janus_sdp_mtype type;      // 媒体类型（audio/video/application）
    char *type_str;            // 媒体类型字符串
    guint16 port;              // m= port
    char *proto;               // m= proto（如 RTP/SAVPF）
    GList *fmts;               // 格式列表（字符串）
    GList *ptypes;             // payload type 列表
    gboolean c_ipv4;           // 媒体级 c= address type
    char *c_addr;              // 媒体级 c= address
    char *b_name;              // b= type
    uint32_t b_value;          // b= value
    janus_sdp_mdirection direction;  // 媒体方向（sendrecv/sendonly/recvonly/inactive）
    GList *attributes;         // 媒体级 a= 属性列表
    // ...
} janus_sdp_mline;
```

### 1.4 janus_sdp_attribute（`sdp-utils.h:198`）

```c
typedef struct janus_sdp_attribute {
    char *name;                // 属性名（如 rtpmap、fmtp、fingerprint）
    char *value;               // 属性值
    janus_sdp_mdirection direction;  // 方向（用于 extmap 等）
    // ...
} janus_sdp_attribute;
```

**关键枚举**：
- **`janus_sdp_mtype`**：`JANUS_SDP_AUDIO` / `JANUS_SDP_VIDEO` / `JANUS_SDP_APPLICATION`
- **`janus_sdp_mdirection`**：`JANUS_SDP_SENDRECV` / `JANUS_SDP_SENDONLY` / `JANUS_SDP_RECVONLY` / `JANUS_SDP_INACTIVE`

---

## 二、SDP 处理核心机制

### 2.1 关键函数（sdp.h）

```c
// 预解析 SDP（快速检查 media line 数量和 DTLS role）
janus_sdp *janus_sdp_preparse(void *handle, const char *jsep_sdp, ...);

// 处理远端 SDP（来自浏览器）
int janus_sdp_process_remote(void *handle, janus_sdp *sdp, gboolean rids_hml, gboolean update);

// 处理本地 SDP（来自插件）
int janus_sdp_process_local(void *handle, janus_sdp *sdp, gboolean update);

// 剥离/匿名化 SDP（移除 ICE/DTLS/transport 信息）
int janus_sdp_anonymize(janus_sdp *sdp);

// 合并 SDP（添加正确的 transport 信息）
int janus_sdp_merge_transport(void *handle, janus_sdp *sdp, gboolean offer);
```

### 2.2 SDP 剥离和合并（核心设计）

这是 Janus SDP 处理的核心设计模式（sdp.h 第 5-13 行的注释）：

```
客户端 SDP（含 ICE/DTLS/transport 信息）
    │
    ▼
janus_sdp_preparse()   -- 预解析（检查格式）
    │
    ▼
janus_sdp_anonymize()  -- 剥离！移除 ICE/DTLS 信息
    │                     （留给插件的是"纯净"的媒体信息）
    ▼
插件收到剥离后的 SDP → 处理媒体协商
    │
    ▼
janus_sdp_merge_transport()  -- 合并！重新添加 ICE/DTLS 信息
    │
    ▼
客户端收到完整 SDP（含 ICE/DTLS/transport 信息）
```

**设计原因**：
- 插件不需要关心 ICE/DTLS 等底层传输细节
- 核心统一管理传输层，插件只关注媒体内容
- 简化插件开发

---

## 三、W7 周一-周二：SDP 解析和生成

### 3.1 关键函数实现位置

```c
// sdp-utils.c 中的核心函数
janus_sdp *janus_sdp_parse(const char *sdp, char *error, size_t errlen);
    // SDP 字符串 → janus_sdp 结构体（解析）
    
char *janus_sdp_write(janus_sdp *sdp);
    // janus_sdp 结构体 → SDP 字符串（生成）

janus_sdp *janus_sdp_new(const char *name, const char *address);
    // 快速创建一个空的 janus_sdp 实例
```

### 3.2 辅助函数

```c
// 创建 m-line
janus_sdp_mline *janus_sdp_mline_create(janus_sdp_mtype type, guint16 port, 
                                         const char *proto, janus_sdp_mdirection direction);

// 查找 m-line
janus_sdp_mline *janus_sdp_mline_find(janus_sdp *sdp, janus_sdp_mtype type);

// 创建 attribute
janus_sdp_attribute *janus_sdp_attribute_create(const char *name, const char *value, ...);

// 将 attribute 添加到 m-line
int janus_sdp_attribute_add_to_mline(janus_sdp_mline *mline, janus_sdp_attribute *attr);

// 查找首选 codec
void janus_sdp_find_preferred_codec(janus_sdp *sdp, janus_sdp_mtype type, int index, const char **codec);

// 移除 payload type
int janus_sdp_remove_payload_type(janus_sdp *sdp, int index, int pt);
```

---

## 四、W7 周三-周四：SDP Offer/Answer 模型

### 4.1 Offer/Answer 流程

```
客户端                                    Janus
  │                                        │
  │-- attach ---------------------------->│
  │<-- attached (handle_id) --------------│
  │                                        │
  │-- message + SDP offer --------------->│
  │                                        │
  │    1. janus_sdp_preparse()            │
  │       → 检查 SDP 格式                  │
  │       → 返回 DTLS role、m-line 数量    │
  │                                        │
  │    2. janus_sdp_process_remote()      │
  │       → 设置 ICE remote credentials    │
  │       → 设置远端 candidates            │
  │       → 开始 ICE 检查                  │
  │                                        │
  │    3. janus_sdp_anonymize()           │
  │       → 移除 ICE/DTLS 信息            │
  │       → 传给插件                      │
  │                                        │
  │    4. plugin->handle_message()        │
  │       → 插件处理媒体的 SDP 信息       │
  │       → 返回剥离后的 SDP answer       │
  │                                        │
  │    5. janus_sdp_merge_transport()     │
  │       → 添加 ICE/DTLS 信息            │
  │       → 生成完整的 SDP answer         │
  │                                        │
  │<-- message + SDP answer --------------│
```

### 4.2 janus_sdp_process_remote 代码分析（sdp.c:146）

**作用**：处理远端（浏览器）发来的 SDP，提取 ICE/DTLS 信息并设置媒体方向。

**处理流程**：

```c
int janus_sdp_process_remote(void *ice_handle, janus_sdp *remote_sdp, gboolean rids_hml, gboolean update) {
    janus_ice_handle *handle = (janus_ice_handle *)ice_handle;
    
    // 1. 解析全局属性
    //    提取：fingerprint、ice-ufrag、ice-pwd
    while(temp) {
        janus_sdp_attribute *a = (janus_sdp_attribute *)temp->data;
        if(!strcasecmp(a->name, "fingerprint")) {
            // 保存远端 DTLS 证书指纹（sha-256 / sha-1）
            rfingerprint = g_strdup(a->value + strlen("sha-256 "));
        } else if(!strcasecmp(a->name, "ice-ufrag")) {
            ruser = g_strdup(a->value);  // ICE 用户名
        } else if(!strcasecmp(a->name, "ice-pwd")) {
            rpass = g_strdup(a->value);  // ICE 密码
        }
    }
    
    // 2. 遍历每个 m-line
    while(temp) {
        janus_sdp_mline *m = (janus_sdp_mline *)temp->data;
        
        // 根据 SDP direction 设置媒体方向
        switch(m->direction) {
            case JANUS_SDP_INACTIVE:
                medium->send = FALSE; medium->recv = FALSE;  break;
            case JANUS_SDP_SENDONLY:
                medium->send = FALSE; medium->recv = TRUE;   // 对端 sendonly = 我们 recv
                break;
            case JANUS_SDP_RECVONLY:
                medium->send = TRUE; medium->recv = FALSE;   // 对端 recvonly = 我们 send
                break;
            case JANUS_SDP_SENDRECV:
            default:
                medium->send = TRUE; medium->recv = TRUE;    // 双向
                break;
        }
        
        // 记录 payload types（codec 列表）
        medium->payload_types = g_list_copy(m->ptypes);
    }
}
```

### 4.3 janus_sdp_anonymize 剥离机制（sdp.c:1315）

**作用**：移除 ICE/DTLS/transport 信息，只留媒体相关信息给插件。

**被移除的属性**：
- **全局**：`ice-ufrag`、`ice-pwd`、`ice-options`、`fingerprint`、`group`、`msid-semantic`
- **m-line 级**：`ice-ufrag`、`ice-pwd`、`fingerprint`、`candidate`、`rtcp-mux`、`setup`、`crypto`、`rid`、`simulcast`、`end-of-candidates` 等

**被匿名化的地址**：
```c
// o= address → 1.1.1.1
g_free(anon->o_addr);
anon->o_addr = g_strdup("1.1.1.1");

// c= address → 1.1.1.1
g_free(m->c_addr);
m->c_addr = g_strdup("1.1.1.1");

// m= port → 9（或 0 禁用）
m->port = 9;
```

**保留给插件的信息**：codec（rtpmap/fmtp）、ssrc、msid、mid、extmap 等纯媒体相关属性。

---

### 4.4 Unified Plan vs Plan B

| 特性 | Plan B（旧） | Unified Plan（新） |
|------|-------------|-------------------|
| **多流** | 每个 m-line 一个流 | 一个 m-line 多个 track（用 a=msid 标识） |
| **SSRC 处理** | 多个 SSRC 在同一个 m-line | 每个 track 有自己的 SSRC |
| **标准** | Google 私有 | RFC 8843 |
| **Chrome 默认** | 旧版 | 新版 |
| **Janus 支持** | 兼容 | 默认 |

**在 Janus 中的处理**：
- `janus_sdp_process_remote` 中的 `rids_hml` 参数用于处理 Simulcast 的 rid 顺序
- Janus 在 SDP 处理中会检查并适配两种格式

---

## 五、W7 周五-周末：画 SDP 流程图 + 综合整理

### 5.1 SDP 处理流程时序图

```
Client                    Janus Core                  ICE/DTLS                  Plugin
  │                          │                          │                        │
  │-- SDP Offer ----------->│                          │                        │
  │                          │-- janus_sdp_preparse-->│                        │
  │                          │                          │                        │
  │                          │-- janus_sdp_process_remote -->│                   │
  │                          │                          │-- 设置 remote credentials │
  │                          │                          │-- 添加 candidates     │
  │                          │                          │                        │
  │                          │-- janus_sdp_anonymize   │                        │
  │                          │                          │                        │
  │                          │-- (剥离后 SDP) -------->|                        │
  │                          │                          │-- handle_message     │
  │                          │                          │   + (剥离后的 SDP)     │
  │                          │                          │                        │
  │                          │                          │   ← push_event       │
  │                          │                          │   + (剥离后的 answer) │
  │                          │                          │                        │
  │                          │-- janus_sdp_merge_transport                     │
  │                          │   → 添加 ICE candidates                         │
  │                          │   → 添加 DTLS fingerprint                       │
  │                          │                          │                        │
  │<-- SDP Answer ----------│                          │                        │
```

### 5.2 SDP 关键属性速查

| SDP 属性 | 含义 | WebRTC 必需 |
|----------|------|-------------|
| `a=rtpmap:96 opus/48000/2` | codec 映射 | 是 |
| `a=fmtp:96 minptime=10` | codec 参数 | 否 |
| `a=sendrecv` / `a=sendonly` / `a=recvonly` | 媒体方向 | 是 |
| `a=fingerprint:sha-256 XX:XX:...` | DTLS 证书指纹 | 是 |
| `a=ice-ufrag` / `a=ice-pwd` | ICE 凭证 | 是 |
| `a=candidate:...` | ICE 候选地址 | 是 |
| `a=ssrc:...` | RTP 同步源 | 是（Plan B） |
| `a=msid:...` | 媒体流标识 | 是（Unified Plan） |
| `a=mid:0` | 媒体行标识 | 是 |
| `a=extmap:...` | RTP 扩展头 | 否 |
| `a=group:BUNDLE audio video` | BUNDLE 分组 | 是 |
| `a=rtcp-mux` | RTCP 多路复用 | 是 |
| `a=rid:...` | Simulcast RID | 否 |

---

## 六、下一步学习（W8）

**目标**：SDP 在 Janus 中的处理深入

**具体任务**：
1. 追踪 SDP 从收到到返回的完整代码路径（janus.c → sdp.c → ice.c）
2. 理解 `janus_sdp_anonymize` 和 `janus_sdp_merge_transport` 的具体实现
3. Unified Plan vs Plan B 在 Janus 中的兼容性处理代码
4. 对比 SIP 网关的 SDP 处理

---

**学习进度**：✅ W3-6 完成（主流程+插件架构+ICE+DTLS/SRTP） ✅ W7 完成（SDP 结构体+解析/生成+Offer/Answer 模型）
**W8 已开始**：SDP 处理深入（代码路径追踪、process_local、merge、Unified Plan 兼容）→ 见 `week8_notes.md`
