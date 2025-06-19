# 环境变量配置说明

本项目使用环境变量进行配置管理。请创建 `.env` 文件或在系统中设置以下环境变量：

## 必需的环境变量

### ENCRYPTION_KEY
用于数据加密的密钥。

- **格式**: 32字符的十六进制字符串
- **生成方法**: `python -c "import secrets; print(secrets.token_hex(16))"`
- **示例**: `ENCRYPTION_KEY=a1b2c3d4e5f6789012345678901234567890abcdef`

### KEYWORDS_API_URLS
关键词查询API地址列表，支持多个API并发查询。

- **格式**: JSON数组
- **示例**: `KEYWORDS_API_URLS=["https://api1.example.com/keywords", "https://api2.example.com/keywords"]`

### KEYWORD_METRICS_API_URL
关键词指标批量API的基础地址。系统会自动拼接 `/api/v1/keyword-metrics/batch` 路径。

- **格式**: 基础URL（支持多种格式）
- **自动拼接**: `https://work.seokey.vip/` → `https://work.seokey.vip/api/v1/keyword-metrics/batch`
- **示例**: `KEYWORD_METRICS_API_URL=https://work.seokey.vip/`

### SITEMAP_API_KEY
API访问密钥，用于认证API请求。

- **格式**: 字符串
- **用途**: 同时用于关键词查询和指标提交API
- **示例**: `SITEMAP_API_KEY=your_api_key_here`

### WEBSITE_URLS
要监控的网站URL列表。

- **格式**: JSON数组
- **示例**: `WEBSITE_URLS=["https://example1.com", "https://example2.com"]`

## 可选的环境变量

### KEYWORDS_BATCH_SIZE
**功能**: 控制关键词API单次请求的最大关键词数量

- **默认值**: `4`
- **取值范围**: 1-10
- **工作原理**: 
  - 当系统需要查询多个关键词时，会将关键词分批处理
  - 每批最多包含指定数量的关键词，通过逗号分隔发送给API
  - 例如：`KEYWORDS_BATCH_SIZE=4` 时，发送 `keyword1,keyword2,keyword3,keyword4`
- **性能影响**:
  - **设置过大**: 可能超出API限制，导致请求失败或超时
  - **设置过小**: 增加请求次数，但提高成功率
- **建议设置**: 根据API提供商文档限制调整，多数关键词API支持1-4个关键词
- **示例**: `KEYWORDS_BATCH_SIZE=4`

### DEBUG
**功能**: 开启/关闭调试模式，控制详细日志输出

- **默认值**: `false`
- **可选值**: `true` 或 `false`
- **作用效果**:
  - `DEBUG=true`: 输出详细的调试信息，包括API请求、响应、处理过程等
  - `DEBUG=false`: 只输出关键的信息和错误日志，减少日志噪音
- **使用场景**: 
  - **开发/测试**: 设置为 `true` 便于排查问题
  - **生产环境**: 设置为 `false` 提高性能，减少日志存储
- **性能影响**: 开启调试模式会增加日志I/O，轻微影响性能
- **示例**: `DEBUG=false`

### MAX_CONCURRENT
**功能**: 控制系统最大并发处理的网站数量

- **默认值**: `3`
- **取值范围**: 1-10 (建议)
- **工作原理**:
  - 当监控多个网站时，系统会并行处理以提高效率
  - 此参数限制同时处理的网站数量，避免资源耗尽
  - 超出限制的网站会排队等待处理
- **性能权衡**:
  - **设置过大**: 可能消耗过多内存和网络连接，导致系统不稳定
  - **设置过小**: 处理速度慢，但系统稳定性更好
- **建议设置**: 
  - **小型VPS**: 1-3
  - **中等服务器**: 3-5
  - **高配置服务器**: 5-10
- **示例**: `MAX_CONCURRENT=3`

### KEYWORD_QUERY_TIMEOUT
**功能**: 设置关键词API请求的超时时间

- **默认值**: `30` (秒)
- **取值范围**: 10-120 (建议)
- **应用场景**: 
  - 调用关键词查询API时的网络请求超时
  - 包括连接超时和读取响应超时
- **超时后行为**: 
  - 系统会自动重试（最多2-3次）
  - 重试失败后使用默认数据代替
- **设置建议**:
  - **网络良好**: 20-30秒
  - **网络较慢**: 45-60秒
  - **API响应慢**: 60-90秒
- **注意事项**: 设置过短可能导致正常请求被误判为超时
- **示例**: `KEYWORD_QUERY_TIMEOUT=30`

### SITE_REQUEST_TIMEOUT
**功能**: 设置网站sitemap等内容请求的超时时间

- **默认值**: `20` (秒)
- **取值范围**: 5-60 (建议)
- **应用场景**:
  - 下载网站sitemap.xml文件
  - 访问网站页面获取内容
  - 检查网站可访问性
- **超时后行为**: 
  - 跳过该网站的当前处理周期
  - 记录错误日志但不影响其他网站处理
- **设置建议**:
  - **高速网站**: 10-15秒
  - **一般网站**: 15-25秒
  - **慢速网站**: 25-45秒
- **特殊情况**: 某些网站响应很慢，可以适当增加此值
- **示例**: `SITE_REQUEST_TIMEOUT=20`

### DATA_FILE
数据存储文件路径。

- **默认值**: `data/sites_data.json`
- **示例**: `DATA_FILE=custom_data/my_data.json`

## 示例 .env 文件

创建 `.env` 文件并设置以下内容：

```bash
# 数据加密密钥（必需）
ENCRYPTION_KEY=your_32_char_hex_key_here

# 关键词查询API地址列表（必需）
KEYWORDS_API_URLS=["https://api1.example.com", "https://api2.example.com"]

# 关键词指标API地址（必需）
KEYWORD_METRICS_API_URL=https://work.seokey.vip/

# API访问密钥（必需）
SITEMAP_API_KEY=your_api_key_here

# 监控网站列表（必需）
WEBSITE_URLS=["https://example1.com", "https://example2.com"]

# ========== 性能调优参数 ==========
# 关键词批处理大小 - 控制API请求效率
KEYWORDS_BATCH_SIZE=4

# 并发控制 - 平衡速度与稳定性
MAX_CONCURRENT=3

# 超时设置 - 避免长时间等待
KEYWORD_QUERY_TIMEOUT=30
SITE_REQUEST_TIMEOUT=20

# 调试模式 - 生产环境建议关闭
DEBUG=false
```

## 重要配置说明

### 性能调优指南

#### 关键词批处理优化
- **KEYWORDS_BATCH_SIZE** 是性能关键参数
- 设置过大可能导致API请求失败或超时
- 设置过小会增加请求次数，影响性能
- 建议根据API提供商的文档限制进行设置

#### 并发控制策略
- **MAX_CONCURRENT** 控制系统负载
- 需要根据服务器配置和网络环境调整
- 监控系统资源使用情况，避免过载

#### 超时时间设置
- **KEYWORD_QUERY_TIMEOUT**: API响应较慢时适当增加
- **SITE_REQUEST_TIMEOUT**: 网站响应较慢时适当增加
- 平衡等待时间与处理效率

#### 调试模式使用
- **开发阶段**: `DEBUG=true` 便于问题定位
- **生产环境**: `DEBUG=false` 减少日志开销
- **临时排查**: 可动态调整而无需重启

## 配置验证

运行以下命令检查配置：

```bash
python check_config.py
```

此脚本会验证所有环境变量的设置状态和格式正确性。 