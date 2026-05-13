# DeepSeek API 配置说明

## 📊 当前状态

✅ **AI 聊天功能正常工作**（日志显示所有请求返回 200）
❌ **配置文件缺失**（`.env.local` 不存在）

## 🔍 问题分析

从服务器日志可以看到：
```
May 13 21:57:29 "POST /api/ai/chat/ HTTP/1.0" 200 3443
May 13 21:57:41 "POST /api/ai/chat/ HTTP/1.0" 200 3466
May 13 21:58:02 "POST /api/ai/chat/ HTTP/1.0" 200 4145
```

所有 AI 请求都成功返回，说明 **API Key 已经配置，只是不在 `.env.local` 文件中**。

## 🔧 API Key 加载顺序

根据 `app_monitor/views.py` 的代码，API Key 按以下顺序加载：

1. **系统环境变量**：`os.environ.get('DEEPSEEK_API_KEY')`
2. **`.env.local` 文件**：`/home/xuan1203/.env.local`
3. **`settings.py` 配置**：`settings.DEEPSEEK_API_KEY`

由于 `.env.local` 不存在且 `settings.py` 中也没有配置，说明 **API Key 在系统环境变量中**。

## 📋 查找当前配置

在服务器上执行以下命令，找出 API Key 的实际位置：

```bash
cd /home/xuan1203

# 1. 检查系统环境变量
env | grep DEEPSEEK

# 2. 检查 Gunicorn service 配置
sudo systemctl cat gunicorn | grep -i deepseek

# 3. 检查是否在 systemd 环境文件中
sudo cat /etc/systemd/system/gunicorn.service.d/*.conf 2>/dev/null | grep DEEPSEEK

# 4. 检查 Gunicorn 进程的环境变量
sudo cat /proc/$(pgrep -f "gunicorn.*config.wsgi" | head -1)/environ | tr '\0' '\n' | grep DEEPSEEK
```

## ✅ 推荐配置方案：创建 `.env.local`

为了规范化配置并便于管理，建议创建 `.env.local` 文件：

### 步骤 1：创建配置文件

```bash
cd /home/xuan1203

# 创建 .env.local 文件
cat > .env.local << 'EOF'
# DeepSeek API 配置
DEEPSEEK_API_KEY=你的API密钥
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com
EOF

# 设置权限（保护密钥安全）
chmod 600 .env.local
chown xuan1203:xuan1203 .env.local
```

### 步骤 2：安装依赖（如果需要）

```bash
source venv/bin/activate
pip install python-dotenv
```

### 步骤 3：重启服务

```bash
sudo systemctl restart gunicorn
```

### 步骤 4：测试

```bash
# 测试 API 连接
curl -X POST https://3.1415926.love/api/ai/chat/ \
  -H "Content-Type: application/json" \
  -d '{"message":"你好","page_context":{}}'
```

## 🔒 安全建议

1. **不要将 `.env.local` 提交到 Git**
   ```bash
   # 确保 .gitignore 包含
   echo ".env.local" >> .gitignore
   ```

2. **设置正确的文件权限**
   ```bash
   chmod 600 .env.local  # 只有所有者可读写
   ```

3. **定期轮换 API Key**

## 📝 配置文件模板

`.env.local` 文件示例：

```bash
# DeepSeek API 配置
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com

# 可选：其他环境变量
# DEBUG=False
# ALLOWED_HOSTS=3.1415926.love,8.130.88.229
```

## 🎯 总结

- ✅ **当前状态**：API 功能正常，Key 在系统环境变量中
- ⚠️ **建议操作**：创建 `.env.local` 文件，规范化配置
- 🔒 **安全提示**：保护好 API Key，不要泄露到公开仓库

## 🆘 故障排查

如果 API 突然不工作了：

1. **检查 API Key 是否过期**
   ```bash
   curl -X POST https://api.deepseek.com/v1/chat/completions \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer 你的KEY" \
     -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"test"}],"max_tokens":10}'
   ```

2. **检查日志**
   ```bash
   sudo journalctl -u gunicorn -n 100 | grep -i "deepseek\|api\|error"
   ```

3. **检查网络连接**
   ```bash
   ping -c 3 api.deepseek.com
   curl -I https://api.deepseek.com
   ```

4. **重启服务**
   ```bash
   sudo systemctl restart gunicorn
   ```
