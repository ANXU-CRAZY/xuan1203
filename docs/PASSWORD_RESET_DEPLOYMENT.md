# 邮箱验证码找回密码

普通登录页与管理员登录页共用验证码 API。管理员入口通过
`/login/?role=admin#password-reset` 打开重置表单，完成后返回后台登录页。
`role` 只决定返回入口，不修改或授予用户权限。

## 生产配置

将 `.env.example` 中的 SMTP 参数填写到 `/home/xuan1203/.env.local`。
文件仅允许服务账号读取，权限设为 `0600`；不能提交真实凭证。
代码读取 `.env`、`.env.local`，同名服务器环境变量具有更高优先级。
部署代码前先保留服务器原有的数据库、域名和密钥设置，向现有 settings
加入 `load_smtp_settings(BASE_DIR)`，不要用本地 settings 覆盖服务器配置。

SMTP 使用 `smtp.163.com:465`、SSL，关闭 STARTTLS。填写 `SMTP_USER`、
`SMTP_PASSWORD` 和 `SMTP_FROM`，另用 `secrets.token_hex(32)` 生成独立的
`PASSWORD_RESET_HMAC_KEY`。邮件发送进程和 Web 进程必须使用同一个密钥。
只有反向代理可靠覆盖 `X-Real-IP`，且 Gunicorn 不允许外网直接访问时，
才能启用 `PASSWORD_RESET_TRUST_PROXY=True`。

运行数据库迁移后，将 `deploy/ark-password-reset-mail.service` 安装到
`/etc/systemd/system/`，执行 `systemctl daemon-reload` 及
`systemctl enable --now ark-password-reset-mail`。示例用户与当前 Web 服务
相同；如果调整服务账号，必须同时授予配置和数据库的必要读取权限。
重载 Gunicorn，使所有 Web 进程读取新配置。

## 保存和限制

验证码由 `secrets` 生成，六位数字，有效期五分钟；PostgreSQL 只保存
带独立服务端密钥的 HMAC 摘要，绑定请求、账号、邮箱和找回密码用途。
同一邮箱每六十秒一次、每小时五次；每 IP 每小时二十次，全局每十分钟
一百二十次。数据库行锁保护发送配额与验证码消费。错误五次即失效，
重发成功后旧码失效；成功修改密码后立即清除验证码、已有 DRF Token，
Django 登录会话随密码哈希变化失效。

邮件采用持久化队列，避免接口耗时泄露邮箱是否存在。HTTP 202 仅表示请求
被受理，页面使用条件提示；发送失败不记录有效验证码。SMTP 连接故障会
触发短暂熔断，邮件进程失联时发送接口返回 503。日志仅记录异常类型，
不能记录验证码、授权码或完整 SMTP 异常。过期摘要每分钟清理，限流请求
记录保存一天。

重置依赖账号已有唯一、有效的邮箱。被禁用、重复邮箱或无可用密码的账号
不会发送验证码，响应保持一致。上线验证应使用独立临时测试账号，不修改
现有用户密码，也不要将数据库、邮件凭证或验证码放入 Git。

## 检查

运行 `python manage.py check`、`python manage.py migrate --check` 和
`python manage.py test app_monitor.test_account app_monitor.test_password_reset`。
同时检查普通与管理员入口、验证码发送状态、邮件进程心跳、重置后重新登录，
以及 `/platform/` 部署前缀下的链接和静态资源。
