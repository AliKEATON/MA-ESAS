"""
爬虫模块初始化
"""

from app.crawlers.base_crawler import BaseCrawler
from app.crawlers.jd_crawler import JDCrawler, JDCrawlerSimple
from app.crawlers.data_cleaner import DataCleaner

__all__ = [
    "BaseCrawler",
    "JDCrawler",
    "JDCrawlerSimple",
    "DataCleaner"
]
