"""
链接提取模块
从用户提问中自动提取商品链接
"""

import re
from typing import Optional, List
from loguru import logger


class LinkExtractor:
    """链接提取工具"""

    # 支持的电商平台正则表达式
    PATTERNS = {
        "jd": r"https?://(?:item\.)?jd\.com/(\d+)\.html",
        "taobao": r"https?://(?:item\.)?taobao\.com/(?:item\.htm\?id=|auction/auction\.jhtml\?item_id=)(\d+)",
        "tmall": r"https?://(?:detail\.)?tmall\.com/item\.htm\?id=(\d+)",
        "amazon": r"https?://(?:www\.)?amazon\.cn/(?:dp|gp/product)/([A-Z0-9]+)",
    }

    @staticmethod
    def extract_urls(text: str) -> List[str]:
        """
        从文本中提取所有 URL
        
        Args:
            text: 输入文本
            
        Returns:
            URL 列表
        """
        # 通用 URL 正则
        url_pattern = r"https?://[^\s]+"
        urls = re.findall(url_pattern, text)
        return urls

    @staticmethod
    def identify_platform(url: str) -> Optional[str]:
        """
        识别 URL 所属的电商平台
        
        Args:
            url: URL
            
        Returns:
            平台名称（jd/taobao/tmall/amazon）或 None
        """
        for platform, pattern in LinkExtractor.PATTERNS.items():
            if re.search(pattern, url):
                return platform
        return None

    @staticmethod
    def extract_product_id(url: str) -> Optional[str]:
        """
        从 URL 提取商品 ID
        
        Args:
            url: URL
            
        Returns:
            商品 ID 或 None
        """
        for platform, pattern in LinkExtractor.PATTERNS.items():
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def extract_from_text(text: str) -> Optional[dict]:
        """
        从文本中提取第一个商品链接信息
        
        Args:
            text: 输入文本
            
        Returns:
            包含 url、platform、product_id 的字典，或 None
        """
        try:
            urls = LinkExtractor.extract_urls(text)
            
            if not urls:
                logger.debug("No URLs found in text")
                return None
            
            # 处理第一个 URL
            url = urls[0]
            platform = LinkExtractor.identify_platform(url)
            
            if not platform:
                logger.warning(f"Unsupported platform: {url}")
                return None
            
            product_id = LinkExtractor.extract_product_id(url)
            
            if not product_id:
                logger.warning(f"Failed to extract product ID from: {url}")
                return None
            
            logger.info(f"Extracted: platform={platform}, product_id={product_id}")
            
            return {
                "url": url,
                "platform": platform,
                "product_id": product_id
            }
            
        except Exception as e:
            logger.error(f"Failed to extract link: {str(e)}")
            return None

    @staticmethod
    def extract_all_from_text(text: str) -> List[dict]:
        """
        从文本中提取所有商品链接信息
        
        Args:
            text: 输入文本
            
        Returns:
            包含链接信息的字典列表
        """
        try:
            urls = LinkExtractor.extract_urls(text)
            results = []
            
            for url in urls:
                platform = LinkExtractor.identify_platform(url)
                
                if not platform:
                    logger.warning(f"Unsupported platform: {url}")
                    continue
                
                product_id = LinkExtractor.extract_product_id(url)
                
                if not product_id:
                    logger.warning(f"Failed to extract product ID from: {url}")
                    continue
                
                results.append({
                    "url": url,
                    "platform": platform,
                    "product_id": product_id
                })
            
            logger.info(f"Extracted {len(results)} links from text")
            return results
            
        except Exception as e:
            logger.error(f"Failed to extract links: {str(e)}")
            return []
