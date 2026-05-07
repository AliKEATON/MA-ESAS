"""为指定商品生成 1000 条分析友好的虚拟评论数据。"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CURRENT_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models import Comment, Product
from app.models.product import ProductStatus
from app.services.vector_store_service import VectorStoreService
from app.utils.logger import logger


TARGET_PRODUCT = {
    "source": "jd",
    "external_product_id": "100044848690",
    "product_url": "https://item.jd.com/100044848690.html",
    "product_name": "Apple iPhone 15 Pro Max",
    "suggested_prompt": "请综合分析这款手机的用户评价，重点关注性能、续航、拍照、发热和价格争议。",
}

COMMENTS_TOTAL = 1000
RANDOM_SEED = 20260507

# 不同维度评论数量不同，且各维度正负比例不同。
DIMENSION_DISTRIBUTION = [
    {"name": "性能", "positive": 150, "negative": 50},
    {"name": "续航", "positive": 115, "negative": 45},
    {"name": "拍照", "positive": 115, "negative": 35},
    {"name": "质量", "positive": 95, "negative": 35},
    {"name": "价格", "positive": 70, "negative": 60},
    {"name": "发热", "positive": 60, "negative": 50},
    {"name": "物流", "positive": 60, "negative": 20},
    {"name": "售后", "positive": 35, "negative": 5},
]

COMMENT_OPENERS = {
    "positive": [
        "用了几天之后整体感觉挺满意的，",
        "这次入手之后体验比预期更好，",
        "实际使用下来确实有惊喜，",
        "作为日常主力机来讲，这次体验挺顺手，",
        "到手之后连续用了几天，感觉比较稳，",
        "结合我自己的使用场景来看，",
    ],
    "negative": [
        "刚开始还挺期待，但实际体验下来有些失望，",
        "用了这一段时间之后，问题还是比较明显，",
        "从日常使用角度看，这次体验不算理想，",
        "本来冲着配置买的，结果有几个点确实让我介意，",
        "到手之后反复用了几天，还是发现了一些短板，",
        "如果按这个价位来要求，下面这些问题还是得说一下，",
    ],
}

USAGE_SCENES = [
    "平时主要拿来刷视频、聊天和拍照",
    "通勤路上用得比较多",
    "我平常会拿它打游戏和拍短视频",
    "工作和日常娱乐都会一起用",
    "周末外出拍照、导航和高频聊天都靠它",
    "平时会装不少 App，也会开很多后台",
    "晚上会拿来追剧和修图",
    "我比较在意长时间重度使用下的表现",
]

POSITIVE_CLOSERS = [
    "综合来看还是挺值得入手的。",
    "整体体验是在线的。",
    "这一点确实让我比较满意。",
    "放在这个档位里表现算稳。",
    "目前看下来没有后悔。",
    "如果需求和我差不多，应该会喜欢这种表现。",
]

NEGATIVE_CLOSERS = [
    "这个问题确实拉低了整体体验。",
    "如果后续能优化，这台机器会更完整。",
    "以这个价位来说，这一点还是挺难接受的。",
    "所以我对这一项的评价不会太高。",
    "短期内这个问题让我有点犹豫要不要继续留着。",
    "希望后面系统或版本更新能把这个点补起来。",
]

TRANSITIONS = [
    "另外，",
    "同时，",
    "不过，",
    "再补充一点，",
    "更关键的是，",
    "从细节上看，",
]

DIMENSION_LIBRARY = {
    "性能": {
        "positive_core": [
            "系统响应很快，切应用和开大程序都比较跟手",
            "游戏帧率稳定，日常高负载也没有明显卡顿",
            "多任务切换很流畅，后台挂着几个应用也不怎么掉",
            "A 系列芯片的性能优势还是很直接，重度使用明显更稳",
            "日常拍照、修图和剪视频的速度都挺痛快",
        ],
        "negative_core": [
            "高负载场景下性能释放没有一直稳定住",
            "连续打游戏一段时间后会感觉帧率起伏明显",
            "后台开多了之后偶尔会出现掉帧和加载变慢",
            "部分大型应用切换时还是会卡一下，不算特别丝滑",
            "宣传上的性能很强，但长时间持续输出没有想象中稳",
        ],
        "positive_detail": [
            "刷网页和切后台几乎没有等待感",
            "应用安装和更新速度挺快",
            "拍完视频后导出速度也很利索",
            "日常办公和娱乐切换起来很顺手",
        ],
        "negative_detail": [
            "长时间运行大游戏后掉帧会更明显",
            "部分场景下温度一上来就会影响流畅度",
            "切相机和大型应用来回跳时会有顿挫感",
            "一边拍视频一边处理图片时偶尔会发懵",
        ],
        "positive_keywords": ["运行速度", "流畅度", "多任务表现", "芯片性能"],
        "negative_keywords": ["掉帧", "卡顿", "性能波动", "持续输出"],
    },
    "续航": {
        "positive_core": [
            "续航表现比我预期更稳，一天下来还有富余",
            "正常强度用一天问题不大，不用中途一直找充电器",
            "待机掉电控制得不错，晚上放着第二天也不会掉太多",
            "外出拍照和导航同时开的时候，电量也比旧机型更耐用",
            "电池健康和续航初期表现都让我比较放心",
        ],
        "negative_core": [
            "续航没有预想中顶，重度用半天多就得补电",
            "高亮度和高刷一起开的时候掉电偏快",
            "打游戏、拍视频这种场景下电量下降比较明显",
            "白天用得频繁一点，下午就得开始焦虑电量了",
            "待机还行，但一到高强度使用就不够从容",
        ],
        "positive_detail": [
            "通勤加办公一天基本够用",
            "拍照和社交软件混用也撑得住",
            "晚上回到家还有电，整体安心感不错",
            "充电频率明显比旧手机低",
        ],
        "negative_detail": [
            "出门拍一天素材就必须带移动电源",
            "高负载下掉电速度看得见",
            "一开热点或者导航时间久了就不太扛得住",
            "充电次数会比预期更频繁",
        ],
        "positive_keywords": ["续航", "待机", "电量控制", "耐用度"],
        "negative_keywords": ["掉电", "补电频率", "续航压力", "电量焦虑"],
    },
    "拍照": {
        "positive_core": [
            "主摄成像稳定，白天和夜景都有比较高的可用率",
            "人像边缘处理自然，肤色也比较讨喜",
            "长焦在日常拍人和拍景时都很实用",
            "色彩风格比较耐看，随手拍出片率很高",
            "视频防抖做得稳，记录日常真的方便",
        ],
        "negative_core": [
            "夜景场景下高光压制还不够稳，有时会翻车",
            "个别情况下成像偏锐，细节看起来有点硬",
            "长焦在暗光环境下不够稳，成功率一般",
            "逆光拍摄时偶尔会出现发灰或偏色",
            "视频切镜头时的观感不算完全顺滑",
        ],
        "positive_detail": [
            "抓拍小孩和宠物成功率挺高",
            "白平衡稳定，照片风格统一",
            "社交平台直出基本不用怎么修",
            "拍夜景灯牌和建筑层次感不错",
        ],
        "negative_detail": [
            "暗光下噪点控制还能更好一些",
            "室内混光时偶尔会偏黄",
            "高倍变焦时细节下降比较明显",
            "有时拍完会想再修一遍颜色",
        ],
        "positive_keywords": ["成像", "夜景", "人像", "视频防抖"],
        "negative_keywords": ["高光压制", "锐化", "偏色", "长焦表现"],
    },
    "质量": {
        "positive_core": [
            "机身做工很扎实，握在手里有旗舰感",
            "边框、按键和转角的细节处理都比较精致",
            "屏幕观感细腻，亮度和色彩都很舒服",
            "整机装配度不错，没有松垮感",
            "拿在手里质感很强，确实有高端机的完成度",
        ],
        "negative_core": [
            "机身比较重，长时间单手用会累",
            "边框容易留指纹，保持清爽要经常擦",
            "裸机手感高级，但也更担心磕碰",
            "镜头模组突出比较明显，平放时多少会晃",
            "外观质感在线，但握持负担也确实存在",
        ],
        "positive_detail": [
            "按键反馈干脆，细节挺讲究",
            "屏幕边缘过渡很自然",
            "整体做工没有让我挑出明显毛病",
            "拿在手里就能感受到用料比较足",
        ],
        "negative_detail": [
            "长时间刷手机压手感偏明显",
            "边框和后盖都比较娇贵",
            "戴壳之后厚重感更突出",
            "镜头区域太大，桌面上用不够稳",
        ],
        "positive_keywords": ["做工", "质感", "屏幕", "装配度"],
        "negative_keywords": ["重量", "指纹", "镜头突出", "握持负担"],
    },
    "价格": {
        "positive_core": [
            "虽然价格不低，但综合体验确实对得起旗舰定位",
            "如果本身就是苹果生态用户，这个投入还算能接受",
            "大促叠补贴之后，整体入手感受会舒服不少",
            "保值率和长期使用价值算是它的一项优势",
            "预算足够的话，一步到位省得后面反复折腾",
        ],
        "negative_core": [
            "价格还是偏高，普通用户下手门槛不低",
            "同样预算可选项很多，性价比不算最突出",
            "升级点有，但和价格涨幅相比还是会犹豫",
            "配件、存储和官方服务叠加起来成本更高",
            "如果只看参数，这个价格确实会让人纠结",
        ],
        "positive_detail": [
            "长期用下来摊平成本还算能理解",
            "以旧换新后压力会小不少",
            "生态体验让价格显得更容易接受",
            "买来做主力机的安心感比较强",
        ],
        "negative_detail": [
            "同容量版本加价太快了",
            "官方配件价格也不便宜",
            "没有活动的时候真的不太想直接下单",
            "高配版本预算压力非常明显",
        ],
        "positive_keywords": ["保值率", "生态价值", "长期使用", "一步到位"],
        "negative_keywords": ["价格门槛", "性价比", "预算压力", "加价"],
    },
    "发热": {
        "positive_core": [
            "日常轻中度使用下温控其实还算稳",
            "普通刷视频和聊天时机身温度控制得不错",
            "拍照和常规应用切换时没有出现特别夸张的发热",
            "和我之前用过的机型比，日常发热算克制",
            "不开高负载应用的时候，温度表现是可以接受的",
        ],
        "negative_core": [
            "高负载时机身发热还是比较明显",
            "长时间游戏之后边框温度会上来得很快",
            "拍视频或者边充边用时发热感会更明显",
            "夏天户外高亮度使用时温度控制一般",
            "性能强是强，但温度压力也确实随之而来",
        ],
        "positive_detail": [
            "普通办公和社交场景基本不会觉得烫",
            "日常刷信息流时握持温度比较舒服",
            "大多数轻负载场景下都挺稳定",
            "常规使用没有影响体验的热感",
        ],
        "negative_detail": [
            "边充电边玩的时候会明显发热",
            "高亮屏幕下外壳温度上升比较快",
            "长时间相机使用时热感偏强",
            "温度上来后会影响持续体验",
        ],
        "positive_keywords": ["温控", "日常发热", "轻负载表现", "稳定性"],
        "negative_keywords": ["高负载发热", "边充边热", "户外高温", "热感明显"],
    },
    "物流": {
        "positive_core": [
            "发货速度很快，下单后很快就收到了",
            "包装保护得不错，外箱和内盒都挺完整",
            "配送时效稳定，整体体验省心",
            "快递员联系及时，签收过程比较顺利",
            "到货速度和包装保护都让我满意",
        ],
        "negative_core": [
            "发货速度一般，等待时间比预期长",
            "外箱有轻微磕碰，开箱时多少有点担心",
            "物流轨迹更新不够及时，中间等得有些焦虑",
            "配送时间和预计有偏差，影响了使用安排",
            "东西没问题，但物流体验确实不算顺滑",
        ],
        "positive_detail": [
            "整体包装层数够，保护得比较稳妥",
            "急着换机时这个时效挺有帮助",
            "签收之后检查下来没有任何损伤",
            "送达前电话确认也比较到位",
        ],
        "negative_detail": [
            "中途运输状态更新太慢",
            "包装角有一点压痕",
            "快递比预计晚了半天到一天",
            "等待过程不太安心",
        ],
        "positive_keywords": ["发货速度", "包装", "配送时效", "签收体验"],
        "negative_keywords": ["延迟", "磕碰", "轨迹更新", "等待焦虑"],
    },
    "售后": {
        "positive_core": [
            "客服回复比较快，咨询流程挺清楚",
            "售后解释到位，沟通体验还不错",
            "遇到问题后能比较快得到反馈",
            "官方渠道售后流程相对规范，用起来安心一些",
            "售后态度比较稳，至少不会踢皮球",
        ],
        "negative_core": [
            "售后流程偏繁琐，来回确认的步骤比较多",
            "高峰期回复速度一般，等待时间偏长",
            "部分问题需要自己先排查很多轮",
            "沟通效率不算高，想快速处理会有点着急",
            "售后不是不能解决，但过程没有那么省心",
        ],
        "positive_detail": [
            "问题描述后基本能得到明确答复",
            "服务口径比较统一",
            "沟通态度比较专业",
            "处理节奏没有明显拖沓",
        ],
        "negative_detail": [
            "反复提交信息有点折腾",
            "问题定位过程偏慢",
            "不同客服说法偶尔不完全一致",
            "想一步解决并不容易",
        ],
        "positive_keywords": ["客服响应", "售后规范", "处理效率", "沟通体验"],
        "negative_keywords": ["流程繁琐", "回复较慢", "反复确认", "沟通成本"],
    },
}


def parse_args() -> argparse.Namespace:
    """解析脚本参数。"""
    parser = argparse.ArgumentParser(description="为指定商品生成 1000 条虚拟分析评论。")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="删除当前商品历史 demo 评论后重新生成。",
    )
    return parser.parse_args()


def get_or_create_target_product(db: Session) -> Product:
    """获取目标商品，不存在时自动创建。"""
    product = db.query(Product).filter(
        Product.source == TARGET_PRODUCT["source"],
        Product.external_product_id == TARGET_PRODUCT["external_product_id"],
    ).first()
    if product is None:
        product = Product(
            source=TARGET_PRODUCT["source"],
            external_product_id=TARGET_PRODUCT["external_product_id"],
            product_url=TARGET_PRODUCT["product_url"],
            product_name=TARGET_PRODUCT["product_name"],
            crawl_status=ProductStatus.COMPLETED,
        )
        db.add(product)
        db.flush()
        logger.info(
            "Created demo product: product_id={} external_product_id={}",
            product.id,
            product.external_product_id,
        )
    else:
        product.product_url = TARGET_PRODUCT["product_url"]
        product.product_name = TARGET_PRODUCT["product_name"]
        product.crawl_status = ProductStatus.COMPLETED
        logger.info(
            "Reusing demo product: product_id={} external_product_id={}",
            product.id,
            product.external_product_id,
        )
    return product


def reset_demo_comments(db: Session, product: Product) -> int:
    """删除当前商品下旧的 demo 评论与向量。"""
    VectorStoreService.delete_product_comments(product.id)
    deleted_count = (
        db.query(Comment)
        .filter(
            Comment.product_id == product.id,
            Comment.source_comment_id.like("demo-analysis-%"),
        )
        .delete(synchronize_session=False)
    )
    logger.info(
        "Reset demo comments: product_id={} deleted_count={}",
        product.id,
        deleted_count,
    )
    return int(deleted_count or 0)


def _pick_score(is_positive: bool, rng: random.Random) -> int:
    """根据正负面随机生成评分。"""
    if is_positive:
        return rng.choices([5, 4], weights=[0.7, 0.3], k=1)[0]
    return rng.choices([1, 2, 3], weights=[0.25, 0.55, 0.2], k=1)[0]


def _build_comment_text(dimension_name: str, is_positive: bool, rng: random.Random) -> str:
    """随机拼装更丰富的评论文本。"""
    library = DIMENSION_LIBRARY[dimension_name]
    tone = "positive" if is_positive else "negative"
    opener = rng.choice(COMMENT_OPENERS[tone])
    usage_scene = rng.choice(USAGE_SCENES)
    core = rng.choice(library[f"{tone}_core"])
    detail = rng.choice(library[f"{tone}_detail"])
    keyword = rng.choice(library[f"{tone}_keywords"])
    transition = rng.choice(TRANSITIONS)
    closer = rng.choice(POSITIVE_CLOSERS if is_positive else NEGATIVE_CLOSERS)

    extra_fragments = [
        f"我这段时间{usage_scene}，最直接感受到的是{keyword}这一块。",
        f"{transition}{core}。",
        f"{detail}。",
    ]
    rng.shuffle(extra_fragments)

    sentence_pool = [
        opener + extra_fragments[0],
        extra_fragments[1],
        extra_fragments[2],
        closer,
    ]

    # 随机决定评论长度，避免全部都是统一模板长度。
    target_sentence_count = rng.choices([2, 3, 4], weights=[0.2, 0.45, 0.35], k=1)[0]
    selected = sentence_pool[:target_sentence_count]
    return "".join(selected)


def build_demo_comments() -> list[dict]:
    """构造 1000 条多维度、非均匀分布的虚拟评论。"""
    rng = random.Random(RANDOM_SEED)
    comments: list[dict] = []
    base_time = datetime.now(timezone.utc) - timedelta(days=180)
    comment_index = 0

    total_count = sum(item["positive"] + item["negative"] for item in DIMENSION_DISTRIBUTION)
    if total_count != COMMENTS_TOTAL:
        raise ValueError(f"维度分布总数不等于 {COMMENTS_TOTAL}: {total_count}")

    for distribution in DIMENSION_DISTRIBUTION:
        dimension_name = distribution["name"]
        for is_positive, count in ((True, distribution["positive"]), (False, distribution["negative"])):
            for _ in range(count):
                comment_index += 1
                score = _pick_score(is_positive=is_positive, rng=rng)
                comment_time = base_time + timedelta(
                    days=rng.randint(0, 179),
                    hours=rng.randint(0, 23),
                    minutes=rng.randint(0, 59),
                    seconds=rng.randint(0, 59),
                )
                comments.append(
                    {
                        "source_comment_id": (
                            f"demo-analysis-{TARGET_PRODUCT['external_product_id']}-{comment_index:04d}"
                        ),
                        "dimension": dimension_name,
                        "score": score,
                        "content": _build_comment_text(
                            dimension_name=dimension_name,
                            is_positive=is_positive,
                            rng=rng,
                        ),
                        "comment_time": comment_time,
                    }
                )

    rng.shuffle(comments)
    return comments


def upsert_demo_comments(db: Session, product: Product) -> tuple[int, int]:
    """写入或更新 demo 评论。"""
    created_count = 0
    updated_count = 0
    demo_comments = build_demo_comments()

    for item in demo_comments:
        comment = db.query(Comment).filter(
            Comment.product_id == product.id,
            Comment.source_comment_id == item["source_comment_id"],
        ).first()

        if comment is None:
            comment = Comment(
                product_id=product.id,
                source_comment_id=item["source_comment_id"],
                content=item["content"],
                score=item["score"],
                dimension=item["dimension"],
                dimension_score=item["score"],
                comment_time=item["comment_time"],
            )
            db.add(comment)
            created_count += 1
        else:
            comment.content = item["content"]
            comment.score = item["score"]
            comment.dimension = item["dimension"]
            comment.dimension_score = item["score"]
            comment.comment_time = item["comment_time"]
            updated_count += 1

    logger.info(
        "Upserted demo comments: product_id={} created_count={} updated_count={}",
        product.id,
        created_count,
        updated_count,
    )
    return created_count, updated_count


def refresh_product_snapshot(db: Session, product: Product) -> None:
    """刷新商品抓取状态和评论统计。"""
    db.flush()
    product.comment_count = db.query(Comment).filter(Comment.product_id == product.id).count()
    product.last_crawled_at = datetime.now(timezone.utc)
    product.last_crawl_error = None
    product.crawl_status = ProductStatus.COMPLETED
    logger.info(
        "Refreshed demo product snapshot: product_id={} comment_count={}",
        product.id,
        product.comment_count,
    )


def print_distribution_summary() -> None:
    """输出维度分布摘要，便于验证数据设计。"""
    print("评论维度分布规划：")
    for distribution in DIMENSION_DISTRIBUTION:
        total = distribution["positive"] + distribution["negative"]
        print(
            f"  - {distribution['name']}: 总数={total} 好评={distribution['positive']} 差评={distribution['negative']}"
        )


def seed_demo_analysis_data(reset: bool) -> None:
    """执行单商品 demo 评论写入。"""
    db = SessionLocal()
    try:
        product = get_or_create_target_product(db)
        deleted_count = reset_demo_comments(db, product) if reset else 0
        created_count, updated_count = upsert_demo_comments(db, product)
        refresh_product_snapshot(db, product)
        vectorized_count = VectorStoreService.upsert_product_comments(db, product.id)
        db.commit()
        db.refresh(product)

        print(f"Demo product ready: {product.product_name}")
        print(f"  Product URL: {product.product_url}")
        print(f"  Product ID: {product.external_product_id}")
        print(f"  Total comments: {product.comment_count}")
        print(f"  Created comments: {created_count}")
        print(f"  Updated comments: {updated_count}")
        print(f"  Deleted comments: {deleted_count}")
        print(f"  Vectorized comments: {vectorized_count}")
        print(f"  Suggested prompt: {TARGET_PRODUCT['suggested_prompt']}")
        print(f"  Expected comments total: {COMMENTS_TOTAL}")
        print_distribution_summary()
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to seed demo analysis data: {}", exc)
        raise
    finally:
        db.close()


def main() -> None:
    """脚本入口。"""
    args = parse_args()
    seed_demo_analysis_data(reset=args.reset)


if __name__ == "__main__":
    main()
