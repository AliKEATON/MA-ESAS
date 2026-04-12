"""
数据清洗模块
处理爬虫数据的验证和清洗
"""

import re
from typing import Dict, Any, Optional, List
from loguru import logger


class DataCleaner:
    """数据清洗工具"""

    # 维度关键词映射
    DIMENSION_KEYWORDS = {
        "物流": ["物流", "快递", "配送", "发货", "包装"],
        "质量": ["质量", "质地", "做工", "材质", "耐用"],
        "价格": ["价格", "便宜", "贵", "划算", "值"],
        "服务": ["服务", "售后", "客服", "退货", "换货"]
    }

    @staticmethod
    def clean_text(text: str) -> str:
        """
        清洗文本
        - 移除特殊字符
        - 移除多余空格
        - 转换为小写
        """
        if not text:
            return ""
        
        # 移除特殊字符（保留中文、英文、数字、标点）
        text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s，。！？；：\'"，。！？；：]', '', text)
        
        # 移除多余空格
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text

    @staticmethod
    def extract_score(score_data: Any) -> Optional[int]:
        """
        提取评分
        支持多种格式：int, str, float
        """
        try:
            if isinstance(score_data, int):
                return score_data
            elif isinstance(score_data, str):
                # 提取数字
                match = re.search(r'\d+', score_data)
                if match:
                    return int(match.group())
            elif isinstance(score_data, float):
                return int(score_data)
        except Exception as e:
            logger.warning(f"Failed to extract score: {str(e)}")
        
        return None

    @staticmethod
    def detect_dimension(text: str) -> Optional[str]:
        """
        检测评论的维度
        基于关键词匹配
        """
        if not text:
            return None
        
        text_lower = text.lower()
        
        for dimension, keywords in DataCleaner.DIMENSION_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return dimension
        
        return None

    @staticmethod
    def validate_comment(comment: Dict[str, Any]) -> bool:
        """
        验证评论数据的完整性
        """
        required_fields = ["content", "score"]
        
        for field in required_fields:
            if field not in comment or not comment[field]:
                return False
        
        # 验证评分范围
        score = comment.get("score")
        if not isinstance(score, int) or score < 1 or score > 5:
            return False
        
        # 验证内容长度
        content = comment.get("content", "")
        if len(content) < 2 or len(content) > 5000:
            return False
        
        return True

    @staticmethod
    def clean_comment(comment: Dict[str, Any]) -> Dict[str, Any]:
        """
        清洗单条评论
        
        Args:
            comment: 原始评论数据
            
        Returns:
            清洗后的评论数据
        """
        try:
            # 清洗文本
            content = DataCleaner.clean_text(comment.get("content", ""))
            
            # 提取评分
            score = DataCleaner.extract_score(comment.get("score"))
            
            # 检测维度
            dimension = DataCleaner.detect_dimension(content)
            
            # 提取维度评分（如果有）
            dimension_score = None
            if "dimension_score" in comment:
                dimension_score = DataCleaner.extract_score(comment.get("dimension_score"))
            
            cleaned = {
                "content": content,
                "score": score,
                "dimension": dimension,
                "dimension_score": dimension_score,
                "comment_time": comment.get("comment_time"),
                "source_comment_id": comment.get("source_comment_id")
            }
            
            # 验证清洗后的数据
            if not DataCleaner.validate_comment(cleaned):
                logger.warning(f"Comment validation failed: {cleaned}")
                return None
            
            return cleaned
            
        except Exception as e:
            logger.error(f"Failed to clean comment: {str(e)}")
            return None

    @staticmethod
    def clean_comments(comments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        批量清洗评论
        """
        cleaned_comments = []
        
        for comment in comments:
            cleaned = DataCleaner.clean_comment(comment)
            if cleaned:
                cleaned_comments.append(cleaned)
        
        logger.info(f"Cleaned {len(cleaned_comments)} out of {len(comments)} comments")
        return cleaned_comments
