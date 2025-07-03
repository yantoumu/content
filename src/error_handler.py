#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
错误处理系统 - 遵循SOLID原则的异常管理
避免过度捕获异常，确保错误正确传播
"""

import logging
import traceback
import functools
from typing import Any, Callable, Dict, List, Optional, Type, Union
from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

# Interface Segregation Principle - 分离错误处理接口
class IErrorHandler(ABC):
    """错误处理器接口"""
    
    @abstractmethod
    def can_handle(self, error: Exception) -> bool:
        """判断是否能处理该错误"""
        pass
    
    @abstractmethod
    def handle_error(self, error: Exception, context: Dict[str, Any]) -> Any:
        """处理错误"""
        pass

class IErrorReporter(ABC):
    """错误报告器接口"""
    
    @abstractmethod
    def report_error(self, error_info: 'ErrorInfo') -> None:
        """报告错误"""  
        pass

# Single Responsibility Principle - 错误严重性分级
class ErrorSeverity(Enum):
    """错误严重性级别"""
    LOW = "low"          # 可恢复的轻微错误
    MEDIUM = "medium"    # 需要注意但不影响主流程的错误
    HIGH = "high"        # 影响功能的严重错误
    CRITICAL = "critical" # 导致系统崩溃的致命错误

@dataclass
class ErrorInfo:
    """错误信息数据类"""
    error: Exception
    severity: ErrorSeverity
    context: Dict[str, Any]
    timestamp: datetime
    module: str
    function: str
    recoverable: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'error_type': type(self.error).__name__,
            'error_message': str(self.error),
            'severity': self.severity.value,
            'context': self.context,
            'timestamp': self.timestamp.isoformat(),
            'module': self.module,
            'function': self.function,
            'recoverable': self.recoverable,
            'traceback': traceback.format_exception(type(self.error), self.error, self.error.__traceback__)
        }

# Single Responsibility Principle - 具体错误处理器
class NetworkErrorHandler(IErrorHandler):
    """网络错误处理器 - 单一职责：处理网络相关错误"""
    
    def can_handle(self, error: Exception) -> bool:
        """判断是否为网络错误"""
        import requests
        network_errors = (
            requests.exceptions.RequestException,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.HTTPError,
            ConnectionError,
            TimeoutError
        )
        return isinstance(error, network_errors)
    
    def handle_error(self, error: Exception, context: Dict[str, Any]) -> Any:
        """处理网络错误"""
        if isinstance(error, (ConnectionError, TimeoutError)):
            return ErrorInfo(
                error=error,
                severity=ErrorSeverity.HIGH,
                context=context,
                timestamp=datetime.now(),
                module=context.get('module', 'unknown'),
                function=context.get('function', 'unknown'),
                recoverable=True
            )
        else:
            return ErrorInfo(
                error=error,
                severity=ErrorSeverity.MEDIUM,
                context=context,
                timestamp=datetime.now(),
                module=context.get('module', 'unknown'),
                function=context.get('function', 'unknown'),
                recoverable=True
            )

class FileSystemErrorHandler(IErrorHandler):
    """文件系统错误处理器 - 单一职责：处理文件系统错误"""
    
    def can_handle(self, error: Exception) -> bool:
        """判断是否为文件系统错误"""
        file_errors = (
            FileNotFoundError,
            PermissionError,
            IsADirectoryError,
            OSError,
            IOError
        )
        return isinstance(error, file_errors)
    
    def handle_error(self, error: Exception, context: Dict[str, Any]) -> Any:
        """处理文件系统错误"""
        if isinstance(error, PermissionError):
            severity = ErrorSeverity.HIGH
            recoverable = False
        elif isinstance(error, FileNotFoundError):
            severity = ErrorSeverity.MEDIUM
            recoverable = True
        else:
            severity = ErrorSeverity.MEDIUM
            recoverable = True
        
        return ErrorInfo(
            error=error,
            severity=severity,
            context=context,
            timestamp=datetime.now(),
            module=context.get('module', 'unknown'),
            function=context.get('function', 'unknown'),
            recoverable=recoverable
        )

class DataValidationErrorHandler(IErrorHandler):
    """数据验证错误处理器 - 单一职责：处理数据验证错误"""
    
    def can_handle(self, error: Exception) -> bool:
        """判断是否为数据验证错误"""
        validation_errors = (
            ValueError,
            TypeError,
            KeyError,
            AttributeError
        )
        return isinstance(error, validation_errors)
    
    def handle_error(self, error: Exception, context: Dict[str, Any]) -> Any:
        """处理数据验证错误"""
        if isinstance(error, (ValueError, TypeError)):
            severity = ErrorSeverity.HIGH
            recoverable = False
        else:
            severity = ErrorSeverity.MEDIUM  
            recoverable = True
        
        return ErrorInfo(
            error=error,
            severity=severity,
            context=context,
            timestamp=datetime.now(),
            module=context.get('module', 'unknown'),
            function=context.get('function', 'unknown'),
            recoverable=recoverable
        )

class GenericErrorHandler(IErrorHandler):
    """通用错误处理器 - 处理未分类的错误"""
    
    def can_handle(self, error: Exception) -> bool:
        """可以处理任何错误"""
        return True
    
    def handle_error(self, error: Exception, context: Dict[str, Any]) -> Any:
        """处理通用错误"""
        return ErrorInfo(
            error=error,
            severity=ErrorSeverity.CRITICAL,
            context=context,
            timestamp=datetime.now(),
            module=context.get('module', 'unknown'),
            function=context.get('function', 'unknown'),
            recoverable=False
        )

# Open/Closed Principle - 可扩展的错误管理器
class ErrorManager:
    """错误管理器 - 协调各种错误处理器"""
    
    def __init__(self):
        self._handlers: List[IErrorHandler] = []
        self._reporters: List[IErrorReporter] = []
        self._error_history: List[ErrorInfo] = []
        self._max_history_size = 1000
        
        # 注册默认处理器（按优先级排序）
        self._register_default_handlers()
    
    def _register_default_handlers(self):
        """注册默认错误处理器"""
        self._handlers = [
            NetworkErrorHandler(),
            FileSystemErrorHandler(),
            DataValidationErrorHandler(),
            GenericErrorHandler()  # 放在最后作为兜底
        ]
    
    def add_handler(self, handler: IErrorHandler) -> None:
        """添加自定义错误处理器"""
        # 插入到通用处理器之前
        self._handlers.insert(-1, handler)
    
    def add_reporter(self, reporter: IErrorReporter) -> None:
        """添加错误报告器"""
        self._reporters.append(reporter)
    
    def handle_error(self, error: Exception, context: Optional[Dict[str, Any]] = None) -> ErrorInfo:
        """处理错误"""
        if context is None:
            context = {}
        
        # 添加调用栈信息到上下文
        if 'module' not in context or 'function' not in context:
            frame = traceback.extract_stack()[-3]  # 获取调用者信息
            context.setdefault('module', frame.filename.split('/')[-1])
            context.setdefault('function', frame.name)
        
        # 找到合适的处理器
        error_info = None
        for handler in self._handlers:
            if handler.can_handle(error):
                error_info = handler.handle_error(error, context)
                break
        
        if error_info is None:
            # 如果没有处理器能处理，使用通用处理器
            error_info = self._handlers[-1].handle_error(error, context)
        
        # 记录错误历史
        self._add_to_history(error_info)
        
        # 报告错误
        for reporter in self._reporters:
            try:
                reporter.report_error(error_info)
            except Exception as report_error:
                logger.error(f"错误报告器失败: {report_error}")
        
        return error_info
    
    def _add_to_history(self, error_info: ErrorInfo) -> None:
        """添加到错误历史"""
        self._error_history.append(error_info)
        
        # 限制历史记录大小
        if len(self._error_history) > self._max_history_size:
            self._error_history = self._error_history[-self._max_history_size:]
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """获取错误统计信息"""
        if not self._error_history:
            return {'total_errors': 0}
        
        severity_counts = {}
        error_type_counts = {}
        
        for error_info in self._error_history:
            # 统计严重性
            severity = error_info.severity.value
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
            
            # 统计错误类型
            error_type = type(error_info.error).__name__
            error_type_counts[error_type] = error_type_counts.get(error_type, 0) + 1
        
        return {
            'total_errors': len(self._error_history),
            'severity_counts': severity_counts,
            'error_type_counts': error_type_counts,
            'recent_errors': [info.to_dict() for info in self._error_history[-5:]]
        }

class LoggingErrorReporter(IErrorReporter):
    """日志错误报告器 - 将错误记录到日志"""
    
    def report_error(self, error_info: ErrorInfo) -> None:
        """报告错误到日志"""
        log_level = {
            ErrorSeverity.LOW: logging.INFO,
            ErrorSeverity.MEDIUM: logging.WARNING,
            ErrorSeverity.HIGH: logging.ERROR,
            ErrorSeverity.CRITICAL: logging.CRITICAL
        }.get(error_info.severity, logging.ERROR)
        
        message = (
            f"[{error_info.severity.value.upper()}] "
            f"{type(error_info.error).__name__}: {error_info.error} "
            f"in {error_info.module}:{error_info.function}"
        )
        
        logger.log(log_level, message, extra={
            'error_context': error_info.context,
            'recoverable': error_info.recoverable
        })

# 全局错误管理器实例
_error_manager: Optional[ErrorManager] = None

def get_error_manager() -> ErrorManager:
    """获取全局错误管理器实例"""
    global _error_manager
    if _error_manager is None:
        _error_manager = ErrorManager()
        _error_manager.add_reporter(LoggingErrorReporter())
    return _error_manager

# 装饰器 - 自动错误处理
def handle_errors(
    severity: ErrorSeverity = ErrorSeverity.MEDIUM,
    recoverable: bool = True,
    re_raise: bool = False,
    default_return: Any = None
):
    """错误处理装饰器"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                context = {
                    'module': func.__module__,
                    'function': func.__name__,
                    'args': args,
                    'kwargs': kwargs
                }
                
                error_manager = get_error_manager()
                error_info = error_manager.handle_error(e, context)
                
                if re_raise or error_info.severity == ErrorSeverity.CRITICAL:
                    raise
                
                return default_return
        
        return wrapper
    return decorator

# 上下文管理器 - 错误处理上下文
class error_context:
    """错误处理上下文管理器"""
    
    def __init__(self, operation: str, **context):
        self.operation = operation
        self.context = context
        self.error_manager = get_error_manager()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val is not None:
            self.context['operation'] = self.operation
            error_info = self.error_manager.handle_error(exc_val, self.context)
            
            # 只有可恢复的错误才抑制异常
            if error_info.recoverable and error_info.severity != ErrorSeverity.CRITICAL:
                return True  # 抑制异常
        
        return False  # 不抑制异常 