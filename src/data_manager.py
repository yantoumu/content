#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据管理模块
处理数据的存储和加载
"""

import os
import json
import base64
import logging
import hashlib
import time
from typing import Dict, List, Any
from urllib.parse import urlparse

from src.encryption import encryptor

# 配置日志
logger = logging.getLogger('content_watcher.data_manager')

# 文件路径
DATA_FILE = 'previous_data.json'

class DataManager:
    """处理数据的存储和加载"""

    def __init__(self):
        """初始化数据管理器"""
        self.previous_data = self._load_previous_data()

    def _load_previous_data(self) -> Dict[str, List[Dict[str, str]]]:
        """加载先前保存的数据"""
        try:
            if os.path.exists(DATA_FILE):
                # 使用缓冲读取来提高性能
                with open(DATA_FILE, 'r', encoding='utf-8', buffering=65536) as f:
                    data = json.load(f)
                return data.get('sites', {})
            else:
                logger.info("先前的数据文件不存在，将创建新文件")
                return {}
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误: {e}")
            # 备份损坏的文件并创建新的空文件
            if os.path.exists(DATA_FILE):
                backup_file = f"{DATA_FILE}.bak.{int(time.time())}"
                try:
                    import shutil
                    shutil.copy2(DATA_FILE, backup_file)
                    logger.info(f"已备份损坏的数据文件到 {backup_file}")
                except Exception as backup_err:
                    logger.error(f"备份数据文件失败: {backup_err}")
            return {}
        except Exception as e:
            logger.error(f"加载先前数据时出错: {e}")
            return {}

    def save_data(self, data: Dict[str, List[Dict[str, Any]]]) -> None:
        """保存数据到文件"""
        try:
            # 首先写入临时文件，然后原子地重命名，避免数据损坏
            import tempfile
            import os

            # 创建临时文件
            fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(DATA_FILE))
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    # 使用更高效的JSON序列化选项
                    json.dump({'sites': data}, f, ensure_ascii=False, separators=(',', ':'))

                # 在Windows上，需要先删除目标文件
                if os.path.exists(DATA_FILE):
                    os.remove(DATA_FILE)

                # 原子地重命名临时文件
                os.rename(temp_path, DATA_FILE)
                logger.info("数据已安全地保存到文件")
            except Exception as e:
                os.unlink(temp_path)  # 删除临时文件
                raise e
        except Exception as e:
            logger.error(f"保存数据时出错: {e}")

    def get_site_identifier(self, url: str) -> str:
        """获取网站标识符"""
        try:
            parsed = urlparse(url)
            # 使用主机名前8个字符作为站点ID
            return hashlib.md5(parsed.netloc.encode()).hexdigest()[:8]
        except Exception:
            # 如果解析失败，使用MD5哈希值的前8个字符
            return hashlib.md5(url.encode()).hexdigest()[:8]

    def format_site_name(self, site_id: str, index: int) -> str:
        """格式化网站名称用于通知"""
        return f"网站 {index+1} ({site_id})"

    def get_previous_urls(self, site_id: str) -> Dict[str, str]:
        """获取指定站点的先前URL和lastmod映射

        Args:
            site_id: 站点标识符

        Returns:
            URL到lastmod的映射字典
        """
        previous_urls = {}
        previous_keywords_data = {}  # 存储上一次的关键词数据

        if site_id in self.previous_data:
            for item in self.previous_data[site_id]:
                if 'encrypted_url' in item:
                    decrypted_url = encryptor.decrypt_url(item['encrypted_url'])
                    if decrypted_url:
                        previous_urls[decrypted_url] = item.get('lastmod')
                        # 如果存在关键词数据，也进行解密和存储
                        if 'keywords_data' in item:
                            try:
                                encrypted_keywords_data = item['keywords_data']
                                decoded_data = base64.b64decode(encrypted_keywords_data)
                                decrypted_data = encryptor.decrypt_data(decoded_data)
                                keywords_data = json.loads(decrypted_data)
                                previous_keywords_data[decrypted_url] = keywords_data
                            except Exception as e:
                                logger.error(f"解密关键词数据时出错: {e}")
                                logger.error(f"出错的URL: {decrypted_url}")

        return previous_urls, previous_keywords_data

    def update_site_data(self, site_id: str, url_data_list: List[Dict[str, Any]]) -> None:
        """更新站点数据

        Args:
            site_id: 站点标识符
            url_data_list: URL数据列表
        """
        self.previous_data[site_id] = url_data_list
        self.save_data(self.previous_data)

    def is_first_run(self) -> bool:
        """检查是否是首次运行"""
        return not bool(self.previous_data)

# 创建全局数据管理器实例
data_manager = DataManager()
