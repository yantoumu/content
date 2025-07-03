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
import threading
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Iterator, Protocol
from urllib.parse import urlparse
from contextlib import contextmanager

from src.encryption import encryptor

# 配置日志
logger = logging.getLogger('content_watcher.data_manager')

# 文件路径
DATA_FILE = 'previous_data.json'


class IDataWriter(Protocol):
    """数据写入器接口 - 依赖倒置原则"""
    
    @contextmanager
    def open_write_stream(self):
        """打开写入流"""
        pass


class FileDataWriter:
    """文件数据写入器实现"""
    
    def __init__(self, file_path: str, buffer_size: int = 8192):
        self._file_path = file_path
        self._buffer_size = buffer_size
        self._lock = threading.RLock()
    
    @contextmanager
    def open_write_stream(self):
        """打开文件写入流 - 原子操作"""
        temp_path = f"{self._file_path}.tmp.{os.getpid()}"
        
        with self._lock:
            try:
                with open(temp_path, 'w', encoding='utf-8', buffering=self._buffer_size) as f:
                    yield f
                
                # 原子替换文件
                self._atomic_replace(temp_path, self._file_path)
                
            except Exception as e:
                self._cleanup_temp_file(temp_path)
                raise e
    
    def _atomic_replace(self, temp_path: str, target_path: str) -> None:
        """原子替换文件 - 跨平台兼容"""
        try:
            if os.name == 'nt':  # Windows
                if os.path.exists(target_path):
                    os.replace(temp_path, target_path)
                else:
                    os.rename(temp_path, target_path)
            else:  # Unix/Linux
                os.rename(temp_path, target_path)
        except OSError as e:
            logger.error(f"原子替换文件失败: {e}")
            raise e
    
    def _cleanup_temp_file(self, temp_path: str) -> None:
        """清理临时文件"""
        try:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        except OSError:
            pass  # 忽略清理失败


class StreamingDataWriter:
    """流式数据写入器 - 内存友好的数据保存"""
    
    def __init__(self, writer: FileDataWriter):
        self._writer = writer
    
    def write_streaming(self, data_iterator: Iterator[tuple]) -> bool:
        """流式写入数据 - 避免大对象内存占用
        
        Args:
            data_iterator: 产生(site_id, site_data)元组的迭代器
            
        Returns:
            bool: 写入是否成功
        """
        try:
            with self._writer.open_write_stream() as stream:
                stream.write('{"sites":{')  # JSON开始
                
                first_site = True
                for site_id, site_data in data_iterator:
                    if not first_site:
                        stream.write(',')
                    
                    # 分块序列化，控制内存使用
                    site_json = self._serialize_site_chunked(site_id, site_data)
                    stream.write(site_json)
                    first_site = False
                
                stream.write('}}')  # JSON结束
            
            logger.info("流式数据写入完成")
            return True
            
        except Exception as e:
            logger.error(f"流式写入失败: {e}")
            return False
    
    def _serialize_site_chunked(self, site_id: str, data: List[Dict]) -> str:
        """分块序列化站点数据 - 内存优化
        
        Args:
            site_id: 站点ID
            data: 站点数据列表
            
        Returns:
            str: 序列化的JSON字符串片段
        """
        # 使用紧凑格式，减少内存占用
        return f'"{site_id}":{json.dumps(data, separators=(",", ":"), ensure_ascii=False)}'

class DataManager:
    """处理数据的存储和加载"""

    def __init__(self):
        """初始化数据管理器"""
        self.previous_data = self._load_previous_data()

    def reload_data(self):
        """重新加载数据文件 - 用于测试和数据重置场景"""
        self.previous_data = self._load_previous_data()
        logger.debug("数据已重新加载")

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
                except (IOError, OSError, shutil.Error) as backup_err:
                    logger.error(f"备份数据文件失败: {backup_err}")
            return {}
        except (IOError, OSError, PermissionError) as e:
            logger.error(f"文件访问错误: {e}")
            return {}
        except Exception as e:
            logger.error(f"加载先前数据时出现未知错误: {e}")
            return {}

    def save_data(self, data: Dict[str, List[Dict[str, Any]]]) -> None:
        """保存数据到文件 - 使用流式写入优化内存"""
        try:
            # 创建流式写入器
            file_writer = FileDataWriter(DATA_FILE)
            streaming_writer = StreamingDataWriter(file_writer)
            
            # 创建数据迭代器，避免一次性加载所有数据到内存
            data_iterator = self._create_data_iterator(data)
            
            # 流式写入数据
            if streaming_writer.write_streaming(data_iterator):
                logger.info("数据已安全地保存到文件（流式写入）")
            else:
                raise Exception("流式写入失败")
                
        except Exception as e:
            logger.error(f"保存数据时发生错误: {e}")
            # 降级到传统方式作为备用
            self._fallback_save_data(data)
    
    def _create_data_iterator(self, data: Dict[str, List[Dict[str, Any]]]) -> Iterator[tuple]:
        """创建数据迭代器 - 惰性加载数据
        
        Args:
            data: 要保存的数据字典
            
        Yields:
            tuple: (site_id, site_data) 元组
        """
        for site_id, site_data in data.items():
            yield site_id, site_data
    
    def _fallback_save_data(self, data: Dict[str, List[Dict[str, Any]]]) -> None:
        """备用保存方法 - 传统原子写入"""
        try:
            import tempfile
            logger.warning("使用备用保存方法")
            
            # 创建临时文件
            fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(DATA_FILE))
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump({'sites': data}, f, ensure_ascii=False, separators=(',', ':'))

                # 原子替换
                if os.name == 'nt':  # Windows
                    if os.path.exists(DATA_FILE):
                        os.replace(temp_path, DATA_FILE)
                    else:
                        os.rename(temp_path, DATA_FILE)
                else:  # Unix/Linux
                    os.rename(temp_path, DATA_FILE)
                    
                logger.info("备用保存成功")
            except Exception as e:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                raise e
        except Exception as e:
            logger.error(f"备用保存也失败: {e}")

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

    def get_previous_urls(self, site_id: str) -> tuple[Dict[str, str], Dict[str, Any]]:
        """获取指定站点的先前URL和lastmod映射以及关键词数据

        Args:
            site_id: 站点标识符

        Returns:
            tuple: (URL到lastmod的映射字典, URL到关键词数据的映射字典)
        """
        previous_urls = {}
        previous_keywords_data = {}  # 存储上一次的关键词数据

        if site_id in self.previous_data:
            for item in self.previous_data[site_id]:
                if 'encrypted_url' in item:
                    try:
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
                                    # 不输出完整URL，避免敏感信息泄露
                                    domain_part = urlparse(decrypted_url).netloc if decrypted_url else '***'
                                    logger.error(f"出错的域名: {domain_part}")
                        else:
                            logger.warning("URL解密结果为空，跳过此项目")
                    except Exception as e:
                        logger.error(f"解密URL时出错: {e}")
                        # 不输出加密数据，避免敏感信息泄露
                        logger.error("跳过此加密URL项目")


        return previous_urls, previous_keywords_data

    def update_site_data(self, site_id: str, url_data_list: List[Dict[str, Any]]) -> None:
        """更新站点数据 - 优化并发安全性

        Args:
            site_id: 站点标识符
            url_data_list: URL数据列表
        """
        # 使用深拷贝避免并发修改问题
        import copy
        
        # 创建数据副本进行更新
        updated_data = copy.deepcopy(self.previous_data)
        updated_data[site_id] = url_data_list
        
        # 保存更新后的数据
        if self._save_data_safely(updated_data):
            # 只有保存成功才更新内存中的数据
            self.previous_data = updated_data
            logger.debug(f"站点 {site_id} 数据更新成功")
        else:
            logger.error(f"站点 {site_id} 数据保存失败")
            raise Exception(f"无法保存站点 {site_id} 的数据")
    
    def _save_data_safely(self, data: Dict[str, List[Dict[str, Any]]]) -> bool:
        """安全保存数据 - 带重试机制
        
        Args:
            data: 要保存的数据
            
        Returns:
            bool: 保存是否成功
        """
        max_retries = 3
        retry_delay = 0.5
        
        for attempt in range(max_retries):
            try:
                self.save_data(data)
                return True
            except Exception as e:
                logger.warning(f"保存尝试 {attempt + 1}/{max_retries} 失败: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2  # 指数退避
                else:
                    logger.error("所有保存尝试都失败")
                    
        return False

    def is_first_run(self) -> bool:
        """检查是否是首次运行"""
        return not bool(self.previous_data)



# 创建全局数据管理器实例
data_manager = DataManager()
