# 方舟云图 Android 观测贡献接口 v1.0.0

正式 API 基址是 `https://arklab-geoai.org.cn/platform/api`，请求路径保留末尾斜杠。机器可读接口见 [OpenAPI 3.0](android-contributions.openapi.yaml)，可导入 Postman 或 Apifox。

当前联调状态（2026-11-22）。登录、贡献资料和权限校验可先对接。线上尚未配置私有 S3 Bucket，创建新上传任务当前会返回 503，真实图片直传需等待存储配置完成。

下文的 `/api/…` 路径用于本机访问。线上请在这些路径前加 `/platform`。认证沿用平台的 `POST /api/login/`，请求体为 `{"username":"…","password":"…"}`。APP 对业务请求发送 `Authorization: Token <token>`。这些接口返回 JSON，图片请求则直接发往 S3。只通过 HTTPS 使用正式环境。

## 1. 创建上传任务

`POST /api/observations/upload-session/`

```json
{
  "clientObservationId": "f0d35f8e-e95f-4594-959b-75f26d17ed93",
  "title": "湿地观测",
  "description": "",
  "capturedAt": "2026-11-22T10:30:00+08:00",
  "location": {"longitude": 113.6, "latitude": 34.9, "accuracy": 8.5, "source": "gps"},
  "device": {"phoneModel": "Android", "thermalDeviceModel": "E20 Plus"},
  "media": [
    {
      "clientMediaId": "8dfeb84b-38af-491b-8f1a-6adf81e79dc9",
      "type": "rgb",
      "pairGroupId": "2c99774f-232d-4dd1-89ba-1e82fe1fc105",
      "filename": "rgb.jpg",
      "mimeType": "image/jpeg",
      "fileSize": 3456789,
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    }
  ]
}
```

上例 SHA-256 为占位。上传前请计算最终文件的 64 位十六进制 SHA-256，上传时使用计算过哈希的原始字节。支持 JPEG、PNG、WebP 静态图，单张最多 20 MiB 和 2500 万像素。每条贡献最多一张 RGB、一张红外、一张可选缩略图。至少提交一张原图，组内图片使用同一 `pairGroupId`。无定位时省略 `location`，设备和物种名称可省略。

首次创建返回 201，重复调用返回 200。例如：

```json
{
  "observationId": 123,
  "status": "uploading",
  "uploads": [{
    "clientMediaId": "8dfeb84b-38af-491b-8f1a-6adf81e79dc9",
    "objectKey": "contributions/staging/17/123/8dfeb84b-38af-491b-8f1a-6adf81e79dc9/rgb.jpg",
    "uploadUrl": "https://example.invalid/presigned-put",
    "method": "PUT",
    "headers": {
      "Content-Type": "image/jpeg",
      "Content-Length": "3456789",
      "x-amz-checksum-sha256": "<S3 使用的 Base64 校验值>"
    },
    "expiresAt": "2026-11-22T02:40:00Z"
  }]
}
```

同一用户、同一 UUID 对应一份固定清单。网络重试和链接刷新应发送原始清单，变更清单返回 409。已校验的图片无需再次上传，已完成观测返回空的 `uploads`。

## 2. APP 直传双光图片

对每个任务向 `uploadUrl` 发原始文件的 PUT 请求，使用返回的所有请求头和确切的文件长度。Android 的请求体应能返回确定的 `contentLength()`。不要用 multipart，不要对图片重新编码，也不要把平台 Token 附加到 S3 请求。上传地址和短时下载地址属于临时凭证，不应写入日志或长期缓存。链接过期时重新申请任务。

## 3. 确认、重试、查阅

`POST /api/observations/123/complete/` 接收**完整清单**，包括之前已验证成功的图片：

```json
{
  "media": [{
    "clientMediaId": "8dfeb84b-38af-491b-8f1a-6adf81e79dc9",
    "objectKey": "contributions/staging/17/123/8dfeb84b-38af-491b-8f1a-6adf81e79dc9/rgb.jpg",
    "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }]
}
```

成功返回 200，包含 `observationId`、`status: "completed"`、`pointsAwarded`、积分与段位、每张图片状态。同一条贡献只能发一次分，重复确认返回该观测和用户当前积分。缺图或图片校验失败返回 409 与各项状态，保留已经验证的图片。校验失败如果源文件本身已损坏，应先修正文件，再用新 UUID 建立新观测。存储暂不可用返回 503，可用原参数重试。APP 应给确认请求留出足够时间，重复请求不会重复发分。

例如只有 RGB、带坐标的观测完成后返回以下字段。完整响应还包含 `clientObservationId`、`uploadError`、`retryable`、`media` 和 `rank`。

```json
{
  "observationId": 123,
  "status": "completed",
  "pointsAwarded": 15,
  "availablePoints": 15,
  "totalContributionPoints": 15,
  "completedObservationCount": 1
}
```

| 方法和路径 | 返回内容或行为 |
| --- | --- |
| GET `/api/observations/123/upload-status/` | 上传中、失败或已完成，包含逐图状态、失败原因和重试标记 |
| GET `/api/observations/mine/?page=1&pageSize=20&status=completed` | `count`、分页参数、`results`。每条含拍摄时间、位置、双光配对、积分和短时缩略图地址。无缩略图时回退为原图 |
| GET `/api/observations/123/contribution/` | 详情，完成后发放短时 `rgbImageUrl`、`thermalImageUrl`、`thumbnailUrl` |
| DELETE `/api/observations/123/contribution/` | 204，软删除。停止签发下载链接，已签发的链接会正常到期，保留历史积分和流水 |
| GET `/api/users/me/contribution-profile/` | `availablePoints`、`totalContributionPoints`、`completedObservationCount`、`rank` |

本版 APP 观测默认私有，拥有者之外返回 404，且不会进入原有 Web 观测接口、公开地图或后台导出。没有公开发布接口。位置及原始图片内嵌 EXIF 随原图受同一访问控制。接口不额外提取或回传 EXIF。

贡献资料示例：

```json
{
  "availablePoints": 1000,
  "totalContributionPoints": 1320,
  "completedObservationCount": 66,
  "rank": {
    "code": "ECO_GOLD_WING",
    "name": "生态金翼",
    "minimumPoints": 1200,
    "maximumPoints": 2499,
    "nextRankName": "方舟守望者",
    "nextRankPoints": 2500,
    "pointsToNextRank": 1180,
    "progressPercent": 9
  }
}
```

APP 用历史贡献积分和服务端返回的 `rank`，不要再把手机记录的最高余额视为段位。双光原图一对得 20 分，单种原图得 10 分，有有效坐标额外得 5 分。缩略图不额外计分。积分规则位于 `config/contribution_settings.py`。兑换会扣可用余额，继续沿用 `POST /api/products/{id}/redeem/`。新客户端请发送每笔交易独立的 `Idempotency-Key`，重试同笔交易时复用该值。旧 Web 客户端不带该请求头的操作按新交易处理。

## 配置与迁移

1. 为服务创建 AWS S3 通用型私有 Bucket，启用 Block Public Access。为 Django 运行身份授予该专用桶的 `s3:ListBucket`，并允许对 `contributions/staging/*` 和 `contributions/images/*` 执行所需的 `s3:GetObject`、`s3:PutObject`。原图下载地址只在服务端为所有者签发。
2. 按 `.env.example` 将 `CONTRIBUTION_STORAGE_BUCKET`、`CONTRIBUTION_STORAGE_REGION` 注入 Django 进程环境。上传签名默认 600 秒，下载默认 300 秒，可通过 `CONTRIBUTION_UPLOAD_TTL`、`CONTRIBUTION_DOWNLOAD_TTL` 调整。建议用 IAM Role。环境凭证也由 AWS SDK 读取，切勿写入代码。
3. 安装 `requirements.txt` 后先由部署人员在目标环境运行 `python manage.py migrate --plan`，再运行 `python manage.py migrate` 并发布新代码。迁移 `0011_observation_contributions` 扩展现有观测和积分档案，新增图片及流水表，无须手工改库。历史兑换余额原样保留，无法从旧余额可靠恢复历史贡献或已完成数量，两者从新流水开始统计。旧 Web 上报仍发 10 分。同时，小游戏分数继续由原个人资料接口记录到 `game_score`，兑换余额通过 `score` 读取。旧客户端提交的游戏分数不再增加兑换余额。
4. 建议只为 `contributions/staging/` 设置例如 7 天过期的 S3 生命周期。七天后若尚未确认，重试所需图片要重新上传。正式对象保留时间、软删除后的清理以及云端孤立对象回收由项目部署方制定。已签发的 PUT 可在到期前重放，但签名绑定数据长度和 SHA-256，且只允许写暂存路径。确认时服务端读取 S3 原始字节核对 SHA-256 并解码图片，再由 S3 条件复制到正式路径。上传流量不经过 Django，确认环节仍会产生服务端读取图片的流量。
5. 若目标环境已有 APP 网关、CDN 或反向代理，禁止缓存这些私有 API 响应。使用真实 Bucket 后，请用测试账号跑一遍登录、双光直传、确认、兑换、权限检查和短时 URL 过期。

AWS 操作参考：[S3 PutObject](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/put_object.html)、[S3 CopyObject](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/copy_object.html)。

## 文件清单

- `app_monitor/models.py`、`app_monitor/migrations/0011_observation_contributions.py` 扩展现有数据模型和约束。
- `app_monitor/contribution_api.py`、`app_monitor/contribution_serializers.py`、`app_monitor/contributions.py` 实现接口、输入验证和上传流程。
- `app_monitor/contribution_storage.py`、`app_monitor/contribution_points.py` 实现对象存储与积分流水。
- `app_monitor/views.py`、`app_monitor/serializers.py`、`app_monitor/admin.py` 接入旧版 Web、商城和后台。移除 `app_monitor/signals.py` 中旧的无效积分逻辑及其注册（`app_monitor/apps.py`）。
- `app_monitor/management/commands/fast_import_observations.py`、`app_monitor/management/commands/refresh_map_observation_cache.py` 保持 APP 私有观测与旧数据导入和公开地图缓存隔离。
- `templates/bird-guess.html`、`templates/bird-runner.html`、`templates/floating-island.html`、`templates/migration.html`、`templates/wetland-detective.html`、`templates/wetland-restorer.html` 读取独立的游戏分数。
- `config/urls.py`、`config/settings.py`、`config/contribution_settings.py`、`.env.example`、`requirements.txt` 提供路由、配置和依赖。
- `app_monitor/test_contributions.py` 覆盖 API、权限、积分和对象存储适配器。
- `docs/android-contributions.openapi.yaml` 提供可导入的 OpenAPI 接口定义。
