# API日志改进说明

## 问题描述
用户反馈关键词API出现500错误时，日志信息不够详细，无法确定具体是哪个API调用失败。

## 解决方案

### 1. 关键词API日志增强 (`src/keyword_api.py`)

**改进前的日志**：
```
API请求返回500，将在2秒后重试
```

**改进后的日志**：
```
API请求返回500，将在2秒后重试
失败的API URL: https://k.seokey.vip/api/keywords/game,puzzle,strategy
请求的关键词: game,puzzle,strategy (共3个)
```

### 2. 关键词指标API日志增强 (`src/keyword_metrics_api.py`)

**改进前的日志**：
```
服务器暂不可用(500)，建议重试
```

**改进后的日志**：
```
服务器暂不可用(500)，建议重试
失败的API URL: https://api.example.com/v1/keyword-metrics/batch
```

## 功能特性

### 🔍 详细错误信息
- **完整API URL**：显示具体调用失败的API地址
- **关键词预览**：显示请求的关键词内容（前50字符）
- **关键词数量**：显示本次请求包含的关键词总数

### 🛡️ 隐私保护
- **自动截断**：关键词字符串超过50字符时自动截断并添加省略号
- **敏感信息过滤**：避免在日志中暴露过多敏感数据

### 📊 全面覆盖
- **HTTP错误**：500、429、502、503、504等状态码
- **网络异常**：连接超时、SSL错误等
- **重试机制**：每次重试都显示详细信息
- **最终失败**：重试耗尽时显示完整错误上下文

## 日志示例

### HTTP 500错误重试
```
2025-06-20 00:07:14,891 - content_watcher.keyword_api - WARNING - API请求返回500，将在2秒后重试
2025-06-20 00:07:14,891 - content_watcher.keyword_api - WARNING - 失败的API URL: https://k.seokey.vip/api/keywords/game,puzzle,strategy,action,adventure
2025-06-20 00:07:14,891 - content_watcher.keyword_api - WARNING - 请求的关键词: game,puzzle,strategy,action,adventure (共5个)
```

### 网络连接异常
```
2025-06-20 00:07:17,590 - content_watcher.keyword_api - WARNING - API请求异常: SSLError，将在2秒后重试
2025-06-20 00:07:17,590 - content_watcher.keyword_api - WARNING - 异常的API URL: https://api.example.com/keywords/very,long,keyword,list,that,gets,truncated
2025-06-20 00:07:17,590 - content_watcher.keyword_api - WARNING - 请求的关键词: very,long,keyword,list,that,gets,truncated,... (共20个)
```

### 最终失败错误
```
2025-06-20 00:07:20,338 - content_watcher.keyword_api - ERROR - API请求异常，重试次数超过上限: ConnectionError
2025-06-20 00:07:20,338 - content_watcher.keyword_api - ERROR - 异常的API URL: https://api.example.com/keywords/game,action
2025-06-20 00:07:20,338 - content_watcher.keyword_api - ERROR - 请求的关键词: game,action (共2个)
```

## 使用方法

这些改进是自动生效的，无需额外配置。当API调用出现问题时，你将在日志中看到：

1. **具体的API URL** - 帮助识别是哪个API服务出现问题
2. **请求的关键词** - 了解是哪些关键词导致的问题
3. **关键词数量** - 判断是否因批次过大导致问题

## 调试建议

当看到API错误日志时，可以：

1. **检查API服务状态**：访问失败的API URL查看服务是否正常
2. **分析关键词内容**：检查是否有特殊字符或过长的关键词
3. **调整批次大小**：如果关键词数量过多，考虑减小`KEYWORDS_BATCH_SIZE`配置
4. **检查网络连接**：确认网络环境是否稳定

## 技术实现

- ✅ 遵循SOLID原则：单一职责，只增强日志功能
- ✅ KISS原则：实现简洁，易于维护
- ✅ 向后兼容：不影响现有功能
- ✅ 性能友好：日志处理开销最小 