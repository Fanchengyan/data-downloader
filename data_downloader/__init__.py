from . import downloader, parse_urls, services, utils
import logging

logger = logging.getLogger("data_downloader")
logger.setLevel(logging.DEBUG)
logger.propagate = True  # 确保日志向上传播
logger.addHandler(logging.NullHandler())

