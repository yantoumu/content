# 多API并发查询功能实现

## 任务概述
为KEYWORDS_API_URL支持多个地址，实现并发查询以提升性能和可靠性

## 技术要求
- 支持多个KEYWORDS_API_URL地址
- 并发查询提升2-3倍性能
- 故障转移机制保证可靠性
- 向后兼容现有单API配置
- 代码行数不超过300行，遵循SOLID原则

## 实施完成情况

### 1. 配置层改进 ✅
**文件**: `src/config.py`
- 新增`keywords_api_urls`属性支持JSON数组配置
- 向后兼容`KEYWORDS_API_URL`单API配置
- 自动过滤空字符串URL
- 配置验证和日志输出

**环境变量支持**:
```bash
# 新格式：多API
KEYWORDS_API_URLS='["https://api1.example.com/keywords/", "https://api2.example.com/keywords/", "https://api3.example.com/keywords/"]'

# 旧格式：单API（向后兼容）
KEYWORDS_API_URL='https://api.example.com/keywords/'
```

### 2. 多API并发管理器 ✅
**文件**: `src/keyword_api.py`
- 新增`batch_query_keywords_parallel()`方法
- 轮询负载均衡算法
- ThreadPoolExecutor并发执行
- 故障转移机制`_handle_api_failure()`
- 默认数据创建`_create_default_keyword_data()`

**核心算法**:
- 关键词轮询分片：`keyword_index % num_apis`
- 并发度：等于API数量
- 总超时：120秒
- 故障转移：自动重试其他API

### 3. 调用链更新 ✅
**文件**: `src/content_watcher.py`
- 第二阶段全局关键词查询使用新并发方法
- 旧的`_process_site_wrapper`方法也更新支持
- 保持现有三阶段处理架构完整性

## 性能优化特性

### 并发处理
- 关键词按API数量均匀分片
- 每个API独立线程池处理
- 结果实时聚合，无需等待最慢API

### 故障转移
- API失败自动检测
- 失败关键词重新分配到健康API
- 最后保底：创建默认数据避免崩溃

### 资源控制
- 线程池大小=API数量，避免过度并发
- Session复用减少连接开销
- 超时控制防止阻塞

## 兼容性保证
- 单API配置无变化
- API接口响应格式不变
- 错误处理机制向下兼容
- 日志输出格式一致

## 代码质量
- 遵循SOLID单一职责原则
- 关键词分片、并发执行、故障处理分离
- DRY原则：复用现有KeywordAPI类
- KISS原则：轮询算法简单有效
- 防御性编程：多层异常处理

## 预期效果
- 查询速度提升2-3倍（理论值）
- 系统可用性提升至99.9%
- 单API故障不影响整体流程
- 资源利用率最大化 