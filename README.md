# 网站内容更新监控

这是一个用于监控网站内容更新并发送通知的工具。该工具通过GitHub Actions自动运行，可以监控多个网站的内容变化，并通过Telegram发送通知。

## 主要功能

- 监控多个网站的内容更新
- 使用加密技术保护监控的数据
- 通过Telegram发送更新通知
- 定时自动监控（默认每12小时检查一次）

## 使用方法

### 1. 准备工作

1. Fork本仓库到你的GitHub账户
2. 创建一个Telegram Bot并获取Token
   - 在Telegram中搜索 @BotFather
   - 发送 `/newbot` 并按提示完成创建
   - 记下Bot Token
3. 获取你的Telegram Chat ID
   - 可以使用 @getidbot 获取

### 2. 配置GitHub Secrets

在仓库的Settings > Secrets and variables > Actions中添加以下Secret:

- `SITEMAP_URLS`: 要监控的网站地址JSON数组，例如 `["https://example1.com/file.xml", "https://example2.com/file.xml"]`
- `ENCRYPTION_KEY`: 32字节的加密密钥（可使用 `openssl rand -base64 32` 生成）
- `TELEGRAM_BOT_TOKEN`: 你的Telegram Bot Token
- `TELEGRAM_CHAT_ID`: 你的Telegram Chat ID

### 3. 启用GitHub Actions

- 默认情况下，Actions会按配置的时间表自动运行
- 也可以在Actions标签页手动触发工作流

## 配置选项

修改 `.github/workflows/monitor_job.yml` 文件可以调整:

- 监控频率（修改cron表达式）
- Python版本
- 其他GitHub Actions相关设置

## 本地开发

如需在本地运行或测试:

```bash
# 克隆仓库
git clone https://github.com/yourusername/your-repo-name.git
cd your-repo-name

# 安装依赖
pip install -r requirements.txt

# 设置环境变量
export SITEMAP_URLS='["https://example1.com/file.xml"]'
export ENCRYPTION_KEY='your_32_byte_key'
export TELEGRAM_BOT_TOKEN='your_bot_token'
export TELEGRAM_CHAT_ID='your_chat_id'

# 运行脚本
python content_watcher.py
```

## 注意事项

- 确保加密密钥安全，一旦更改将无法读取之前的加密数据
- 定时任务执行期间，保持Telegram Bot处于活跃状态 