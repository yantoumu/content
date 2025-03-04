#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试网站更新检测逻辑
这个脚本模拟网站内容更新，测试更新检测逻辑是否正确
"""

import os
import json
import logging
import datetime
import hashlib
import base64
import tempfile
import shutil

from typing import Dict, List, Tuple, Optional
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from Crypto.Random import get_random_bytes

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('test_detection')

class UpdateDetectionTester:
    """测试更新检测逻辑"""
    
    def __init__(self):
        """初始化测试环境"""
        # 创建临时目录
        self.temp_dir = tempfile.mkdtemp()
        self.data_file = os.path.join(self.temp_dir, 'test_data.json')
        
        # 生成加密密钥
        self.encryption_key = get_random_bytes(32)
        
        # 初始站点数据
        self.site_id = "test_site"
        self.previous_data = {}
        
        logger.info(f"测试环境初始化完成，临时目录: {self.temp_dir}")
    
    def cleanup(self):
        """清理测试环境"""
        shutil.rmtree(self.temp_dir)
        logger.info("测试环境已清理")
    
    def _encrypt_url(self, url: str) -> str:
        """加密URL，返回加密后的URL（包含IV）"""
        iv = get_random_bytes(16)
        cipher = AES.new(self.encryption_key, AES.MODE_CBC, iv)
        padded_data = pad(url.encode('utf-8'), AES.block_size)
        encrypted_data = cipher.encrypt(padded_data)
        
        # 将IV和加密数据组合在一起
        combined = iv + encrypted_data
        # 转为Base64编码便于存储
        return base64.b64encode(combined).decode('utf-8')
    
    def _decrypt_url(self, encrypted_data: str) -> str:
        """解密URL"""
        try:
            # 解码Base64数据
            combined = base64.b64decode(encrypted_data)
            
            # 提取IV和加密数据
            iv = combined[:16]
            encrypted = combined[16:]
            
            cipher = AES.new(self.encryption_key, AES.MODE_CBC, iv)
            decrypted_padded = cipher.decrypt(encrypted)
            decrypted_data = unpad(decrypted_padded, AES.block_size)
            
            return decrypted_data.decode('utf-8')
        except Exception as e:
            logger.error(f"解密URL时出错: {e}")
            return ""
    
    def _is_updated_today(self, lastmod: Optional[str]) -> bool:
        """检查lastmod是否是今天的日期"""
        if not lastmod:
            return False
            
        try:
            # 解析ISO格式的日期
            lastmod_date = datetime.datetime.fromisoformat(lastmod.replace('Z', '+00:00'))
            today = datetime.datetime.now(datetime.timezone.utc).date()
            return lastmod_date.date() == today
        except Exception as e:
            logger.error(f"解析日期时出错: {lastmod}, {e}")
            return False
    
    def save_previous_data(self, urls_with_lastmod: Dict[str, Optional[str]]):
        """保存URL数据作为历史数据"""
        encrypted_data = []
        
        for url, lastmod in urls_with_lastmod.items():
            encrypted_url = self._encrypt_url(url)
            encrypted_data.append({
                'encrypted_url': encrypted_url,
                'lastmod': lastmod
            })
        
        self.previous_data = {self.site_id: encrypted_data}
        
        # 保存到文件
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump({'sites': self.previous_data}, f, ensure_ascii=False, indent=2)
        
        logger.info(f"已保存 {len(urls_with_lastmod)} 个URL作为历史数据")
    
    def detect_updates(self, current_urls_with_lastmod: Dict[str, Optional[str]]) -> List[str]:
        """检测更新的URL"""
        # 加载历史数据
        previous_urls = {}
        if self.site_id in self.previous_data:
            for item in self.previous_data[self.site_id]:
                if 'encrypted_url' in item:
                    decrypted_url = self._decrypt_url(item['encrypted_url'])
                    if decrypted_url:
                        previous_urls[decrypted_url] = item.get('lastmod')
        
        # 检测更新
        updated_urls = []
        
        for url, lastmod in current_urls_with_lastmod.items():
            # 检查URL是否为新URL或今天更新的URL
            is_new = url not in previous_urls
            
            # 对于已存在的URL，检查lastmod是否更新
            is_updated = False
            if not is_new and lastmod:
                previous_lastmod = previous_urls.get(url)
                is_updated = previous_lastmod != lastmod and self._is_updated_today(lastmod)
            
            # 新URL或今天更新的URL都被视为"今天的更新"
            if is_new or is_updated:
                updated_urls.append(url)
                # 记录检测到更新的原因
                if is_new:
                    logger.info(f"检测到新URL: {url}")
                else:
                    logger.info(f"检测到URL更新: {url}, 前一个lastmod: {previous_urls.get(url)}, 新lastmod: {lastmod}")
        
        logger.info(f"共检测到 {len(updated_urls)} 个更新")
        return updated_urls

def get_iso_date(days_ago: int = 0) -> str:
    """获取ISO格式的日期字符串"""
    date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_ago)
    return date.isoformat()

def run_test_case(name: str, previous_data: Dict[str, Optional[str]], current_data: Dict[str, Optional[str]], expected_updates: int):
    """运行测试用例"""
    logger.info(f"========== 开始测试: {name} ==========")
    
    tester = UpdateDetectionTester()
    try:
        # 保存历史数据
        tester.save_previous_data(previous_data)
        
        # 检测更新
        updated_urls = tester.detect_updates(current_data)
        
        # 验证结果
        if len(updated_urls) == expected_updates:
            logger.info(f"✅ 测试通过: 期望检测到 {expected_updates} 个更新，实际检测到 {len(updated_urls)} 个")
        else:
            logger.error(f"❌ 测试失败: 期望检测到 {expected_updates} 个更新，实际检测到 {len(updated_urls)} 个")
            logger.error(f"检测到的更新: {updated_urls}")
    finally:
        tester.cleanup()

def main():
    """运行所有测试用例"""
    # 今天和昨天的ISO日期
    today = get_iso_date()
    yesterday = get_iso_date(1)
    
    # 测试用例1: 全新URL，无lastmod
    previous_data1 = {
        "https://example.com/page1": None,
        "https://example.com/page2": None
    }
    current_data1 = {
        "https://example.com/page1": None,
        "https://example.com/page2": None,
        "https://example.com/page3": None  # 新URL，无lastmod
    }
    run_test_case("全新URL无lastmod", previous_data1, current_data1, 1)
    
    # 测试用例2: 全新URL，有lastmod（今天）
    current_data2 = {
        "https://example.com/page1": None,
        "https://example.com/page2": None,
        "https://example.com/page4": today  # 新URL，今天的lastmod
    }
    run_test_case("全新URL有今天的lastmod", previous_data1, current_data2, 1)
    
    # 测试用例3: 全新URL，有lastmod（昨天）
    current_data3 = {
        "https://example.com/page1": None,
        "https://example.com/page2": None,
        "https://example.com/page5": yesterday  # 新URL，昨天的lastmod
    }
    run_test_case("全新URL有昨天的lastmod", previous_data1, current_data3, 1)
    
    # 测试用例4: 现有URL，lastmod从无到有（今天）
    previous_data4 = {
        "https://example.com/page1": None
    }
    current_data4 = {
        "https://example.com/page1": today  # 现有URL，lastmod从无到今天
    }
    run_test_case("现有URL的lastmod从无到今天", previous_data4, current_data4, 1)
    
    # 测试用例5: 现有URL，lastmod从无到有（昨天）
    current_data5 = {
        "https://example.com/page1": yesterday  # 现有URL，lastmod从无到昨天
    }
    run_test_case("现有URL的lastmod从无到昨天", previous_data4, current_data5, 0)
    
    # 测试用例6: 现有URL，lastmod从昨天变成今天
    previous_data6 = {
        "https://example.com/page1": yesterday
    }
    current_data6 = {
        "https://example.com/page1": today  # 现有URL，lastmod从昨天变成今天
    }
    run_test_case("现有URL的lastmod从昨天变成今天", previous_data6, current_data6, 1)
    
    # 测试用例7: 现有URL，lastmod从今天变成另一个今天的时间
    today_earlier = datetime.datetime.now(datetime.timezone.utc).replace(hour=8, minute=0, second=0).isoformat()
    today_later = datetime.datetime.now(datetime.timezone.utc).replace(hour=15, minute=0, second=0).isoformat()
    
    previous_data7 = {
        "https://example.com/page1": today_earlier
    }
    current_data7 = {
        "https://example.com/page1": today_later  # 现有URL，lastmod从今天早些时候变成今天晚些时候
    }
    run_test_case("现有URL的lastmod在今天内更新", previous_data7, current_data7, 1)
    
    logger.info("所有测试完成")

if __name__ == "__main__":
    main() 