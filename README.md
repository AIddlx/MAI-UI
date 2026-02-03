# MAI-UI 桌面自动化

基于 MAI-UI 视觉模型的 Windows 桌面自动化工具，支持点击、输入、滚动等操作。

---

## 快速开始

### 1. 安装 LM Studio

访问 [lmstudio.ai](https://lmstudio.ai/) 下载并安装。

### 2. 下载模型

```
视觉模型:
https://hf-mirror.com/mradermacher/MAI-UI-8B-GGUF/resolve/main/MAI-UI-8B.Q8_0.gguf?download=true

文本模型:
https://hf-mirror.com/mradermacher/MAI-UI-8B-GGUF/resolve/main/MAI-UI-8B.mmproj-Q8_0.gguf?download=true
```

下载后放在同一目录，在 LM Studio 中加载 `MAI-UI-8B.Q8_0.gguf`。

### 3. 启动模型服务

在 LM Studio 中点击 **Server** → **Start Server**

### 4. 安装依赖

```bash
pip install -r requirements.txt
```

---

## 使用方式

### 方式一：单步代理（简单单动作）

适合快速执行单个操作。

```bash
cd examples
python oneshot_agent_example.py
```

**示例**：
```
💬 输入指令: 点击开始按钮
✓ 已点击
```

---

### 方式二：完整代理（多步任务）

适合复杂多步骤任务，自动执行直到完成。

```bash
cd examples
python desktop_agent_full_example.py
```

**示例**：
```
💬 输入指令: 打开记事本并输入Hello
✓ 启动记事本
✓ 输入文本
✓ 任务完成
```

---

### 方式三：MCP 服务器（阶跃 AI 桌面助手）

作为 MCP 服务集成到阶跃 AI 桌面助手。

#### 启动服务器

```bash
python src\mai_desktop_http_mcp_server.py
```

#### 配置阶跃 AI 桌面助手

在阶跃 AI 桌面助手的 MCP 设置中添加：

```json
{
  "mcpServers": {
    "mai-desktop": {
      "url": "http://127.0.0.1:3359/mcp"
    }
  }
}
```

重启阶跃 AI 桌面助手后即可使用。

---

## 三个方式的区别

| 方式 | 文件 | 特点 | 适用场景 |
|------|------|------|----------|
| 单步代理 | `oneshot_agent_example.py` | 每次执行一个动作，无历史 | 简单操作、快速测试 |
| 完整代理 | `desktop_agent_full_example.py` | 多步自动执行，有历史反馈 | 复杂多步骤任务 |
| MCP服务器 | `mai_desktop_http_mcp_server.py` | 作为服务供 AI 调用 | 集成到阶跃等 AI 助手 |

---

## 完整文档

详细使用指南请查看 [docs](docs) 目录：

- [安装与测试指南](docs/setup_and_test.md)
- [单步代理指南](docs/oneshot_agent_guide.md)
- [完整代理指南](docs/desktop_agent_full_guide.md)
- [MCP 服务器指南](docs/mcp_server_guide.md)
