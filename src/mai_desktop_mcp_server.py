# Copyright (c) 2025, Alibaba Cloud and its affiliates;
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
MAI-UI Desktop MCP Server - Single-shot desktop automation agent.

This MCP server provides a single tool that takes a user instruction and screenshot,
then returns ONE action to perform. No history is maintained between calls.

Design Philosophy:
- Stateless: Each call is independent
- Single-action: Returns exactly one action per call
- Simple: No complex multi-step planning
"""

import base64
import json
from io import BytesIO
from typing import Any, Dict, Optional

from openai import OpenAI
from PIL import Image


class MAIDesktopMCPServer:
    """
    Single-shot desktop automation MCP server.

    This server processes one screenshot and instruction at a time,
    returning exactly one action to perform.
    """

    def __init__(
        self,
        llm_base_url: str,
        model_name: str,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ):
        """
        Initialize the MCP server.

        Args:
            llm_base_url: Base URL for the LLM API endpoint.
            model_name: Name of the model to use.
            temperature: Sampling temperature (default: 0.0 for deterministic output).
            max_tokens: Maximum tokens in response.
        """
        self.llm_base_url = llm_base_url
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens

        self.llm = OpenAI(
            base_url=self.llm_base_url,
            api_key="empty",
        )

    def _encode_image(self, image: Image.Image) -> str:
        """
        Encode PIL Image to base64 string.

        Args:
            image: PIL Image object.

        Returns:
            Base64 encoded string.
        """
        buffered = BytesIO()
        image.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode("utf-8")

    def _build_messages(
        self,
        instruction: str,
        image_base64: str,
    ) -> list:
        """
        Build messages for LLM API call.

        Args:
            instruction: User's instruction/natural language command.
            image_base64: Base64 encoded screenshot.

        Returns:
            List of message dictionaries.
        """
        system_prompt = """你是一个 Windows 桌面自动化助手。

你的任务：根据用户的指令和当前屏幕截图，返回一个动作来执行。

## 输出格式
<thinking>
简要说明：1) 你看到了什么 2) 你要执行什么操作 3) 为什么这样做能完成任务
</thinking>
<invoke>
{"action": "click|type|launch|drag|scroll|wait|terminate|answer", ...}
</invoke>

## 可用动作
- click: {"action": "click", "coordinate": [x, y], "button": "left|right"} - 点击
- type: {"action": "type", "text": "内容"} - 输入文本
- launch: {"action": "launch", "text": "应用名"} - 启动应用
- drag: {"action": "drag", "start_coordinate": [x1,y1], "end_coordinate": [x2,y2]} - 拖拽
- scroll: {"action": "scroll", "coordinate": [x, y], "direction": "up|down", "amount": 1-10} - 滚动
- wait: {"action": "wait", "duration": 秒数} - 等待
- terminate: {"action": "terminate", "status": "success"} - 任务完成
- answer: {"action": "answer", "text": "结果"} - 返回答案

## 重要规则
1. 坐标是归一化的 [0, 1] 范围，左上角是(0,0)，右下角是(1,1)
2. 只返回一个动作，不要返回多个动作
3. 仔细看截图，理解当前屏幕状态
4. 如果应用窗口不是焦点，先点击激活它
5. 在聊天应用中滚动时使用 scroll 动作，不要用 drag"""

        messages = [
            {
                "role": "system",
                "content": [{"type": "text", "text": system_prompt}],
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": instruction},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_base64}"
                        },
                    },
                ],
            },
        ]

        return messages

    def predict_action(
        self,
        instruction: str,
        screenshot: Image.Image,
    ) -> Dict[str, Any]:
        """
        Predict a single action based on instruction and screenshot.

        Args:
            instruction: User's natural language instruction.
            screenshot: Current screenshot as PIL Image.

        Returns:
            Dictionary with keys:
                - "thinking": Model's reasoning process
                - "action": Parsed action dictionary
                - "raw_output": Raw model output
        """
        # Encode image
        image_base64 = self._encode_image(screenshot)

        # Build messages
        messages = self._build_messages(instruction, image_base64)

        # Call LLM
        response = self.llm.chat.completions.create(
            model=self.model_name,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )

        raw_output = response.choices[0].message.content.strip()

        # Parse response
        result = self._parse_response(raw_output)

        result["raw_output"] = raw_output
        return result

    def _parse_response(self, text: str) -> Dict[str, Any]:
        """
        Parse model output to extract thinking and action.

        Args:
            text: Raw model output.

        Returns:
            Dictionary with "thinking" and "action" keys.
        """
        import re

        result = {
            "thinking": None,
            "action": None,
        }

        # Extract thinking
        thinking_pattern = r"<thinking>(.*?)</thinking>"
        thinking_match = re.search(thinking_pattern, text, re.DOTALL)
        if thinking_match:
            result["thinking"] = thinking_match.group(1).strip()

        # Extract action JSON
        invoke_pattern = r"<invoke>\s*(\{.*?\})\s*</invoke>"
        invoke_match = re.search(invoke_pattern, text, re.DOTALL)
        if invoke_match:
            action_json = invoke_match.group(1).strip()
            try:
                result["action"] = json.loads(action_json)
            except json.JSONDecodeError:
                result["action"] = None

        return result


# MCP Server Interface (for FastMCP or similar)
def get_server_config() -> Dict[str, Any]:
    """
    Get MCP server configuration.

    Returns:
        Dictionary with server metadata and tools.
    """
    return {
        "name": "mai-desktop-automation",
        "version": "1.0.0",
        "description": "Single-shot Windows desktop automation agent",
        "tools": [
            {
                "name": "predict_action",
                "description": "Predict a single desktop action based on instruction and screenshot",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "instruction": {
                            "type": "string",
                            "description": "User's natural language instruction",
                        },
                        "screenshot_base64": {
                            "type": "string",
                            "description": "Base64 encoded PNG screenshot",
                        },
                    },
                    "required": ["instruction", "screenshot_base64"],
                },
            }
        ],
    }


def create_tool_handler(llm_base_url: str, model_name: str):
    """
    Create a tool handler function for the MCP server.

    Args:
        llm_base_url: Base URL for the LLM API.
        model_name: Name of the model to use.

    Returns:
        Async function that handles the predict_action tool call.
    """
    server = MAIDesktopMCPServer(
        llm_base_url=llm_base_url,
        model_name=model_name,
    )

    async def predict_action_handler(arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle the predict_action tool call.

        Args:
            arguments: Tool arguments containing instruction and screenshot.

        Returns:
            Tool result with the predicted action.
        """
        instruction = arguments["instruction"]
        screenshot_base64 = arguments["screenshot_base64"]

        # Decode base64 image
        image_data = base64.b64decode(screenshot_base64)
        image = Image.open(BytesIO(image_data))

        # Predict action
        result = server.predict_action(instruction, image)

        return {
            "success": True,
            "thinking": result["thinking"],
            "action": result["action"],
        }

    return predict_action_handler


# Example usage (when not using MCP framework)
if __name__ == "__main__":
    import sys
    from pathlib import Path

    # Add src to path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    # Example configuration
    SERVER = MAIDesktopMCPServer(
        llm_base_url="http://localhost:1234/v1",
        model_name="mai-ui",
    )

    # Test with a screenshot (if available)
    print("MAI-UI Desktop MCP Server")
    print(f"Model: {SERVER.model_name}")
    print(f"API: {SERVER.llm_base_url}")
    print("\nServer ready for MCP requests")
