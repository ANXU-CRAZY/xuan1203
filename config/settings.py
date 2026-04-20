import os
import platform  # 引入系统判断模块
from pathlib import Path

# 构建路径
BASE_DIR = Path(__file__).resolve().parent.parent

# 安全密钥 (开发环境)
SECRET_KEY = 'django-insecure-custom-key-for-xuan'
DEBUG = True
ALLOWED_HOSTS = ['*']

# === 1. 应用注册 (SimpleUI 必须在最前) ===
INSTALLED_APPS = [
    'simpleui',  # 后台美化主题 (必须是第一行)
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # GIS 与 API 核心库
    'django.contrib.gis',  # GeoDjango 核心
    'rest_framework',  # API 接口框架
    'rest_framework_gis',
    'rest_framework.authtoken',
    'import_export',  # 导入导出支持
    'leaflet',  # GIS 后台地图控件
    'corsheaders',
    'app_monitor',  # 我们的监控 App
    'bird_recognition',  # 新增
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',  # 汉化关键
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# === 2. PostGIS 数据库配置 ===
DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': 'Yellow River',
        'USER': 'postgres',
        'PASSWORD': '111111',  # 【注意】确保你服务器上的数据库密码也是这个，否则需要修改
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

# === 3. 环境变量配置 (这里是修改的核心！) ===
# 逻辑：代码会自动检测：如果是 Windows，就用你的路径；如果是 Linux，就自动使用系统默认路径。

if platform.system() == 'Windows':
    # ----- Windows 本地开发环境 -----
    OSGEO4W_ROOT = r"C:\Users\Xuan\AppData\Local\Programs\OSGeo4W"

    # 修复 PROJ 和 PATH
    os.environ['PROJ_LIB'] = os.path.join(OSGEO4W_ROOT, "share", "proj")
    os.environ['PATH'] = os.path.join(OSGEO4W_ROOT, "bin") + ";" + os.environ['PATH']

    # 指定 DLL 路径
    GDAL_LIBRARY_PATH = os.path.join(OSGEO4W_ROOT, "bin", "gdal312.dll")
    GEOS_LIBRARY_PATH = os.path.join(OSGEO4W_ROOT, "bin", "geos_c.dll")
    os.environ['GDAL_DATA'] = os.path.join(OSGEO4W_ROOT, "share", "gdal")

else:
    # ----- Linux 服务器环境 -----
    # 只要服务器上安装了 gdal-bin，Django 通常能自己找到。
    # 这里不需要写任何路径，保持为空即可，避免报错。
    pass

# === 4. 品牌与文件配置 ===
LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static_root')

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# === 5. GIS 配置 ===
TDT_KEY = '0de0375367832014891a9f40e0e42911'

LEAFLET_CONFIG = {
    'DEFAULT_CENTER': (34.75, 113.62),
    'DEFAULT_ZOOM': 10,
    'MIN_ZOOM': 3,
    'MAX_ZOOM': 18,
    'RESET_VIEW': False,
    'SCALE': 'metric',
    'ATTRIBUTION_PREFIX': 'Powered by Django-Leaflet & Tianditu',
    'TILES': [
        (
            '天地图矢量底图',
            f'http://t0.tianditu.gov.cn/vec_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=vec&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={{z}}&TILEROW={{y}}&TILECOL={{x}}&tk={TDT_KEY}',
            {'attribution': '天地图'}
        ),
        (
            '天地图卫星影像',
            f'http://t0.tianditu.gov.cn/img_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=img&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={{z}}&TILEROW={{y}}&TILECOL={{x}}&tk={TDT_KEY}',
            {'attribution': '天地图'}
        ),
    ],
    'OVERLAYS': [
        (
            '天地图地名注记(文字)',
            f'http://t0.tianditu.gov.cn/cva_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=cva&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={{z}}&TILEROW={{y}}&TILECOL={{x}}&tk={TDT_KEY}',
            {'attribution': '天地图'}
        ),
        (
            '卫星图注记(文字)',
            f'http://t0.tianditu.gov.cn/cia_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=cia&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={{z}}&TILEROW={{y}}&TILECOL={{x}}&tk={TDT_KEY}',
            {'attribution': '天地图'}
        ),
    ],
}

# === 6. SimpleUI 后台美化配置 ===
SIMPLEUI_HOME_INFO = False
SIMPLEUI_ANALYSIS = False
SIMPLEUI_LOGO = 'https://cdn-icons-png.flaticon.com/512/2913/2913520.png'
SIMPLEUI_DEFAULT_THEME = 'admin.lte.css'

SIMPLEUI_HOME_TITLE = '黄河生态监测平台'
SIMPLEUI_SITE_TITLE = '黄河生态监测平台'
SIMPLEUI_INDEX_TITLE = '监测系统后台'


# === SimpleUI 图标配置 ===
SIMPLEUI_ICON = {
    '积分商城商品': 'fas fa-gift',      # 🎁 对应 Product (必须填 verbose_name 的名字)
    '观测记录': 'fas fa-binoculars',    # 🔭 对应 ObservationRecord
    '监测点位': 'fas fa-map-marker-alt',# 📍 对应 WetlandZone
    '监测样线': 'fas fa-route',         # 🛣️ 对应 MonitoringRoute
    '物种信息': 'fas fa-dove',          # 🐦 对应 SpeciesInfo
    '用户积分档案': 'fas fa-user-tag',  # 🏷️ 对应 UserProfile
    '模型识别记录': 'fas fa-robot',      # 🤖 对应 AIDetectionResult
}
CORS_ALLOW_ALL_ORIGINS = True
SIMPLEUI_CONFIG = {
    'system_keep': True,  # 保留系统自动生成的所有菜单
    'menus': [
        {
            'name': '水鸟识别',
            'icon': 'fas fa-dove',  # 使用与“物种信息”相同的图标，风格统一
            'url': '/bird-page/',   # 指向我们创建的水鸟识别页面
        }
    ]
}

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
}
