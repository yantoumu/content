#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主入口文件
启动网站内容监控程序
"""

import logging
import argparse

from src.content_watcher import ContentWatcher

# 配置日志
import os
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
    parser.add_argument('--max-updates', type=int, default=0, help='首次运行时最多报告的更新数量，0表示不限制')
    return parser.parse_args()

def main():
    """主函数"""
    args = parse_args()
    try:
        # 创建内容监控器
        watcher = ContentWatcher(
            test_mode=args.test,
            max_first_run_updates=args.max_updates
        )
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
