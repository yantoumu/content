# 内容监控系统配置说明

## 环境变量配置

### 基础配置

#### LOGLEVEL
- **描述**: 日志输出级别
- **可选值**: `DEBUG`, `INFO`, `WARNING`, `ERROR`
- **默认值**: `INFO`
- **示例**: `LOGLEVEL=INFO`

#### ENCRYPTION_KEY
- **描述**: 数据加密密钥（必须设置）
- **类型**: 字符串
- **示例**: `ENCRYPTION_KEY=your_encryption_key_here`

### 网站监控配置

#### WEBSITE_URLS
- **描述**: 要监控的网站URL列表
- **格式**: JSON数组
- **示例**: `WEBSITE_URLS=["https://example.com/sitemap.xml","https://another-site.com/sitemap.xml"]`

### 关键词查询API配置

#### KEYWORDS_API_URLS (推荐)
- **描述**: 多个关键词查询API地址，支持并发查询和负载均衡
- **格式**: JSON数组
- **示例**: `KEYWORDS_API_URLS=["https://api1.example.com","https://api2.example.com"]`

#### KEYWORDS_API_URL (向后兼容)
- **描述**: 单个关键词查询API地址
- **格式**: URL字符串
- **示例**: `KEYWORDS_API_URL=https://api.example.com`

### 关键词指标API配置 (新版)

#### KEYWORD_METRICS_API_URL
- **描述**: 关键词指标批量提交API基础地址
- **格式**: 基础域名URL
- **路径拼接**: 系统会自动拼接 `/api/v1/keyword-metrics/batch` 路径
- **示例**: 
  - 配置: `KEYWORD_METRICS_API_URL=https://work.seokey.vip/`
  - 实际调用: `https://work.seokey.vip/api/v1/keyword-metrics/batch`

#### SITEMAP_API_KEY
- **描述**: API访问密钥（新旧版本共用）
- **格式**: 字符串
- **示例**: `SITEMAP_API_KEY=your_api_key_here`

### 已弃用的配置项

#### SITEMAP_API_URL (已弃用)
- **状态**: 已禁用，代码中强制设置为 `False`
- **替代方案**: 使用 `KEYWORD_METRICS_API_URL`
- **说明**: 旧版网站地图更新API已被新版关键词指标API替代

#### SITEMAP_URLS (已弃用)
- **状态**: 仍可使用，但建议改为 `WEBSITE_URLS`
- **说明**: 向后兼容，建议使用新的配置名称

## 配置示例

创建 `.env` 文件并配置以下内容：

```bash
# 基础配置
LOGLEVEL=INFO
ENCRYPTION_KEY=your_encryption_key_here

# 网站监控
WEBSITE_URLS=["https://example.com/sitemap.xml"]

# 关键词查询API（多API并发）
KEYWORDS_API_URLS=["https://api1.example.com","https://api2.example.com"]

# 关键词指标API（新版）
KEYWORD_METRICS_API_URL=https://work.seokey.vip/
SITEMAP_API_KEY=your_api_key_here
```

## 重要变更说明

### 2024年更新：关键词指标API路径自动拼接

**变更内容**: `KEYWORD_METRICS_API_URL` 现在支持自动路径拼接功能

**变更前**: 需要提供完整的API路径
```bash
KEYWORD_METRICS_API_URL=https://work.seokey.vip/api/v1/keyword-metrics/batch
```

**变更后**: 只需提供基础域名，系统自动拼接路径
```bash
KEYWORD_METRICS_API_URL=https://work.seokey.vip/
```

**拼接逻辑**:
1. 自动提取基础域名部分
2. 拼接标准API路径 `/api/v1/keyword-metrics/batch`
3. 支持多种输入格式的智能处理

**兼容性**: 同时支持新旧两种配置方式，向后兼容 