#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主入口文件
启动网站内容监控程序
"""

import logging
import argparse
import os

# 自动加载.env文件（如果存在）
def load_env_file():
    """加载.env文件中的环境变量"""
    env_file = '.env'
    if os.path.exists(env_file):
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    # 移除引号（如果有）
                    value = value.strip('"').strip("'")
                    os.environ[key] = value
        print(f"✅ 已加载 {env_file} 文件")
    else:
        print(f"⚠️  未找到 {env_file} 文件，使用系统环境变量")

# 在导入其他模块之前加载环境变量
load_env_file()

from src.content_watcher import ContentWatcher

# 配置日志
log_level = os.environ.get('LOGLEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('content_watcher.main')

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='网站内容更新监控工具')
    parser.add_argument('--test', action='store_true', help='在测试模式下运行')
    return parser.parse_args()

def main():
    """主函数"""
    args = parse_args()
    try:
        # 简化配置：统一使用全量处理模式
        logger.info(f"启动参数: 测试模式={args.test}")

        # 创建内容监控器
        watcher = ContentWatcher(test_mode=args.test)
        # 运行监控
        watcher.run()

        logger.info("监控任务完成")

    except Exception as e:
        logger.error(f"运行监控任务时出错: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 1

    return 0

if __name__ == "__main__":
    exit(main())
