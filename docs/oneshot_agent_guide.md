# 单步代理使用指南

`oneshot_agent_example.py` 提供了一个简单易用的单指令单动作自动化方案。

---

## 功能特点

- **单动作执行**: 每条指令只执行一个动作
- **无状态管理**: 不保存历史记录
- **交互式运行**: 命令行交互界面
- **自动截图**: 自动保存截图到 `screenshots/` 目录

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
pip install pyautogui pillow mss
```

---

## 快速开始

### 基本用法

```bash
cd examples
python oneshot_agent_example.py
```

### 交互示例

```
🚀 Initializing MAI-UI Desktop One-Shot Agent...
✓ Model: mai-ui
✓ Screen: 1920x1080

============================================================
MAI-UI One-Shot Agent - 单指令单动作
============================================================

每次调用只执行一个动作，无历史记录

💬 输入指令 (或 'quit' 退出): 点击任务栏左侧的记事本图标
  📸 截图中...
  🤖 预测并执行...

  🧠 思考过程: 在任务栏左侧找到记事本图标，准备点击

  🎯 执行动作: CLICK
  📋 动作详情: {"action": "click", "coordinate": [0.05, 0.98], "button": "left"}

  ✅ 执行结果: Clicked (96, 1058) with left button
```

---

## 支持的动作

| 动作 | 示例指令 |
|------|----------|
| 点击 | "点击记事本图标" |
| 输入 | "输入 Hello World" |
| 启动 | "打开计算器" |
| 滚动 | "向上滚动" |
| 等待 | "等待2秒" |

---

## 代码用法

### 直接调用

```python
from mai_desktop_oneshot_agent import MAIDesktopOneShotAgent, execute_instruction

# 方式1: 使用便捷函数
result = execute_instruction("点击记事本图标")
print(result["action"])
print(result["result"])

# 方式2: 创建代理实例
agent = MAIDesktopOneShotAgent(
    llm_base_url="http://localhost:1234/v1",
    model_name="mai-ui",
)

result = agent.run(
    instruction="点击记事本图标",
    screenshot=screenshot_image,
    execute=True,  # 是否执行动作
    confirm=False,  # 是否需要确认
)
```

### 只预测不执行

```python
result = agent.run(
    instruction="点击记事本图标",
    screenshot=screenshot_image,
    execute=False,  # 只预测，不执行
)

print(f"预测动作: {result['action']}")
print(f"思考过程: {result['thinking']}")
```

---

## 返回结果

`run()` 方法返回的字典包含：

```python
{
    "thinking": "模型思考过程",
    "action": {"action": "click", "coordinate": [x, y], "button": "left"},
    "executed": True,
    "result": "Clicked (100, 200) with left button",
    "raw_output": "原始模型输出",
    "screenshot_path": "screenshots/step_001_20250115_123456_点击记事本.png"
}
```

---

## 配置选项

```python
agent = MAIDesktopOneShotAgent(
    llm_base_url="http://localhost:1234/v1",
    model_name="mai-ui",
    screen_width=1920,        # 屏幕宽度（自动检测）
    screen_height=1080,       # 屏幕高度（自动检测）
    temperature=0.0,          # 采样温度
    max_tokens=2048,          # 最大输出长度
    save_screenshots=True,    # 是否保存截图
    screenshot_dir="screenshots",  # 截图保存目录
)
```

---

## 常见问题

### Q: 为什么动作没有执行？

A: 检查 `execute` 参数是否为 `True`：

```python
result = agent.run(instruction, screenshot, execute=True)
```

### Q: 如何查看详细日志？

A: 模型会在控制台输出坐标转换信息：

```
🔍 Raw coordinate from model: [500, 530]
🔍 Normalized coordinate: [0.26, 0.49]
🔍 Screen size: 1920x1080
```

### Q: 支持哪些应用启动？

A: 内置支持常见应用（记事本、计算器、浏览器、微信等），可通过代码添加更多。

---

## 适用场景

| 场景 | 推荐使用 |
|------|----------|
| 简单单步操作 | ✅ 推荐 |
| 快速测试模型 | ✅ 推荐 |
| 作为 API 集成 | ✅ 推荐 |
| 复杂多步任务 | ❌ 建议使用 `desktop_agent_full_example.py` |
