#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
资源管理器 - 遵循SOLID原则的资源生命周期管理
确保Session对象和文件句柄正确关闭
"""

import os
import io
import logging
import requests
import weakref
from typing import Any, Dict, Optional, List, Union, TextIO, BinaryIO
from contextlib import contextmanager, ExitStack
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)

# Interface Segregation Principle - 接口隔离
class IResourceManager(ABC):
    """资源管理器接口"""
    
    @abstractmethod
    def acquire_resource(self, resource_id: str) -> Any:
        """获取资源"""
        pass
    
    @abstractmethod
    def release_resource(self, resource_id: str) -> None:
        """释放资源"""
        pass

class ISessionManager(ABC):
    """Session管理器接口"""
    
    @abstractmethod
    def get_session(self) -> requests.Session:
        """获取Session"""
        pass
    
    @abstractmethod
    def close_session(self) -> None:
        """关闭Session"""
        pass

class IFileManager(ABC):
    """文件管理器接口"""
    
    @abstractmethod
    def open_file(self, file_path: str, mode: str = 'r') -> Union[TextIO, BinaryIO]:
        """打开文件"""
        pass
    
    @abstractmethod
    def close_all_files(self) -> None:
        """关闭所有文件"""
        pass

# Single Responsibility Principle - 每个类只负责一个职责
class SafeSessionManager(ISessionManager):
    """安全的Session管理器 - 单一职责：管理HTTP Session"""
    
    def __init__(self, 
                 timeout: int = 30,
                 max_retries: int = 3,
                 pool_connections: int = 10,
                 pool_maxsize: int = 10):
        self._session: Optional[requests.Session] = None
        self._timeout = timeout
        self._max_retries = max_retries
        self._pool_connections = pool_connections
        self._pool_maxsize = pool_maxsize
        self._is_closed = False
        
        # 使用weakref确保垃圾回收时正确清理
        weakref.finalize(self, self._cleanup_session, self._session)
    
    def get_session(self) -> requests.Session:
        """获取配置好的Session实例"""
        if self._is_closed:
            raise RuntimeError("SessionManager已关闭，无法获取Session")
        
        if self._session is None:
            self._session = self._create_session()
        
        return self._session
    
    def _create_session(self) -> requests.Session:
        """创建配置好的Session"""
        session = requests.Session()
        
        # 配置连接池
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=self._pool_connections,
            pool_maxsize=self._pool_maxsize,
            max_retries=requests.adapters.Retry(
                total=self._max_retries,
                backoff_factor=0.3,
                status_forcelist=[500, 502, 504]
            )
        )
        
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        
        # 设置默认超时
        session.timeout = self._timeout
        
        # 设置默认headers
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; ContentWatcher/1.0)',
            'Accept': 'application/json, text/html, */*',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive'
        })
        
        logger.debug("创建新的HTTP Session")
        return session
    
    def close_session(self) -> None:
        """安全关闭Session"""
        if self._session and not self._is_closed:
            try:
                self._session.close()
                logger.debug("HTTP Session已关闭")
            except Exception as e:
                logger.error(f"关闭Session时出错: {e}")
            finally:
                self._session = None
                self._is_closed = True
    
    @staticmethod
    def _cleanup_session(session: Optional[requests.Session]):
        """静态清理方法，用于weakref.finalize"""
        if session:
            try:
                session.close()
            except Exception:
                pass  # 垃圾回收时忽略异常
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_session()

class SafeFileManager(IFileManager):
    """安全的文件管理器 - 单一职责：管理文件句柄"""
    
    def __init__(self):
        self._open_files: Dict[str, Union[TextIO, BinaryIO]] = {}
        self._file_stack = ExitStack()
        self._is_closed = False
        
        # 使用weakref确保垃圾回收时正确清理
        weakref.finalize(self, self._cleanup_files, self._open_files)
    
    def open_file(self, file_path: str, mode: str = 'r', 
                  encoding: str = 'utf-8') -> Union[TextIO, BinaryIO]:
        """安全打开文件"""
        if self._is_closed:
            raise RuntimeError("FileManager已关闭，无法打开文件")
        
        # 如果文件已经打开，直接返回
        if file_path in self._open_files:
            return self._open_files[file_path]
        
        try:
            # 确保目录存在
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
            
            # 打开文件
            if 'b' in mode:
                file_obj = open(file_path, mode)
            else:
                file_obj = open(file_path, mode, encoding=encoding)
            
            # 注册到exit stack
            self._file_stack.enter_context(file_obj)
            self._open_files[file_path] = file_obj
            
            logger.debug(f"打开文件: {file_path} (模式: {mode})")
            return file_obj
            
        except Exception as e:
            logger.error(f"打开文件失败 {file_path}: {e}")
            raise
    
    def close_file(self, file_path: str) -> None:
        """关闭特定文件"""
        if file_path in self._open_files:
            try:
                self._open_files[file_path].close()
                del self._open_files[file_path]
                logger.debug(f"关闭文件: {file_path}")
            except Exception as e:
                logger.error(f"关闭文件失败 {file_path}: {e}")
    
    def close_all_files(self) -> None:
        """关闭所有文件"""
        if not self._is_closed:
            try:
                self._file_stack.close()
                self._open_files.clear()
                self._is_closed = True
                logger.debug("所有文件已关闭")
            except Exception as e:
                logger.error(f"关闭所有文件时出错: {e}")
    
    @staticmethod
    def _cleanup_files(open_files: Dict[str, Any]):
        """静态清理方法，用于weakref.finalize"""
        for file_obj in open_files.values():
            try:
                if hasattr(file_obj, 'close'):
                    file_obj.close()
            except Exception:
                pass  # 垃圾回收时忽略异常
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_all_files()

# Dependency Inversion Principle - 依赖抽象
class UnifiedResourceManager(IResourceManager):
    """统一资源管理器 - 协调所有资源管理"""
    
    def __init__(self):
        self.session_manager = SafeSessionManager()
        self.file_manager = SafeFileManager()
        self._resources: Dict[str, Any] = {}
        self._is_closed = False
    
    def acquire_resource(self, resource_id: str) -> Any:
        """获取资源"""
        if self._is_closed:
            raise RuntimeError("ResourceManager已关闭")
        
        if resource_id in self._resources:
            return self._resources[resource_id]
        
        # 根据resource_id类型决定资源类型
        if resource_id == 'http_session':
            resource = self.session_manager.get_session()
        elif resource_id.startswith('file:'):
            file_path = resource_id[5:]  # 移除'file:'前缀
            resource = self.file_manager.open_file(file_path)
        else:
            raise ValueError(f"未知的资源类型: {resource_id}")
        
        self._resources[resource_id] = resource
        return resource
    
    def release_resource(self, resource_id: str) -> None:
        """释放资源"""
        if resource_id in self._resources:
            if resource_id == 'http_session':
                self.session_manager.close_session()
            elif resource_id.startswith('file:'):
                file_path = resource_id[5:]
                self.file_manager.close_file(file_path)
            
            del self._resources[resource_id]
    
    def close_all_resources(self) -> None:
        """关闭所有资源"""
        if not self._is_closed:
            try:
                self.session_manager.close_session()
                self.file_manager.close_all_files()
                self._resources.clear()
                self._is_closed = True
                logger.info("所有资源已释放")
            except Exception as e:
                logger.error(f"释放资源时出错: {e}")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_all_resources()

# 全局资源管理器实例
_resource_manager: Optional[UnifiedResourceManager] = None

def get_resource_manager() -> UnifiedResourceManager:
    """获取全局资源管理器实例"""
    global _resource_manager
    if _resource_manager is None or _resource_manager._is_closed:
        _resource_manager = UnifiedResourceManager()
    return _resource_manager

@contextmanager
def managed_session():
    """Session上下文管理器"""
    with SafeSessionManager() as session_manager:
        yield session_manager.get_session()

@contextmanager  
def managed_file(file_path: str, mode: str = 'r', encoding: str = 'utf-8'):
    """文件上下文管理器"""
    with SafeFileManager() as file_manager:
        yield file_manager.open_file(file_path, mode, encoding)

@contextmanager
def managed_resources():
    """统一资源上下文管理器"""
    with UnifiedResourceManager() as resource_manager:
        yield resource_manager 