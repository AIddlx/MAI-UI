# 虚拟环境设置与测试指南

本文档指导你从零开始设置虚拟环境并运行 MAI-UI 桌面自动化示例。

**使用 LM Studio 运行 MAI-UI 模型**

---

## 系统要求

- **操作系统**: Windows 10/11
- **Python**: 3.9 - 3.11
- **LM Studio**: 最新版本（用于运行 MAI-UI 模型）
- **内存**: 推荐 16GB+

---

## 第一步：安装 LM Studio

### 1. 下载 LM Studio

访问 [lmstudio.ai](https://lmstudio.ai/) 下载并安装。

### 2. 下载 MAI-UI 模型

下载以下两个文件（放在同一目录）：

```
视觉模型:
https://hf-mirror.com/mradermacher/MAI-UI-8B-GGUF/resolve/main/MAI-UI-8B.Q8_0.gguf?download=true

文本模型:
https://hf-mirror.com/mradermacher/MAI-UI-8B-GGUF/resolve/main/MAI-UI-8B.mmproj-Q8_0.gguf?download=true
```

下载后目录结构：
```
D:\models\MAI-UI-8B\
├── MAI-UI-8B.Q8_0.gguf        (视觉模型)
└── MAI-UI-8B.mmproj-Q8_0.gguf  (文本模型)
```

### 3. 在 LM Studio 中加载模型

1. 打开 LM Studio
2. 点击左侧 **"💾"** 图标
3. 点击 **"📁"** 按钮，选择模型文件所在目录
4. 选择 `MAI-UI-8B.Q8_0.gguf` 文件加载

### 4. 启动模型服务

1. 在 LM Studio 左侧选择已下载的模型
2. 点击 **"Server"** 按钮（或 **"💾"** 图标）
3. 确认配置：
   - **Host**: `127.0.0.1`
   - **Port**: `1234`
   - **Base URL**: `http://localhost:1234/v1`
4. 点击 **"Start Server"** 启动服务

服务启动后会显示：
```
Server running at http://localhost:1234/v1
```

---

## 第二步：创建虚拟环境并安装依赖

### 完整操作流程

```powershell
# 进入项目目录
cd C:\Project\IDEA\MAI-UI

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
.\venv\Scripts\Activate.ps1

# 如果遇到执行策略错误，先运行：
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 升级 pip
python -m pip install --upgrade pip

# 安装依赖
pip install -r requirements.txt
```

激活成功后，命令行前面会显示 `(venv)`：

```
(venv) C:\Project\IDEA\MAI-UI>
```

### 依赖列表

```
Jinja2==3.1.6
numpy==2.3.5
openai==2.13.0
Pillow==12.0.0
fastapi>=0.104.0
uvicorn>=0.24.0
mss>=9.0.0
pyautogui>=0.9.54
pyperclip>=1.8.0
```

---

## 第三步：确认模型服务运行

在浏览器或终端测试 LM Studio API：

```powershell
# 测试 API 是否可用
curl http://localhost:1234/v1/models
```

正常返回：
```json
{
  "object": "list",
  "data": [
    {
      "id": "mai-ui",
      "object": "model"
    }
  ]
}
```

---

## 第四步：运行测试

### 测试1：单步代理

在第一个终端（虚拟环境已激活）中运行：

```powershell
cd examples
python oneshot_agent_example.py
```

**测试指令**：
```
点击任务栏左边的开始按钮
```

**预期结果**：
```
🚀 Initializing MAI-UI Desktop One-Shot Agent...
✓ Model: mai-ui
✓ Screen: 1920x1080

💬 输入指令 (或 'quit' 退出): 点击任务栏左边的开始按钮
  📸 截图中...
  🤖 预测并执行...
  🧠 思考过程: 在任务栏左侧找到开始按钮...
  🎯 执行动作: CLICK
  ✅ 执行结果: Clicked (x, y) with left button
```

### 测试2：完整导航代理

```powershell
cd examples
python desktop_agent_full_example.py
```

**测试指令**：
```
打开计算器并输入 123+456
```

**预期结果**：
```
🚀 Initializing MAI-UI Desktop Agent...
💬 Enter your instruction: 打开计算器并输入 123+456

============================================================
🎯 Task: 打开计算器并输入 123+456
============================================================

  🧠 Thinking: 启动计算器
  [EXECUTED] LAUNCH → Launched: calc

  🧠 Thinking: 输入计算表达式
  [EXECUTED] TYPE → Typed: "123+456"
  ...
```

### 测试3：MCP 服务器

```powershell
python src\mai_desktop_http_mcp_server.py
```

**预期结果**：
```
🚀 MAI-UI Desktop HTTP MCP Server
📡 Listening on http://127.0.0.1:3359/mcp
🤖 Model: mai-ui
```

然后用另一个终端测试 API：

```powershell
curl -X POST http://127.0.0.1:3359/mcp `
    -H "Content-Type: application/json" `
    -d '{"jsonrpc":"2.0","id":"1","method":"tools/list"}'
```

---

## 故障排查

### 问题1：虚拟环境激活失败

```powershell
# PowerShell 执行策略问题
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 问题2：LM Studio 连接失败

```powershell
# 检查 LM Studio 是否启动了 Server
# 确认端口是 1234
# 检查 Base URL 是否为 http://localhost:1234/v1
```

### 问题3：模型未加载

```powershell
# 在 LM Studio 中检查：
# 1. 模型是否已下载完成
# 2. Server 按钮是否已启动
# 3. 查看底部状态栏确认服务运行中
```

### 问题4：API 调用失败

```powershell
# 确认模型名称正确
# LM Studio 默认使用下载的模型名称
# 可以在代码中使用实际模型名，例如：
model_name="Tongyi-MAI/MAI-UI-8B-GGUF"
```

### 问题5：pyautogui 鼠标移动

```powershell
# 如果 pyautogui 导致鼠标移动不正常，禁用 fail-safe
import pyautogui
pyautogui.FAILSAFE = False
```

### 问题5：截图不工作

```powershell
# Windows 上可能需要以管理员权限运行
# 或者尝试安装 pygetwindow
pip install pygetwindow
```

---

## 退出虚拟环境

```powershell
deactivate
```

---

## 下一步

测试成功后，可以：

1. 阅读 [单步代理指南](oneshot_agent_guide.md) 了解详细用法
2. 阅读 [完整导航代理指南](desktop_agent_full_guide.md) 了解多步任务
3. 阅读 [MCP 服务器指南](mcp_server_guide.md) 了解服务集成
