# authomatical\modules\wordpress_steps.py
from enum import Enum

class WordPressSteps(Enum):
    BUILD_ARTICLE = "build_article"
    STORE_TEMP = "store_temp"
    GENERATE_IMAGE = "generate_image"
    COMBINE_HTML = "combine_html"
    CREATE_POST = "create_post"
    UPLOAD_MEDIA = "upload_media"
    CLEANUP = "cleanup"
    ACKNOWLEDGE = "acknowledge"
