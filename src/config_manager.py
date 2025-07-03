#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理器 - 遵循SOLID原则的配置管理
确保配置访问有默认值处理，避免配置依赖问题
"""

import os
import json
import logging
from typing import Any, Dict, List, Optional, Type, Union, get_type_hints
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)

# Interface Segregation Principle - 分离配置接口
class IConfigProvider(ABC):
    """配置提供者接口"""
    
    @abstractmethod
    def get_value(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        pass
    
    @abstractmethod
    def set_value(self, key: str, value: Any) -> None:
        """设置配置值"""
        pass
    
    @abstractmethod
    def has_key(self, key: str) -> bool:
        """检查是否存在配置项"""
        pass

class IConfigValidator(ABC):
    """配置验证器接口"""
    
    @abstractmethod
    def validate(self, key: str, value: Any) -> bool:
        """验证配置值"""
        pass

# Single Responsibility Principle - 配置数据类
@dataclass
class ConfigItem:
    """配置项数据类"""
    key: str
    value: Any
    default_value: Any
    value_type: Type
    required: bool = False
    description: str = ""
    validator: Optional[IConfigValidator] = None
    
    def get_safe_value(self) -> Any:
        """安全获取配置值"""
        if self.value is not None:
            return self.value
        elif self.default_value is not None:
            return self.default_value
        elif self.required:
            raise ValueError(f"必需的配置项 {self.key} 未设置且无默认值")
        else:
            return None

# Single Responsibility Principle - 环境变量配置提供者
class EnvironmentConfigProvider(IConfigProvider):
    """环境变量配置提供者 - 单一职责：从环境变量获取配置"""
    
    def __init__(self, prefix: str = ""):
        self.prefix = prefix
    
    def get_value(self, key: str, default: Any = None) -> Any:
        """从环境变量获取配置值"""
        env_key = f"{self.prefix}{key}" if self.prefix else key
        value = os.environ.get(env_key)
        
        if value is None:
            return default
        
        # 尝试解析JSON格式的值
        if value.startswith(('[', '{')):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass
        
        # 处理布尔值
        if value.lower() in ('true', 'false'):
            return value.lower() == 'true'
        
        # 尝试转换为数字
        try:
            if '.' in value:
                return float(value)
            return int(value)
        except ValueError:
            pass
        
        return value
    
    def set_value(self, key: str, value: Any) -> None:
        """设置环境变量"""
        env_key = f"{self.prefix}{key}" if self.prefix else key
        if isinstance(value, (dict, list)):
            os.environ[env_key] = json.dumps(value)
        else:
            os.environ[env_key] = str(value)
    
    def has_key(self, key: str) -> bool:
        """检查环境变量是否存在"""
        env_key = f"{self.prefix}{key}" if self.prefix else key
        return env_key in os.environ

class FileConfigProvider(IConfigProvider):
    """文件配置提供者 - 单一职责：从文件获取配置"""
    
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self._config_data: Dict[str, Any] = {}
        self._load_config()
    
    def _load_config(self) -> None:
        """加载配置文件"""
        if not self.file_path.exists():
            logger.warning(f"配置文件不存在: {self.file_path}")
            return
        
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                if self.file_path.suffix == '.json':
                    self._config_data = json.load(f)
                elif self.file_path.suffix in ('.env', '.txt'):
                    self._load_env_format(f)
                else:
                    logger.warning(f"不支持的配置文件格式: {self.file_path.suffix}")
        except Exception as e:
            logger.error(f"加载配置文件失败 {self.file_path}: {e}")
    
    def _load_env_format(self, file_obj) -> None:
        """加载.env格式的配置文件"""
        for line in file_obj:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                
                # 尝试解析JSON
                if value.startswith(('[', '{')):
                    try:
                        value = json.loads(value)
                    except json.JSONDecodeError:
                        pass
                
                self._config_data[key] = value
    
    def get_value(self, key: str, default: Any = None) -> Any:
        """从文件配置获取值"""
        return self._config_data.get(key, default)
    
    def set_value(self, key: str, value: Any) -> None:
        """设置配置值（内存中）"""
        self._config_data[key] = value
    
    def has_key(self, key: str) -> bool:
        """检查配置项是否存在"""
        return key in self._config_data
    
    def save_config(self) -> None:
        """保存配置到文件"""
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.file_path, 'w', encoding='utf-8') as f:
                if self.file_path.suffix == '.json':
                    json.dump(self._config_data, f, indent=2, ensure_ascii=False)
                else:
                    for key, value in self._config_data.items():
                        if isinstance(value, (dict, list)):
                            value = json.dumps(value)
                        f.write(f"{key}={value}\n")
        except Exception as e:
            logger.error(f"保存配置文件失败 {self.file_path}: {e}")

# Open/Closed Principle - 可扩展的配置验证器
class URLListValidator(IConfigValidator):
    """URL列表验证器"""
    
    def validate(self, key: str, value: Any) -> bool:
        """验证URL列表"""
        if not isinstance(value, list):
            return False
        
        for url in value:
            if not isinstance(url, str) or not url.startswith(('http://', 'https://')):
                return False
        
        return True

class PositiveIntValidator(IConfigValidator):
    """正整数验证器"""
    
    def validate(self, key: str, value: Any) -> bool:
        """验证正整数"""
        try:
            return isinstance(value, int) and value > 0
        except (ValueError, TypeError):
            return False

class RangeValidator(IConfigValidator):
    """范围验证器"""
    
    def __init__(self, min_val: float, max_val: float):
        self.min_val = min_val
        self.max_val = max_val
    
    def validate(self, key: str, value: Any) -> bool:
        """验证数值范围"""
        try:
            num_val = float(value)
            return self.min_val <= num_val <= self.max_val
        except (ValueError, TypeError):
            return False

# Dependency Inversion Principle - 依赖抽象的配置管理器
class ConfigManager:
    """配置管理器 - 协调多个配置提供者"""
    
    def __init__(self):
        self._providers: List[IConfigProvider] = []
        self._config_items: Dict[str, ConfigItem] = {}
        self._cache: Dict[str, Any] = {}
        self._cache_enabled = True
        
        # 注册默认配置项
        self._register_default_configs()
    
    def _register_default_configs(self) -> None:
        """注册默认配置项"""
        default_configs = [
            ConfigItem(
                key="KEYWORDS_API_URLS",
                value=None,
                default_value=["https://k3.seokey.vip/api/keywords?keyword="],
                value_type=list,
                required=True,
                description="关键词API URL列表",
                validator=URLListValidator()
            ),
            ConfigItem(
                key="BATCH_SIZE",
                value=None,
                default_value=5,
                value_type=int,
                description="批处理大小",
                validator=RangeValidator(1, 50)
            ),
            ConfigItem(
                key="MAX_WORKERS",
                value=None,
                default_value=2,
                value_type=int,
                description="最大工作线程数",
                validator=RangeValidator(1, 10)
            ),
            ConfigItem(
                key="REQUEST_TIMEOUT",
                value=None,
                default_value=30,
                value_type=int,
                description="请求超时时间（秒）",
                validator=RangeValidator(5, 300)
            ),
            ConfigItem(
                key="MAX_RETRIES",
                value=None,
                default_value=3,
                value_type=int,
                description="最大重试次数",
                validator=RangeValidator(0, 10)
            ),
            ConfigItem(
                key="HEALTH_CHECK_INTERVAL",
                value=None,
                default_value=60,
                value_type=int,
                description="健康检查间隔（秒）",
                validator=RangeValidator(10, 3600)
            ),
            ConfigItem(
                key="ENCRYPTION_KEY",
                value=None,
                default_value="default_encryption_key_change_me",
                value_type=str,
                required=True,
                description="加密密钥"
            ),
            ConfigItem(
                key="DATA_FILE_PATH",
                value=None,
                default_value="previous_data.json",
                value_type=str,
                description="数据文件路径"
            ),
            ConfigItem(
                key="LOG_LEVEL",
                value=None,
                default_value="INFO",
                value_type=str,
                description="日志级别"
            ),
            ConfigItem(
                key="ENABLE_PARALLEL_PROCESSING",
                value=None,
                default_value=True,
                value_type=bool,
                description="启用并行处理"
            )
        ]
        
        for config in default_configs:
            self._config_items[config.key] = config
    
    def add_provider(self, provider: IConfigProvider) -> None:
        """添加配置提供者"""
        self._providers.append(provider)
        self._clear_cache()
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        # 检查缓存
        if self._cache_enabled and key in self._cache:
            return self._cache[key]
        
        # 从配置项获取
        if key in self._config_items:
            config_item = self._config_items[key]
            
            # 尝试从各个提供者获取
            for provider in self._providers:
                if provider.has_key(key):
                    value = provider.get_value(key)
                    if value is not None:
                        # 验证配置值
                        if config_item.validator and not config_item.validator.validate(key, value):
                            logger.warning(f"配置项 {key} 验证失败，使用默认值")
                            value = config_item.default_value
                        
                        config_item.value = value
                        if self._cache_enabled:
                            self._cache[key] = value
                        return value
            
            # 使用默认值
            safe_value = config_item.get_safe_value()
            if self._cache_enabled:
                self._cache[key] = safe_value
            return safe_value
        
        # 如果没有注册的配置项，直接从提供者获取
        for provider in self._providers:
            if provider.has_key(key):
                value = provider.get_value(key, default)
                if self._cache_enabled:
                    self._cache[key] = value
                return value
        
        return default
    
    def set_config(self, key: str, value: Any) -> None:
        """设置配置值"""
        if key in self._config_items:
            config_item = self._config_items[key]
            
            # 验证配置值
            if config_item.validator and not config_item.validator.validate(key, value):
                raise ValueError(f"配置项 {key} 验证失败: {value}")
            
            config_item.value = value
        
        # 设置到第一个提供者
        if self._providers:
            self._providers[0].set_value(key, value)
        
        # 更新缓存
        if self._cache_enabled:
            self._cache[key] = value
    
    def validate_all_configs(self) -> Dict[str, List[str]]:
        """验证所有配置项"""
        errors = {}
        
        for key, config_item in self._config_items.items():
            item_errors = []
            
            # 检查必需配置项
            if config_item.required:
                value = self.get_config(key)
                if value is None:
                    item_errors.append(f"必需的配置项 {key} 未设置")
            
            # 验证配置值
            if config_item.validator:
                value = self.get_config(key)
                if value is not None and not config_item.validator.validate(key, value):
                    item_errors.append(f"配置项 {key} 验证失败: {value}")
            
            if item_errors:
                errors[key] = item_errors
        
        return errors
    
    def get_config_summary(self) -> Dict[str, Any]:
        """获取配置摘要"""
        summary = {}
        for key, config_item in self._config_items.items():
            value = self.get_config(key)
            # 隐藏敏感信息
            if 'key' in key.lower() or 'password' in key.lower():
                display_value = "***"
            else:
                display_value = value
            
            summary[key] = {
                'value': display_value,
                'default': config_item.default_value,
                'type': config_item.value_type.__name__,
                'required': config_item.required,
                'description': config_item.description
            }
        
        return summary
    
    def _clear_cache(self) -> None:
        """清空缓存"""
        self._cache.clear()
    
    def reload_configs(self) -> None:
        """重新加载配置"""
        self._clear_cache()
        for provider in self._providers:
            if hasattr(provider, '_load_config'):
                provider._load_config()

# 全局配置管理器实例
_config_manager: Optional[ConfigManager] = None

def get_config_manager() -> ConfigManager:
    """获取全局配置管理器实例"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
        
        # 添加默认配置提供者
        _config_manager.add_provider(EnvironmentConfigProvider())
        
        # 如果存在.env文件，添加文件配置提供者
        if Path('.env').exists():
            _config_manager.add_provider(FileConfigProvider('.env'))
    
    return _config_manager

def get_config(key: str, default: Any = None) -> Any:
    """获取配置值的便捷函数"""
    return get_config_manager().get_config(key, default)

def set_config(key: str, value: Any) -> None:
    """设置配置值的便捷函数"""
    get_config_manager().set_config(key, value)

# 类型安全的配置获取函数
def get_string_config(key: str, default: str = "") -> str:
    """获取字符串配置"""
    value = get_config(key, default)
    return str(value) if value is not None else default

def get_int_config(key: str, default: int = 0) -> int:
    """获取整数配置"""
    value = get_config(key, default)
    try:
        return int(value) if value is not None else default
    except (ValueError, TypeError):
        return default

def get_bool_config(key: str, default: bool = False) -> bool:
    """获取布尔配置"""
    value = get_config(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ('true', '1', 'yes', 'on')
    return default

def get_list_config(key: str, default: List[Any] = None) -> List[Any]:
    """获取列表配置"""
    if default is None:
        default = []
    value = get_config(key, default)
    return value if isinstance(value, list) else default 