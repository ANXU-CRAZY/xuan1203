# 黄河生态方舟平台接口文档说明书

版本：v1.0  
部署地址：http://8.130.88.229  
后端框架：Django + Django REST Framework  
部署方式：Nginx + Gunicorn + PostgreSQL/PostGIS  

## 1. 文档说明

本文档用于说明“黄河生态方舟”平台在服务器部署后的主要页面入口、业务 API、认证方式、请求参数和返回字段。平台主要面向黄河湿地水鸟监测、鸟类识别、观测记录管理、图库科普和公众参与等场景。

接口基础地址：

```text
http://8.130.88.229
```

API 基础路径：

```text
http://8.130.88.229/api/
```

水鸟识别接口基础路径：

```text
http://8.130.88.229/bird/
```

## 2. 页面入口

| 页面 | 地址 | 说明 |
|---|---|---|
| 首页/地图监测平台 | `/` | 水鸟观测地图、点位、样线、热力图、图层切换等 |
| 管理后台 | `/admin/` | Django 管理后台，用于审核和维护数据 |
| 登录页 | `/login/` | 前端登录页面 |
| 个人中心 | `/profile/` | 用户资料和积分等信息 |
| 观测报告页 | `/report/` | 观测/报告相关页面 |
| 物种列表页 | `/species/` | 鸟类物种信息列表 |
| 物种详情页 | `/species/{species_id}/` | 单个鸟类物种详情 |
| 鸟类图库页 | `/gallery/` | 鸟类图库展示 |
| 图片图库页 | `/image-gallery/` | 图片图库页面 |
| 科普文章页 | `/articles/` | 鸟类科普文章列表 |
| 文章详情页 | `/articles/{article_id}/` | 单篇科普文章详情 |
| 水鸟识别页 | `/bird-page/` | 上传图片并调用识别模型 |
| 看图识鸟游戏 | `/bird-guess/` | 看图识鸟互动功能 |
| 迁徙页面 | `/migration/` | 鸟类迁徙展示页面 |
| 湿地修复互动 | `/wetland-restorer/` | 湿地修复互动页面 |
| 湿地侦探互动 | `/wetland-detective/` | 湿地侦探互动页面 |
| 飞鸟跑酷互动 | `/bird-runner/` | 飞鸟跑酷互动页面 |
| 浮岛互动页面 | `/floating-island/` | 浮岛相关互动页面 |

## 3. 认证方式

平台采用 Token 认证。用户登录成功后，后端返回 token，后续需要登录态的接口在请求头中携带：

```http
Authorization: Token <token>
```

示例：

```bash
curl -H "Authorization: Token xxxxxx" http://8.130.88.229/api/profiles/me/
```

## 4. 用户注册与登录接口

### 4.1 用户注册

```http
POST /api/auth/register/
```

请求体：

```json
{
  "username": "testuser",
  "email": "test@example.com",
  "password": "YourPassword123",
  "password_confirm": "YourPassword123"
}
```

成功返回：

```json
{
  "user": {
    "id": 1,
    "username": "testuser",
    "email": "test@example.com",
    "score": 0,
    "avatar": null
  },
  "token": "xxxxxxxxxxxxxxxx",
  "message": "注册成功"
}
```

说明：

- 注册成功后会自动创建用户积分档案。
- 返回的 `token` 用于后续登录接口鉴权。

### 4.2 用户登录

```http
POST /api/login/
```

请求体：

```json
{
  "username": "testuser",
  "password": "YourPassword123"
}
```

成功返回：

```json
{
  "token": "xxxxxxxxxxxxxxxx"
}
```

## 5. 用户资料接口

### 5.1 获取当前用户信息

```http
GET /api/profiles/me/
```

权限：需要 Token

返回字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | number | 用户 ID |
| username | string | 用户名 |
| email | string | 邮箱 |
| score | number | 当前积分 |
| avatar | string/null | 头像地址 |

### 5.2 修改当前用户积分

```http
PATCH /api/profiles/me/score/
```

权限：需要 Token

请求体：

```json
{
  "score": 120
}
```

成功返回：

```json
{
  "score": 120
}
```

### 5.3 修改用户资料

```http
PATCH /api/profiles/update_profile/
```

权限：需要 Token

请求体：

```json
{
  "email": "new@example.com"
}
```

### 5.4 上传头像

```http
POST /api/profiles/me/avatar/
```

权限：需要 Token  
请求类型：`multipart/form-data`

参数：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| avatar | file | 是 | 用户头像图片 |

## 6. 物种信息接口

### 6.1 获取物种列表

```http
GET /api/species/
```

权限：公开访问

返回字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | number | 物种 ID |
| name_cn | string | 中文名 |
| name_latin | string | 拉丁名 |
| order | string | 目 |
| family | string | 科 |
| protection_level | string | 保护等级 |
| distribution_habit | string | 分布习性 |
| cover_image_url | string/null | 封面图片地址 |
| gallery_images | array | 图库图片列表 |
| gallery_count | number | 图库图片数量 |
| observation_count | number | 已审核观测记录数量 |
| last_observed | string/null | 最近观测日期 |
| iucn_status | object | 风险状态展示信息 |
| article_count | number | 相关文章数量 |

示例：

```bash
curl http://8.130.88.229/api/species/
```

### 6.2 获取单个物种信息

```http
GET /api/species/{id}/
```

示例：

```bash
curl http://8.130.88.229/api/species/1/
```

## 7. 观测记录接口

### 7.1 获取观测记录列表

```http
GET /api/observations/
```

权限：

- 游客：只能看到已审核通过的记录。
- 登录用户：能看到已审核通过的记录和自己上传的记录。
- 管理员：能看到全部记录。

返回字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | number | 观测记录 ID |
| image | string/null | 现场照片 |
| description | string/null | 描述 |
| observation_time | string | 观测日期 |
| count | number | 观测数量 |
| status | string | 审核状态，`pending`/`approved`/`rejected` |
| species | number | 物种 ID |
| species_id | number | 物种 ID |
| species_name | string | 物种中文名 |
| species_protection | string | 物种保护等级 |
| zone | number | 点位 ID |
| zone_name | string | 点位名称 |
| transect_name | string/null | 关联样线名称 |
| x | number/null | 经度 |
| y | number/null | 纬度 |
| lng | number/null | 经度 |
| lat | number/null | 纬度 |
| reporter_name | string | 上报人 |
| uploader_name | string | 上传者 |

### 7.2 新增观测记录

```http
POST /api/observations/
```

权限：需要 Token  
请求类型：`multipart/form-data` 或 JSON，若上传图片建议使用 `multipart/form-data`

常用参数：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| species | number | 是 | 物种 ID |
| zone | number | 是 | 点位 ID |
| count | number | 否 | 鸟类数量，默认 1 |
| image | file | 否 | 现场照片 |
| description | string | 否 | 描述 |

说明：

- 新记录默认进入待审核状态。
- 用户上传成功后，系统会为上传者增加积分。

### 7.3 获取单条观测记录

```http
GET /api/observations/{id}/
```

### 7.4 修改观测记录

```http
PUT /api/observations/{id}/
PATCH /api/observations/{id}/
```

权限：登录用户或后台权限，具体以 DRF 权限和后台配置为准。

### 7.5 删除观测记录

```http
DELETE /api/observations/{id}/
```

权限：登录用户或后台权限，具体以 DRF 权限和后台配置为准。

### 7.6 附近观测预警

```http
GET /api/observations/nearby_alert/?lat={纬度}&lng={经度}
```

功能：查询某个经纬度附近约 500 米范围内已审核通过的观测记录。

示例：

```bash
curl "http://8.130.88.229/api/observations/nearby_alert/?lat=34.75&lng=113.62"
```

### 7.7 矢量瓦片接口

```http
GET /api/observations/tiles/{z}/{x}/{y}/
```

返回类型：

```text
application/vnd.mapbox-vector-tile
```

说明：用于地图端加载观测记录矢量瓦片。

## 8. 监测点位接口

### 8.1 获取点位列表

```http
GET /api/zones/
```

返回字段为 `WetlandZone` 模型全部字段，主要包括：

| 字段 | 说明 |
|---|---|
| id | 点位 ID |
| name | 点位名称 |
| longitude | 经度 |
| latitude | 纬度 |
| location | GIS 点位 |
| is_hotspot | 是否推荐热点 |
| observation_tips | 观测提示 |

### 8.2 获取单个点位

```http
GET /api/zones/{id}/
```

### 8.3 新增/修改/删除点位

```http
POST /api/zones/
PUT /api/zones/{id}/
PATCH /api/zones/{id}/
DELETE /api/zones/{id}/
```

说明：建议由后台管理员维护。

## 9. 监测样线接口

### 9.1 获取样线列表

```http
GET /api/transects/
```

返回字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | number | 样线 ID |
| name | string | 样线名称 |
| description | string | 样线说明 |
| path | array | 适配 Leaflet 的坐标数组，格式为 `[[lat, lng], ...]` |

### 9.2 获取单个样线

```http
GET /api/transects/{id}/
```

### 9.3 新增/修改/删除样线

```http
POST /api/transects/
PUT /api/transects/{id}/
PATCH /api/transects/{id}/
DELETE /api/transects/{id}/
```

说明：建议由后台管理员维护，样线数据可通过 SHP 导入。

## 10. 鸟类图库接口

### 10.1 获取图库图片列表

```http
GET /api/species-images/
```

可选查询参数：

| 参数 | 类型 | 说明 |
|---|---|---|
| species_id | number | 按物种 ID 筛选图片 |

示例：

```bash
curl "http://8.130.88.229/api/species-images/?species_id=1"
```

返回字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | number | 图片 ID |
| species | number | 关联物种 ID |
| url | string/null | 图片访问地址 |
| caption | string | 图片说明 |
| source | string | 来源代码 |
| source_display | string | 来源展示文本 |
| source_url | string | 来源链接 |
| source_author | string | 作者 |
| views | number | 浏览量 |
| is_featured | boolean | 是否精选封面 |
| created_at | string | 添加时间 |

### 10.2 获取单张图片

```http
GET /api/species-images/{id}/
```

### 10.3 设置物种精选封面

```http
POST /api/species-images/{id}/set-featured/
```

请求体：

```json
{
  "species_id": 1
}
```

返回：

```json
{
  "success": true,
  "image_id": 10,
  "species_id": 1,
  "cover_image_url": "/media/species/gallery/example.jpg",
  "message": "精选封面已更新"
}
```

### 10.4 增加图片浏览量

```http
POST /api/species-images/{id}/view_image/
```

返回：

```json
{
  "views": 101
}
```

## 11. 科普文章接口

### 11.1 获取文章列表

```http
GET /api/articles/
```

权限：公开访问

返回字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | number | 文章 ID |
| title | string | 标题 |
| category | string | 分类 |
| summary | string | 摘要 |
| content | string | 正文 HTML |
| cover_image | string/null | 封面图 |
| author_name | string | 作者/来源 |
| views | number | 浏览量 |
| is_published | boolean | 是否发布 |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |

### 11.2 获取文章详情

```http
GET /api/articles/{id}/
```

### 11.3 增加文章浏览量

```http
POST /api/articles/{id}/view/
```

返回：

```json
{
  "views": 101
}
```

## 12. 积分商城接口

### 12.1 获取商品列表

```http
GET /api/products/
```

返回字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | number | 商品 ID |
| name | string | 商品名称 |
| price | number | 所需积分 |
| image | string | 商品图片 |
| description | string | 商品描述 |
| stock | number | 库存 |

### 12.2 兑换商品

```http
POST /api/products/{id}/redeem/
```

权限：需要 Token

成功返回：

```json
{
  "message": "成功兑换: 商品名称",
  "remaining_score": 80
}
```

失败情况：

| 情况 | 返回 |
|---|---|
| 库存不足 | `{"error": "商品库存不足"}` |
| 积分不足 | `{"error": "积分不足..."}` |
| 用户档案不存在 | `{"error": "用户档案不存在"}` |

## 13. 水鸟识别接口

### 13.1 图片识别

```http
POST /bird/recognize/
```

权限：公开访问  
请求类型：`multipart/form-data`

参数：

| 参数 | 类型 | 必填 | 默认值 | 范围 | 说明 |
|---|---|---|---|---|---|
| image | file | 是 | - | JPEG/PNG/BMP，最大 10MB | 待识别鸟类图片 |
| detection_threshold | number | 否 | 0.25 | 0.01-0.95 | 检测模型置信度阈值 |
| classification_threshold | number | 否 | 0.0 | 0.0-0.95 | 分类模型置信度阈值 |

请求示例：

```bash
curl -X POST "http://8.130.88.229/bird/recognize/" \
  -F "image=@test_bird.JPG" \
  -F "detection_threshold=0.25" \
  -F "classification_threshold=0.10"
```

成功返回：

```json
{
  "success": true,
  "thresholds": {
    "detection": 0.25,
    "classification": 0.1
  },
  "image": {
    "width": 1920,
    "height": 1080
  },
  "results": [
    {
      "detection_bbox": [100, 120, 420, 520],
      "detection_confidence": 0.86,
      "detection_class_id": 0,
      "fine_class_id": 12,
      "fine_confidence": 0.92
    }
  ]
}
```

常见错误：

| 状态码 | 原因 |
|---|---|
| 400 | 图片格式错误、图片超过 10MB、参数范围不合法 |
| 500 | 模型加载或推理失败 |

模型文件部署路径：

```text
/home/xuan1203/bird_recognition/yolo_model/detector.pt
/home/xuan1203/bird_recognition/yolo_model/classifier.pt
```

## 14. 静态与媒体文件访问

### 14.1 静态文件

```http
GET /static/{path}
```

示例：

```text
http://8.130.88.229/static/admin/css/base.css
```

### 14.2 媒体文件

```http
GET /media/{path}
```

示例：

```text
http://8.130.88.229/media/species/gallery/鹌鹑.jpg
```

说明：

- 图库图片位于 `/media/species/gallery/`。
- 用户上传头像位于 `/media/avatars/`。
- 观测记录图片位于 `/media/observations/`。
- AI 识别记录图片位于 `/media/ai_records/`。

## 15. 部署后接口验证命令

服务器部署完成后，可在服务器终端执行以下命令验证：

```bash
curl -I http://8.130.88.229/
curl -I http://8.130.88.229/gallery/
curl -I http://8.130.88.229/admin/
curl -I http://8.130.88.229/api/species/
curl -I http://8.130.88.229/api/observations/
curl -I http://8.130.88.229/api/zones/
curl -I http://8.130.88.229/api/transects/
curl -I http://8.130.88.229/api/articles/
curl -I http://8.130.88.229/api/species-images/
```

预期结果：

| 地址 | 预期状态 |
|---|---|
| `/` | `200 OK` |
| `/gallery/` | `200 OK` |
| `/admin/` | `302 Found` 或登录页 `200 OK` |
| `/api/species/` | `200 OK` |
| `/api/observations/` | `200 OK` |
| `/api/zones/` | `200 OK` |
| `/api/transects/` | `200 OK` |
| `/api/articles/` | `200 OK` |
| `/api/species-images/` | `200 OK` |

## 16. 服务重启命令

服务器更新代码、迁移数据库、上传模型后，建议执行：

```bash
cd /home/xuan1203
source venv/bin/activate
python manage.py check
python manage.py migrate
python manage.py collectstatic --noinput
systemctl restart gunicorn
systemctl restart nginx
systemctl status gunicorn --no-pager -l
systemctl status nginx --no-pager -l
```

若水鸟识别模型更新，只需确认模型文件存在并重启：

```bash
ls -lh /home/xuan1203/bird_recognition/yolo_model
systemctl restart gunicorn
```

## 17. 备注

1. `/api/login/` 与 `/api/auth/register/` 用于前端登录和注册。
2. 需要用户身份的接口必须携带 `Authorization: Token <token>`。
3. `/bird/recognize/` 是模型识别接口，依赖服务器上的 `detector.pt` 和 `classifier.pt`。
4. `/api/species/`、`/api/species-images/`、`/api/articles/` 对图库、物种百科和科普页面提供数据支持。
5. `/api/observations/` 是首页地图、观测弹窗、热力图和统计面板的核心数据来源。
