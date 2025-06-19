# 关键词指标API路径拼接功能

## 任务概述
为 `KEYWORD_METRICS_API_URL` 添加自动路径拼接功能，用户只需配置基础域名，系统自动拼接 `/api/v1/keyword-metrics/batch` 路径。

## 问题背景
- 新版 KeywordMetricsAPI 缺少自动路径拼接功能
- 用户必须手动提供完整的API路径，使用不便
- 旧版 SITEMAP_API_URL 有类似的拼接功能，但已被禁用

## 解决方案

### 1. 代码修改
在 `src/config.py` 中为 `KEYWORD_METRICS_API_URL` 添加路径拼接逻辑：

```python
# 确保使用正确的API URL - 自动拼接批量API路径
if metrics_api_url:
    # 解析基础URL部分（协议和域名）
    import re
    base_url_match = re.match(r'(https?://[^/]+).*', metrics_api_url)
    if base_url_match:
        base_url = base_url_match.group(1)
        # 使用正确的API路径 - 批量关键词指标API
        self.metrics_batch_api_url = f"{base_url}/api/v1/keyword-metrics/batch"
    else:
        # 如果无法解析，尝试构造批量提交URL
        if metrics_api_url.endswith('/api/v1/keyword-metrics'):
            self.metrics_batch_api_url = f"{metrics_api_url}/batch"
        elif metrics_api_url.endswith('/api/v1/keyword-metrics/batch'):
            # 已经是完整路径，直接使用
            self.metrics_batch_api_url = metrics_api_url
        else:
            self.metrics_batch_api_url = f"{metrics_api_url}/api/v1/keyword-metrics/batch"
else:
    self.metrics_batch_api_url = ''
```

### 2. 拼接逻辑
1. **基础域名提取**: 使用正则表达式提取 `https://domain.com` 部分
2. **标准路径拼接**: 自动拼接 `/api/v1/keyword-metrics/batch`
3. **智能处理**: 支持多种输入格式
4. **向后兼容**: 完整路径直接使用

### 3. 支持的输入格式
- `https://work.seokey.vip/` → `https://work.seokey.vip/api/v1/keyword-metrics/batch`
- `https://work.seokey.vip` → `https://work.seokey.vip/api/v1/keyword-metrics/batch`
- `https://work.seokey.vip/api/v1/keyword-metrics` → `https://work.seokey.vip/api/v1/keyword-metrics/batch`
- `https://work.seokey.vip/api/v1/keyword-metrics/batch` → `https://work.seokey.vip/api/v1/keyword-metrics/batch`

## 文档更新
创建了 `CONFIGURATION.md` 配置说明文档，包含：
- 详细的环境变量说明
- 配置示例
- 重要变更说明
- 向后兼容性说明

## 使用示例

### 新的配置方式（推荐）
```bash
KEYWORD_METRICS_API_URL=https://work.seokey.vip/
SITEMAP_API_KEY=your_api_key_here
```

### 旧的配置方式（仍然支持）
```bash
KEYWORD_METRICS_API_URL=https://work.seokey.vip/api/v1/keyword-metrics/batch
SITEMAP_API_KEY=your_api_key_here
```

## 技术实现

### 文件修改
- `src/config.py`: 添加路径拼接逻辑
- `CONFIGURATION.md`: 新建配置说明文档

### 设计原则
- ✅ SOLID原则：单一职责，配置处理逻辑集中
- ✅ KISS原则：简单易用，用户只需配置基础域名
- ✅ DRY原则：复用旧版的拼接逻辑模式
- ✅ 向后兼容：支持新旧两种配置方式

## 测试建议
1. 测试基础域名拼接：`https://work.seokey.vip/`
2. 测试无结尾斜杠：`https://work.seokey.vip`
3. 测试部分路径：`https://work.seokey.vip/api/v1/keyword-metrics`
4. 测试完整路径：`https://work.seokey.vip/api/v1/keyword-metrics/batch`
5. 验证日志输出显示正确的拼接结果

## 完成时间
2024年 - 根据用户需求实现 