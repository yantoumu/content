#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
加密模块
处理数据加密和解密
"""

import base64
import binascii
import logging

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad

from src.config import config

# 配置日志
logger = logging.getLogger('content_watcher.encryption')

class Encryptor:
    """处理数据加密和解密的类"""

    def __init__(self):
        """初始化加密器"""
        self.encryption_key = Encryptor._process_encryption_key(config.encryption_key)

        # 验证密钥长度
        if not self.encryption_key or len(self.encryption_key) != 32:
            logger.error("加密密钥无效或不是32字节")
            raise ValueError(f"ENCRYPTION_KEY必须是32字节，当前是{len(self.encryption_key)}字节")

    @staticmethod
    def _process_encryption_key(key: str) -> bytes:
        """处理加密密钥，支持多种格式，确保输出32字节"""
        if not key:
            return b''

        # 尝试将密钥当作十六进制字符串处理
        try:
            if len(key) == 64:  # 32字节的十六进制表示为64个字符
                return binascii.unhexlify(key)
        except binascii.Error:
            pass

        # 尝试将密钥当作Base64编码处理
        try:
            decoded = base64.b64decode(key + '==')  # 添加padding以防格式问题
            if len(decoded) >= 32:  # 如果长度足够，截取前32字节
                return decoded[:32]
            elif len(decoded) < 32:  # 如果长度不足，用零填充
                return decoded + b'\x00' * (32 - len(decoded))
        except (binascii.Error, TypeError, ValueError):
            pass

        # 如果上述方法都失败，处理字符串密钥
        key_bytes = key.encode('utf-8')
        if len(key_bytes) >= 32:
            return key_bytes[:32]  # 截取前32字节
        else:
            return key_bytes + b'\x00' * (32 - len(key_bytes))  # 用零填充到32字节

    def _encrypt_bytes(self, data: bytes) -> bytes:
        """加密二进制数据的内部方法

        Args:
            data: 要加密的二进制数据

        Returns:
            加密后的数据（包含IV）
        """
        iv = get_random_bytes(16)
        cipher = AES.new(self.encryption_key, AES.MODE_CBC, iv)
        padded_data = pad(data, AES.block_size)
        encrypted_data = cipher.encrypt(padded_data)

        # 将IV和加密数据组合在一起
        return iv + encrypted_data

    def _decrypt_bytes(self, encrypted_data: bytes) -> bytes:
        """解密二进制数据的内部方法

        Args:
            encrypted_data: 加密后的二进制数据（包含IV）

        Returns:
            解密后的二进制数据
        """
        # 提取IV和加密数据
        iv = encrypted_data[:16]
        encrypted = encrypted_data[16:]

        cipher = AES.new(self.encryption_key, AES.MODE_CBC, iv)
        decrypted_padded = cipher.decrypt(encrypted)
        return unpad(decrypted_padded, AES.block_size)

    def encrypt_url(self, url: str) -> str:
        """加密URL，返回加密后的URL（包含IV）

        Args:
            url: 要加密的URL字符串

        Returns:
            Base64编码的加密URL
        """
        encrypted_bytes = self._encrypt_bytes(url.encode('utf-8'))
        # 转为Base64编码便于存储
        return base64.b64encode(encrypted_bytes).decode('utf-8')

    def decrypt_url(self, encrypted_data: str) -> str:
        """解密URL

        Args:
            encrypted_data: Base64编码的加密URL

        Returns:
            解密后的URL字符串，失败时返回空字符串
        """
        try:
            # 解码Base64数据
            binary_data = base64.b64decode(encrypted_data)
            decrypted_bytes = self._decrypt_bytes(binary_data)
            return decrypted_bytes.decode('utf-8')
        except (binascii.Error, ValueError, TypeError, IndexError, UnicodeDecodeError) as e:
            logger.error(f"解密URL时出错: {e}")
            return ""

    def encrypt_data(self, data: bytes) -> bytes:
        """加密任意二进制数据

        Args:
            data: 要加密的二进制数据

        Returns:
            加密后的数据（包含IV）
        """
        return self._encrypt_bytes(data)

    def decrypt_data(self, encrypted_data: bytes) -> str:
        """解密二进制数据

        Args:
            encrypted_data: 加密后的二进制数据（包含IV）

        Returns:
            解密后的文本，失败时返回空字符串
        """
        try:
            decrypted_bytes = self._decrypt_bytes(encrypted_data)
            return decrypted_bytes.decode('utf-8')
        except (ValueError, IndexError, UnicodeDecodeError) as e:
            logger.error(f"解密数据时出错: {e}")
            return ""

# 创建全局加密器实例
encryptor = Encryptor()
