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
MAI-UI Desktop HTTP MCP Server - Stateless HTTP-based MCP server.

This server implements the Model Context Protocol (MCP) over standard HTTP.
It's stateless - each request is processed independently.

Usage:
    1. Start the server:
       python mai_desktop_http_mcp_server.py

    2. Configure in your MCP client (e.g., Claude Desktop):
       {
         "mcpServers": {
           "mai-desktop": {
             "url": "http://127.0.0.1:3359/mcp"
           }
         }
       }
"""

import base64
import json
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from openai import OpenAI
from PIL import Image
import uvicorn
import mss

# Import the MCP-specific prompts
from prompt_mcp import MAI_DESKTOP_MCP_PROMPT_CN

# Constants - same as Navigation Agent
SCALE_FACTOR = 999

# Screenshot directory
SCREENSHOT_DIR = Path("screenshots")
SCREENSHOT_DIR.mkdir(exist_ok=True)


def execute_action_on_desktop(action: dict) -> str:
    """
    Execute an action on the Windows desktop.

    Args:
        action: Action dictionary with 'action' type and parameters.

    Returns:
        Execution result message.
    """
    import pyautogui
    import pyperclip
    import time

    action_type = action.get("action")

    try:
        # Configure pyautogui
        pyautogui.FAILSAFE = False
        pyautogui.PAUSE = 0.25

        if action_type == "click":
            coord = action["coordinate"]
            # Convert normalized [0,1] to screen pixels
            screen_width, screen_height = pyautogui.size()
            x = int(coord[0] * screen_width)
            y = int(coord[1] * screen_height)
            button = action.get("button", "left")

            # Execute click
            pyautogui.moveTo(x, y, duration=0.2)
            pyautogui.click(x, y, button=button)

            return f"Clicked ({x}, {y}) with {button} button"

        elif action_type == "type":
            text = action["text"]
            try:
                original = pyperclip.paste()
                pyperclip.copy(text)
                time.sleep(0.1)
                pyautogui.hotkey('ctrl', 'v')
                time.sleep(0.2)
                pyperclip.copy(original)
                return f'Typed: "{text[:50]}..." if len(text) > 50 else text'
            except:
                pyautogui.write(text, interval=0.01)
                return f'Typed: "{text[:50]}..." if len(text) > 50 else text'

        elif action_type == "wait":
            duration = action.get("duration", 1)
            time.sleep(duration)
            return f"Waited {duration} seconds"

        elif action_type == "scroll":
            coord = action["coordinate"]
            # Convert normalized [0,1] to screen pixels
            screen_width, screen_height = pyautogui.size()
            x = int(coord[0] * screen_width)
            y = int(coord[1] * screen_height)
            direction = action.get("direction", "up")
            amount = action.get("amount", 3)

            # Move mouse to position first
            pyautogui.moveTo(x, y, duration=0.1)

            # Use PageUp/PageDown keys for more reliable scrolling
            # Each PageUp/PageDown scrolls approximately one screen
            key = "pageup" if direction == "up" else "pagedown"

            # Calculate number of page presses based on amount
            # amount 1-3 = 1 page, 4-6 = 2 pages, 7-10 = 3 pages, etc.
            page_presses = max(1, (amount + 2) // 3)

            for _ in range(page_presses):
                pyautogui.press(key)
                time.sleep(0.1)  # Small delay between presses

            return f"Scrolled {direction} by {amount} (used {page_presses}x {key}) at ({x}, {y})"

        else:
            return f"Unsupported action: {action_type}"

    except Exception as e:
        return f"Error executing {action_type}: {e}"


# Request/Response models for MCP JSON-RPC protocol
class MCPRequest(BaseModel):
    """MCP JSON-RPC request model."""
    jsonrpc: str = "2.0"
    id: Optional[str] = None
    method: str
    params: Optional[Dict[str, Any]] = None


class MCPTool(BaseModel):
    """MCP tool definition."""
    name: str
    description: str
    inputSchema: Dict[str, Any]


def capture_screenshot() -> str:
    """
    Capture screenshot and save to file.

    Returns:
        Absolute path to the saved screenshot file.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"screenshot_{timestamp}.png"
    filepath = SCREENSHOT_DIR / filename

    # Capture screenshot using mss
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # Primary monitor
        screenshot = sct.grab(monitor)
        img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
        img.save(filepath)

    return str(filepath.absolute())


def image_to_base64(image_path: str) -> str:
    """
    Convert image file to base64 string.

    Args:
        image_path: Path to the image file.

    Returns:
        Base64 encoded string.
    """
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


class MAIDesktopHTTPMCP:
    """
    Stateless HTTP MCP server for desktop automation.

    Each request processes:
    1. User instruction (natural language)
    2. Screenshot (base64 encoded image)
    3. Returns: ONE action to perform

    No state is maintained between requests.
    """

    def __init__(
        self,
        llm_base_url: str = "http://localhost:1234/v1",
        model_name: str = "mai-ui",
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ):
        """
        Initialize the MCP server.

        Args:
            llm_base_url: Base URL for the LLM API.
            model_name: Name of the vision model.
            temperature: Sampling temperature.
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
        """Encode PIL Image to base64 string."""
        buffered = BytesIO()
        image.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode("utf-8")

    def _normalize_action_coordinates(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize coordinates from SCALE_FACTOR range to [0, 1].

        Model outputs coordinates in [0, SCALE_FACTOR] range (0-999).
        We need to normalize them to [0, 1] range.
        """
        def should_normalize(val):
            return isinstance(val, (int, float)) and val > 1.5

        def normalize_value(val):
            if should_normalize(val):
                return val / SCALE_FACTOR
            return val

        # Normalize coordinate
        if "coordinate" in action:
            coord = action["coordinate"]
            if isinstance(coord, list) and len(coord) >= 2:
                x, y = coord[0], coord[1]
                if should_normalize(x) or should_normalize(y):
                    action["coordinate"] = [normalize_value(x), normalize_value(y)]

        # Normalize start_coordinate and end_coordinate
        for key in ["start_coordinate", "end_coordinate"]:
            if key in action:
                coord = action[key]
                if isinstance(coord, list) and len(coord) >= 2:
                    x, y = coord[0], coord[1]
                    if should_normalize(x) or should_normalize(y):
                        action[key] = [normalize_value(x), normalize_value(y)]

        return action

    def _parse_response(self, text: str) -> Dict[str, Any]:
        """Parse model output to extract thinking and action."""
        import re

        result = {"thinking": None, "action": None}

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
                # Handle both wrapped and direct format
                parsed = json.loads(action_json)
                if "arguments" in parsed:
                    action = parsed["arguments"]
                else:
                    action = parsed

                # Normalize coordinates
                action = self._normalize_action_coordinates(action)
                result["action"] = action
            except json.JSONDecodeError as e:
                print(f"Warning: Failed to parse action JSON: {e}")

        return result

    def predict_action(
        self,
        instruction: str,
        screenshot_base64: str,
    ) -> Dict[str, Any]:
        """
        Predict a single action based on instruction and screenshot.

        Args:
            instruction: User's natural language instruction.
            screenshot_base64: Base64 encoded PNG screenshot.

        Returns:
            Dictionary with:
                - "thinking": Model's reasoning
                - "action": Parsed action (normalized coordinates)
                - "raw_output": Raw model output
        """
        # Decode image
        image_data = base64.b64decode(screenshot_base64)
        image = Image.open(BytesIO(image_data))

        # Encode image for API
        image_base64 = self._encode_image(image)

        # Build messages using MCP-specific prompt
        messages = [
            {
                "role": "system",
                "content": [{"type": "text", "text": MAI_DESKTOP_MCP_PROMPT_CN}],
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": instruction},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                    },
                ],
            },
        ]

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


# Global instance
_mcp_instance: Optional[MAIDesktopHTTPMCP] = None


def get_mcp_instance() -> MAIDesktopHTTPMCP:
    """Get or create the global MCP instance."""
    global _mcp_instance
    if _mcp_instance is None:
        _mcp_instance = MAIDesktopHTTPMCP(
            llm_base_url="http://localhost:1234/v1",
            model_name="mai-ui",
        )
    return _mcp_instance


# Create FastAPI app
app = FastAPI(title="MAI-UI Desktop Automation MCP Server")


@app.post("/mcp")
async def mcp_endpoint(request: Request):
    """
    Main MCP endpoint - handles JSON-RPC requests.

    This endpoint implements the Model Context Protocol over HTTP.
    """
    body = await request.json()
    req_id = body.get("id", str(uuid.uuid4()))
    method = body.get("method")
    params = body.get("params", {})

    # Handle different MCP methods
    if method == "tools/list":
        # Return list of available tools
        tools = [
            {
                "name": "screenshot",
                "description": "Capture the current screen and save to a file. Returns the absolute path to the screenshot file.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "predict_action",
                "description": "Predict and execute a single desktop action (click/type/wait) based on instruction and screenshot. For scrolling, use the scroll_action tool instead.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "instruction": {
                            "type": "string",
                            "description": "Clear description of the target element to click or text to type. Examples: 'click the WeChat icon on the left side of taskbar', 'click the X button at top right corner to close window', 'type Hello World'"
                        },
                        "screenshot_path": {
                            "type": "string",
                            "description": "Absolute path to the screenshot file (from screenshot tool)"
                        }
                    },
                    "required": ["instruction", "screenshot_path"]
                }
            },
            {
                "name": "scroll_action",
                "description": "Predict scroll position and execute scroll. You provide direction and amount, MCP will predict the best position based on screenshot.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "instruction": {
                            "type": "string",
                            "description": "Brief description of where to scroll. Example: 'scroll the chat window', 'scroll the file list'"
                        },
                        "direction": {
                            "type": "string",
                            "enum": ["up", "down"],
                            "description": "Scroll direction: 'up' to see more history, 'down' to see newer content"
                        },
                        "amount": {
                            "type": "number",
                            "description": "Scroll amount (recommended: 3-5). Higher value = more scrolling"
                        },
                        "screenshot_path": {
                            "type": "string",
                            "description": "Absolute path to the screenshot file (from screenshot tool)"
                        }
                    },
                    "required": ["instruction", "direction", "amount", "screenshot_path"]
                }
            }
        ]
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": tools
            }
        })

    elif method == "tools/call":
        # Execute a tool call
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if tool_name == "screenshot":
            # Capture screenshot and return path
            screenshot_path = capture_screenshot()
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": screenshot_path
                        }
                    ]
                }
            })

        elif tool_name == "scroll_action":
            # Predict scroll position and execute scroll
            instruction = arguments.get("instruction", "")
            direction = arguments.get("direction", "up")
            amount = arguments.get("amount", 3)
            screenshot_path = arguments.get("screenshot_path", "")

            if not screenshot_path or not Path(screenshot_path).exists():
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32602,
                        "message": f"Screenshot file not found: {screenshot_path}"
                    }
                })

            # Use model to predict scroll position
            screenshot_base64 = image_to_base64(screenshot_path)
            server = get_mcp_instance()

            # Build instruction for position prediction
            position_instruction = f"{instruction}。滚动方向：{direction}，请在截图中找到最佳的滚动位置（通常是内容区域的中心）"

            # Get position prediction
            prediction = server.predict_action(
                instruction=position_instruction,
                screenshot_base64=screenshot_base64
            )

            predicted_action = prediction.get("action")
            thinking = prediction.get("thinking", "")

            if not predicted_action or "coordinate" not in predicted_action:
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps({
                                    "thinking": thinking,
                                    "error": "Failed to predict scroll position from screenshot",
                                    "executed": False
                                }, ensure_ascii=False, indent=2)
                            }
                        ]
                    }
                })

            coord = predicted_action["coordinate"]
            screen_width, screen_height = pyautogui.size()
            x = int(coord[0] * screen_width)
            y = int(coord[1] * screen_height)

            steps_executed = []
            try:
                # Step 1: Click to get focus (important for scroll to work)
                pyautogui.moveTo(x, y, duration=0.1)
                pyautogui.click(x, y)
                steps_executed.append(f"Clicked ({x}, {y}) to get focus")
                time.sleep(0.2)  # Wait for focus to take effect

                # Step 2: Execute scroll using PageUp/PageDown keys
                key = "pageup" if direction == "up" else "pagedown"
                page_presses = max(1, (amount + 2) // 3)

                for _ in range(page_presses):
                    pyautogui.press(key)
                    time.sleep(0.1)

                steps_executed.append(f"Scrolled {direction} using {page_presses}x {key}")

                return JSONResponse({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps({
                                    "thinking": thinking,
                                    "predicted_position": coord,
                                    "scroll_action": {
                                        "direction": direction,
                                        "amount": amount
                                    },
                                    "executed": True,
                                    "steps": steps_executed,
                                    "execution_result": f"Clicked for focus, then scrolled {direction} ({page_presses}x {key})"
                                }, ensure_ascii=False, indent=2)
                            }
                        ]
                    }
                })
            except Exception as e:
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps({
                                    "thinking": thinking,
                                    "predicted_position": coord,
                                    "scroll_action": {
                                        "direction": direction,
                                        "amount": amount
                                    },
                                    "executed": False,
                                    "error": str(e)
                                }, ensure_ascii=False, indent=2)
                            }
                        ]
                    }
                })

        elif tool_name == "predict_action":
            # Predict and execute action from instruction and screenshot
            screenshot_path = arguments.get("screenshot_path", "")
            instruction = arguments.get("instruction", "")

            if not screenshot_path or not Path(screenshot_path).exists():
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32602,
                        "message": f"Screenshot file not found: {screenshot_path}"
                    }
                })

            # Convert screenshot to base64
            screenshot_base64 = image_to_base64(screenshot_path)

            # Get prediction
            server = get_mcp_instance()
            prediction = server.predict_action(
                instruction=instruction,
                screenshot_base64=screenshot_base64
            )

            # Extract action from prediction
            action = prediction.get("action")
            thinking = prediction.get("thinking", "")

            # Prepare response with thinking and predicted action
            response_content = {
                "thinking": thinking,
                "predicted_action": action,
                "executed": False,
                "execution_result": None
            }

            # Execute the action if it's a valid action type
            if action:
                action_type = action.get("action")
                if action_type in ["click", "type", "wait"]:
                    try:
                        execution_result = execute_action_on_desktop(action)
                        response_content["executed"] = True
                        response_content["execution_result"] = execution_result
                    except Exception as e:
                        response_content["execution_result"] = f"Execution failed: {e}"
                        response_content["executed"] = False
                elif action_type == "scroll":
                    # For scroll_action tool internal use: predict position only
                    response_content["execution_result"] = "Position predicted for scroll_action tool"
                    response_content["executed"] = False
                elif action_type in ["answer", "terminate"]:
                    # These are task completion actions, no desktop execution needed
                    response_content["execution_result"] = f"Task action: {action_type} - {action.get('text', '')}"
                    response_content["executed"] = True
                else:
                    response_content["execution_result"] = f"Action not executed: {action_type}"
                    response_content["executed"] = False
            else:
                response_content["execution_result"] = "No valid action predicted"

            return JSONResponse({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(response_content, ensure_ascii=False, indent=2)
                        }
                    ]
                }
            })
        else:
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Tool not found: {tool_name}"
                }
            })

    elif method == "initialize":
        # Initialize the MCP session
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {
                    "name": "mai-desktop-automation",
                    "version": "1.0.0"
                },
                "capabilities": {
                    "tools": {}
                }
            }
        })

    else:
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}"
            }
        })


@app.get("/")
async def root():
    """Root endpoint - server info."""
    return {
        "name": "MAI-UI Desktop Automation MCP Server",
        "version": "1.0.0",
        "endpoint": "/mcp",
        "protocol": "MCP over HTTP (JSON-RPC 2.0)"
    }


def main():
    """Run the HTTP MCP server."""
    import argparse

    parser = argparse.ArgumentParser(description="MAI-UI Desktop HTTP MCP Server")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=3359,
        help="Port to bind to (default: 3359)"
    )
    parser.add_argument(
        "--llm-url",
        default="http://localhost:1234/v1",
        help="LLM API base URL"
    )
    parser.add_argument(
        "--model",
        default="mai-ui",
        help="Model name"
    )

    args = parser.parse_args()

    # Initialize the global instance with custom config
    global _mcp_instance
    _mcp_instance = MAIDesktopHTTPMCP(
        llm_base_url=args.llm_url,
        model_name=args.model,
    )

    print(f"🚀 MAI-UI Desktop HTTP MCP Server")
    print(f"📡 Listening on http://{args.host}:{args.port}/mcp")
    print(f"🤖 Model: {args.model}")
    print(f"🔗 LLM API: {args.llm_url}")
    print(f"\n💡 Configure your MCP client:")
    config_url = f"http://{args.host}:{args.port}/mcp"
    config_json = '{"mcpServers": {"mai-desktop": {"url": "' + config_url + '"}}}'
    print(f"   {config_json}\n")

    # Run the server
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()


"""
====================================================================
阶跃桌面助手使用前置提示词
====================================================================

你作为上层AI的职责：
- 理解用户的完整任务目标
- 将任务分解为清晰的操作步骤
- 给MCP发送明确的动作指令（比如"点击搜索框"、"输入文字xxx"）
- 分析每步执行结果，判断是否成功
- 决策下一步该做什么
- 维护整个任务的上下文和进度

MCP的职责：
- 接收你的指令和当前截图
- 进行视觉定位，找到目标元素
- 返回具体坐标和执行结果
- 每次调用都是独立的
"""
