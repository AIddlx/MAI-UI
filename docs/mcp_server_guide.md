# MCP 服务器使用指南

`mai_desktop_http_mcp_server.py` 提供了基于 HTTP 的 MCP 协议服务器，可集成到 Claude Desktop 等 MCP 客户端。

---

## 功能特点

- **MCP 协议支持**: 遵循 MCP JSON-RPC 2.0 标准
- **HTTP 接口**: 通过 HTTP 请求调用
- **真实执行**: 实际执行桌面操作
- **三合一工具**: 截图、动作预测、滚动操作

---

## 前置要求

### 1. 启动 LM Studio

1. 在 LM Studio 中下载 MAI-UI 模型（搜索 `MAI-UI` 或 `Tongyi-MAI`）
2. 选择模型后点击 **Server** 按钮
3. 确认配置：
   - Host: `127.0.0.1`
   - Port: `1234`
4. 点击 **Start Server** 启动

### 2. 安装依赖

```bash
pip install fastapi uvicorn pyautogui mss pillow
```

---

## 快速开始

### 启动服务器

```bash
python src/mai_desktop_http_mcp_server.py
```

### 自定义配置

```bash
python src/mai_desktop_http_mcp_server.py \
    --host 127.0.0.1 \
    --port 3359 \
    --llm-url http://localhost:1234/v1 \
    --model mai-ui
```

### 启动输出

```
🚀 MAI-UI Desktop HTTP MCP Server
📡 Listening on http://127.0.0.1:3359/mcp
🤖 Model: mai-ui
🔗 LLM API: http://localhost:1234/v1

💡 Configure your MCP client:
   {"mcpServers": {"mai-desktop": {"url": "http://127.0.0.1:3359/mcp"}}
```

---

## MCP 工具

### 1. screenshot - 截取屏幕

截取当前屏幕并保存为文件。

**参数**: 无

**返回**: 截图文件的绝对路径

```json
{
  "name": "screenshot",
  "description": "Capture the current screen and save to a file. Returns the absolute path to the screenshot file.",
  "inputSchema": {
    "type": "object",
    "properties": {},
    "required": []
  }
}
```

### 2. predict_action - 预测并执行动作

根据指令和截图预测并执行单个桌面动作。

**参数**:
- `instruction` (string): 清晰描述要点击的元素或要输入的文本
- `screenshot_path` (string): 截图文件的绝对路径

**返回**: 执行结果（包含思考过程、预测动作、执行状态）

```json
{
  "name": "predict_action",
  "description": "Predict and execute a single desktop action (click/type/wait) based on instruction and screenshot.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "instruction": {
        "type": "string",
        "description": "Clear description of the target element to click or text to type."
      },
      "screenshot_path": {
        "type": "string",
        "description": "Absolute path to the screenshot file"
      }
    },
    "required": ["instruction", "screenshot_path"]
  }
}
```

### 3. scroll_action - 预测并执行滚动

预测滚动位置并执行滚动操作。

**参数**:
- `instruction` (string): 简要描述滚动位置
- `direction` (string): 滚动方向 "up" 或 "down"
- `amount` (number): 滚动量（推荐 3-5）
- `screenshot_path` (string): 截图文件的绝对路径

**返回**: 执行结果（包含预测位置、滚动动作）

```json
{
  "name": "scroll_action",
  "description": "Predict scroll position and execute scroll.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "instruction": {"type": "string"},
      "direction": {"type": "string", "enum": ["up", "down"]},
      "amount": {"type": "number"},
      "screenshot_path": {"type": "string"}
    },
    "required": ["instruction", "direction", "amount", "screenshot_path"]
  }
}
```

---

## MCP 客户端配置

### Claude Desktop

**配置文件位置**:
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

**配置内容**:
```json
{
  "mcpServers": {
    "mai-desktop": {
      "url": "http://127.0.0.1:3359/mcp"
    }
  }
}
```

### 阶跃桌面助手

**配置格式**:
```json
{
  "mcpServers": {
    "mai-desktop": {
      "url": "http://127.0.0.1:3359/mcp"
    }
  }
}
```

**配置步骤**:
1. 启动 MCP 服务器：`python src\mai_desktop_http_mcp_server.py`
2. 在阶跃桌面助手的 MCP 设置中添加上述配置
3. 重启阶跃桌面助手

---

## 使用示例

### 在 Claude Desktop 中使用

```
用户: 帮我点击任务栏左侧的记事本图标

Claude: [调用 screenshot 工具]
       截图已保存: C:\Project\IDEA\MAI-UI\screenshots\screenshot_20250115_123456.png

       [调用 predict_action 工具]
       指令: 点击任务栏左侧的记事本图标
       截图: C:\Project\IDEA\MAI-UI\screenshots\screenshot_20250115_123456.png

       ✓ 已点击记事本图标
```

### 滚动操作

```
用户: 向下滚动聊天窗口

Claude: [调用 screenshot 工具]

       [调用 scroll_action 工具]
       指令: 滚动聊天窗口
       方向: down
       滚动量: 3

       ✓ 已向下滚动
```

---

## API 接口

### MCP 端点

**URL**: `POST http://127.0.0.1:3359/mcp`

**Content-Type**: `application/json`

### 请求格式

```json
{
  "jsonrpc": "2.0",
  "id": "unique-id",
  "method": "tools/call",
  "params": {
    "name": "predict_action",
    "arguments": {
      "instruction": "点击记事本图标",
      "screenshot_path": "C:\\screenshots\\screenshot.png"
    }
  }
}
```

### 响应格式

```json
{
  "jsonrpc": "2.0",
  "id": "unique-id",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\n  \"thinking\": \"...\",\n  \"predicted_action\": {...},\n  \"executed\": true,\n  \"execution_result\": \"Clicked (100, 200)\"\n}"
      }
    ]
  }
}
```

---

## 支持的动作

| 动作 | 说明 |
|------|------|
| `click` | 点击指定坐标 |
| `type` | 输入文本 |
| `wait` | 等待指定时间 |
| `scroll` | 滚动（预测位置） |
| `answer` | 返回答案 |
| `terminate` | 任务完成 |

---

## 坐标系统

- **模型输出**: `[0, 999]` 范围
- **归一化处理**: 自动转换为 `[0, 1]`
- **屏幕执行**: 自动转换为实际像素坐标

---

## 配置参数

```bash
python src/mai_desktop_http_mcp_server.py [OPTIONS]

Options:
  --host TEXT        绑定地址 (默认: 127.0.0.1)
  --port INTEGER     绑定端口 (默认: 3359)
  --llm-url TEXT     LLM API 地址 (默认: http://localhost:1234/v1)
  --model TEXT       模型名称 (默认: mai-ui)
```

---

## 常见问题

### Q: Claude Desktop 无法连接服务器？

A: 检查：
1. 服务器是否正在运行
2. 端口是否正确（默认 3359）
3. 配置文件路径是否正确

### Q: 动作执行失败？

A: 检查：
1. 截图路径是否正确
2. 指令描述是否清晰
3. 查看服务器日志

### Q: 如何查看服务器日志？

A: 服务器会在控制台输出详细日志，包括：
- 接收的请求
- 预测的动作
- 执行结果

---

## 适用场景

| 场景 | 推荐使用 |
|------|----------|
| Claude Desktop 集成 | ✅ 推荐 |
| 需要 MCP 协议 | ✅ 推荐 |
| 作为服务运行 | ✅ 推荐 |
| 直接命令行使用 | ❌ 建议使用 `oneshot_agent_example.py` |
