# Serv00 账号注册服务

这是一个自动化账号注册服务，提供REST API接口。

## 功能特点

- 自动化表单填写
- 验证码自动识别
- RESTful API接口
- 详细的错误信息返回
- 可配置的重试机制
- 支持HTTP/HTTPS代理
- 并发任务控制
- 实时队列状态显示
- WebSocket实时更新

## 安装

1. 克隆仓库：
```bash
git clone <repository-url>
cd serv00Reg-1
```

2. 安装依赖：
```bash
pip install -r requirements.txt
```

3. 确保安装了Firefox浏览器（selenium驱动需要）

## 配置

配置文件 `config.json` 包含以下选项：

```json
{
    "url": "https://www.serv00.com/offer/create_new_account",
    "max_retries": 3,
    "timeout": 5,
    "wait_time": 0.5,
    "headless": true,  // 启用无头模式
    "proxy": {
        "enabled": false,  // 是否启用代理
        "http": "http://proxy.example.com:8080",  // HTTP代理地址
        "https": "http://proxy.example.com:8080"  // HTTPS代理地址
    },
    "max_concurrent_tasks": 2  // 最大并发任务数
}
```

- `url`: 注册页面URL
- `max_retries`: 验证码重试次数
- `timeout`: 页面加载超时时间（秒）
- `wait_time`: 元素等待时间（秒）
- `headless`: 是否启用无头模式（true/false）
- `proxy`: 代理服务器配置
  - `enabled`: 是否启用代理（true/false）
  - `http`: HTTP代理服务器地址（格式：http://host:port）
  - `https`: HTTPS代理服务器地址（格式：http://host:port）
- `max_concurrent_tasks`: 最大并发任务数，控制同时处理的注册任务数量

## 启动服务

### REST API服务

```bash
python api.py
```

API服务将在 http://localhost:8000 运行

### Web界面服务

Web界面支持环境变量配置：
- FLASK_HOST: 服务监听地址（默认：0.0.0.0）
- FLASK_PORT: 服务端口（默认：5000）

启动服务：
```bash
# 使用默认配置
python webui.py

# 或指定配置
export FLASK_HOST=127.0.0.1
export FLASK_PORT=8080
python webui.py
```

Web界面特性：
1. 任务队列管理
   - 自动排队处理注册请求
   - 可配置最大并发任务数
   - 任务间隔5秒，防止频繁请求

2. 实时状态更新
   - WebSocket实时推送任务状态
   - 显示当前队列位置
   - 显示当前活动任务数/最大并发数
   - 状态颜色区分：
     * 黄色：等待中（pending）
     * 蓝色：执行中（running）
     * 绿色：已完成（completed）
     * 红色：失败（failed）

3. 错误处理
   - 详细的错误信息显示
   - 失败原因追踪
   - 任务执行时间记录

4. 服务器状态监控
   - 自动检测服务器连接状态
   - 断线自动重连（最多5次尝试）
   - 服务器重启提示
   - WebSocket心跳检测

5. 跨域支持
   - 支持跨域请求
   - 支持代理服务器

## 使用方式

### 方式一：Web界面

1. 访问 http://localhost:5000
2. 填写注册表单
3. 点击提交按钮
4. 实时查看队列状态和处理进度

### 方式二：API调用

### 注册账号

**请求**:
- 方法: POST
- 端点: `/register`
- Content-Type: application/json

请求体格式：
```json
{
    "first_name": "名",
    "last_name": "姓",
    "username": "用户名",
    "email": "邮箱地址"
}
```

**响应**:
```json
{
    "success": true,
    "error": null  // 成功时为null，失败时包含错误信息
}
```

### 示例

使用curl：
```bash
curl -X POST "http://localhost:8000/register" \
     -H "Content-Type: application/json" \
     -d '{"first_name":"Test","last_name":"User","username":"testuser","email":"test@example.com"}'
```

使用Python requests：
```python
import requests

response = requests.post(
    "http://localhost:8000/register",
    json={
        "first_name": "Test",
        "last_name": "User",
        "username": "testuser",
        "email": "test@example.com"
    }
)
print(response.json())
```

## API 文档

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 错误处理

服务会返回详细的错误信息，包括：
- 验证码识别失败
- 页面加载超时
- 元素查找失败
- 表单提交错误
- 其他系统错误
