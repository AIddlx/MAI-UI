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
MAI Desktop Agent - A GUI automation agent for Windows desktop environments.

This module provides the MAIDesktopNavigationAgent class that uses vision-language models
to interact with desktop interfaces based on natural language instructions.
"""

import copy
import json
import re
import traceback
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from openai import OpenAI
from PIL import Image

from base import BaseAgent
from prompt import (
    MAI_DESKTOP_SYS_PROMPT,
    MAI_DESKTOP_SYS_PROMPT_ASK_USER_MCP,
    MAI_DESKTOP_SYS_PROMPT_SIMPLE,
    MAI_DESKTOP_SYS_PROMPT_CN,
)
from unified_memory import TrajStep
from utils import pil_to_base64, safe_pil_to_bytes

# Constants
SCALE_FACTOR = 999


def mask_image_urls_for_logging(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Create a copy of messages with image URLs masked for logging.

    Args:
        messages: List of message dictionaries that may contain image URLs.

    Returns:
        Deep copy of messages with image URLs replaced by "[IMAGE_DATA]".
    """
    messages_masked = copy.deepcopy(messages)
    for message in messages_masked:
        content = message.get("content", [])
        if content and isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and "image_url" in item:
                    item["image_url"]["url"] = "[IMAGE_DATA]"
    return messages_masked


def parse_tagged_text(text: str) -> Dict[str, Any]:
    """
    Parse text containing XML-style tags to extract thinking and tool_call content.

    Args:
        text: Text containing <thinking> and <tool_call> tags.

    Returns:
        Dictionary with keys:
            - "thinking": Content inside <thinking> tags (str or None)
            - "tool_call": Parsed JSON content inside <tool_call> tags (dict or None)

    Raises:
        ValueError: If tool_call content is not valid JSON.
    """
    # Handle thinking model output format (uses </think> instead of </thinking>)
    if "</think>" in text and "</thinking>" not in text:
        text = text.replace("</think>", "</thinking>")
        text = "<thinking>" + text

    # Define regex pattern with non-greedy matching
    # Model outputs: <thinking>...</thinking>\n<invoke>\n{json}\n</invoke>
    # But sometimes model outputs: <thinking>...</thinking>\n</invoke>\n{json}\n</invoke> (wrong opening tag)
    # Use </?invoke> to match either <invoke> or </invoke>
    pattern = r"<thinking>(.*?)</thinking>.*?</?invoke>(.*?)</invoke>"

    result: Dict[str, Any] = {
        "thinking": None,
        "tool_call": None,
    }

    # Use re.DOTALL to match newlines
    match = re.search(pattern, text, re.DOTALL)
    if match:
        result = {
            "thinking": match.group(1).strip().strip('"'),
            "tool_call": match.group(2).strip().strip('"'),
        }

    # Parse tool_call as JSON
    if result["tool_call"]:
        try:
            result["tool_call"] = json.loads(result["tool_call"])
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in tool_call: {e}")

    return result


def parse_action_to_structure_output(text: str) -> Dict[str, Any]:
    """
    Parse model output text into structured action format.

    Args:
        text: Raw model output containing thinking and tool_call tags.

    Returns:
        Dictionary with keys:
            - "thinking": The model's reasoning process
            - "action_json": Parsed action with normalized coordinates

    Note:
        Coordinates are normalized to [0, 1] range by dividing by SCALE_FACTOR.
    """
    text = text.strip()

    results = parse_tagged_text(text)
    thinking = results["thinking"]
    tool_call = results["tool_call"]

    # Handle both wrapped and direct action formats
    # Wrapped: {"name": "desktop_use", "arguments": {"action": "click", ...}}
    # Direct: {"action": "click", ...}
    if "arguments" in tool_call:
        action = tool_call["arguments"]
    elif "action" in tool_call:
        action = tool_call
    else:
        raise ValueError(f"Invalid tool_call format: {tool_call}")

    # Normalize coordinates from SCALE_FACTOR range to [0, 1]
    # Check if coordinates are already normalized (all values in [0, 1])
    if "coordinate" in action:
        coordinates = action["coordinate"]
        if len(coordinates) == 2:
            point_x, point_y = coordinates
        elif len(coordinates) == 4:
            x1, y1, x2, y2 = coordinates
            point_x = (x1 + x2) / 2
            point_y = (y1 + y2) / 2
        else:
            raise ValueError(
                f"Invalid coordinate format: expected 2 or 4 values, got {len(coordinates)}"
            )
        # Only normalize if coordinates are in SCALE_FACTOR range (> 1)
        # If already normalized (in [0, 1]), keep as is
        if point_x > 1 or point_y > 1:
            point_x = point_x / SCALE_FACTOR
            point_y = point_y / SCALE_FACTOR
        action["coordinate"] = [point_x, point_y]

    if "start_coordinate" in action:
        coordinates = action["start_coordinate"]
        if len(coordinates) == 2:
            point_x, point_y = coordinates
        elif len(coordinates) == 4:
            x1, y1, x2, y2 = coordinates
            point_x = (x1 + x2) / 2
            point_y = (y1 + y2) / 2
        else:
            raise ValueError(
                f"Invalid coordinate format: expected 2 or 4 values, got {len(coordinates)}"
            )
        # Only normalize if coordinates are in SCALE_FACTOR range (> 1)
        if point_x > 1 or point_y > 1:
            point_x = point_x / SCALE_FACTOR
            point_y = point_y / SCALE_FACTOR
        action["start_coordinate"] = [point_x, point_y]

    if "end_coordinate" in action:
        coordinates = action["end_coordinate"]
        if len(coordinates) == 2:
            point_x, point_y = coordinates
        elif len(coordinates) == 4:
            x1, y1, x2, y2 = coordinates
            point_x = (x1 + x2) / 2
            point_y = (y1 + y2) / 2
        else:
            raise ValueError(
                f"Invalid coordinate format: expected 2 or 4 values, got {len(coordinates)}"
            )
        # Only normalize if coordinates are in SCALE_FACTOR range (> 1)
        if point_x > 1 or point_y > 1:
            point_x = point_x / SCALE_FACTOR
            point_y = point_y / SCALE_FACTOR
        action["end_coordinate"] = [point_x, point_y]

    return {
        "thinking": thinking,
        "action_json": action,
    }


class MAIDesktopNavigationAgent(BaseAgent):
    """
    Desktop automation agent using vision-language models.

    This agent processes screenshots and natural language instructions to
    generate GUI actions for Windows desktop automation.

    Attributes:
        llm_base_url: Base URL for the LLM API endpoint.
        model_name: Name of the model to use for predictions.
        runtime_conf: Configuration dictionary for runtime parameters.
        history_n: Number of history steps to include in context.
    """

    def __init__(
        self,
        llm_base_url: str,
        model_name: str,
        runtime_conf: Optional[Dict[str, Any]] = None,
        mcp_tools: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        Initialize the MAIDesktopNavigationAgent.

        Args:
            llm_base_url: Base URL for the LLM API endpoint.
            model_name: Name of the model to use.
            runtime_conf: Optional configuration dictionary with keys:
                - history_n: Number of history images to include (default: 3)
                - max_pixels: Maximum pixels for image processing
                - min_pixels: Minimum pixels for image processing
                - temperature: Sampling temperature (default: 0.0)
                - top_k: Top-k sampling parameter (default: -1)
                - top_p: Top-p sampling parameter (default: 1.0)
                - max_tokens: Maximum tokens in response (default: 2048)
            tools: Optional list of MCP tool definitions. Each tool should be a dict
                with 'name', 'description', and 'parameters' keys.
        """
        super().__init__()
        
        # Store MCP tools
        self.mcp_tools = mcp_tools or []

        # Set default configuration
        default_conf = {
            "history_n": 3,
            "temperature": 0.0,
            "top_k": -1,
            "top_p": 1.0,
            "max_tokens": 2048,
        }
        self.runtime_conf = {**default_conf, **(runtime_conf or {})}

        self.llm_base_url = llm_base_url
        self.model_name = model_name
        self.llm = OpenAI(
            base_url=self.llm_base_url,
            api_key="empty",
        )

        # Initialize log file
        from datetime import datetime
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = log_dir / f"agent_{timestamp}.log"

        # Write initial log info
        self._save_log("=" * 60)
        self._save_log(f"MAI-UI Desktop Agent Session - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self._save_log(f"Model: {model_name}")
        self._save_log(f"API: {llm_base_url}")
        self._save_log(f"Config: {runtime_conf}")
        self._save_log("=" * 60)

        # Extract frequently used config values
        self.temperature = self.runtime_conf["temperature"]
        self.top_k = self.runtime_conf["top_k"]
        self.top_p = self.runtime_conf["top_p"]
        self.max_tokens = self.runtime_conf["max_tokens"]
        self.history_n = self.runtime_conf["history_n"]

    def _save_log(self, message: str) -> None:
        """
        Save detailed log message to log file.

        Args:
            message: Log message to save.
        """
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(message + "\n")
        except Exception:
            pass  # Silently ignore log errors

    @property
    def system_prompt(self) -> str:
        """
        Generate the system prompt based on available MCP tools.

        Returns:
            System prompt string, with MCP tools section if tools are configured.
        """
        if self.mcp_tools:
            mcp_tools_str = "\n".join(
                [json.dumps(tool, ensure_ascii=False) for tool in self.mcp_tools]
            )
            return MAI_DESKTOP_SYS_PROMPT_ASK_USER_MCP.render(tools=mcp_tools_str)
        # Use Chinese prompt for better Chinese user experience
        return MAI_DESKTOP_SYS_PROMPT_CN

    @property
    def history_responses(self) -> List[str]:
        """
        Generate formatted history responses for context.

        Returns:
            List of formatted response strings with thinking and tool_call tags.
        """
        history_responses = []

        for step in self.traj_memory.steps:
            thinking = step.thought
            structured_action = step.structured_action

            if not structured_action:
                continue

            action_json = copy.deepcopy(structured_action.get("action_json", {}))

            # Convert normalized coordinates back to SCALE_FACTOR range
            if "coordinate" in action_json:
                coordinates = action_json.get("coordinate", [])
                if len(coordinates) == 2:
                    point_x, point_y = coordinates
                elif len(coordinates) == 4:
                    x1, y1, x2, y2 = coordinates
                    point_x = (x1 + x2) / 2
                    point_y = (y1 + y2) / 2
                else:
                    continue
                action_json["coordinate"] = [
                    int(point_x * SCALE_FACTOR),
                    int(point_y * SCALE_FACTOR),
                ]

            tool_call_dict = {
                "name": "desktop_use",
                "arguments": action_json,
            }
            tool_call_json = json.dumps(tool_call_dict, separators=(",", ":"))
            # Skip empty thinking to prevent propagation of empty tags
            thinking_content = thinking if thinking else "(proceeding with action)"
            history_responses.append(
                f"<thinking>\n{thinking_content}\n</thinking>\n<invoke>\n{tool_call_json}\n</invoke>"
            )

        return history_responses


    def mem2response(self, step: TrajStep) -> str:
        thinking = step.thought
        structured_action = step.structured_action

        if not structured_action:
            raise ValueError("No structured action found")

        action_json = copy.deepcopy(structured_action.get("action_json", {}))

        # Convert normalized coordinates to SCALE_FACTOR range for model output
        # Use a heuristic: if coordinates are small (< 1.5), they're normalized and need scaling
        def convert_coord(coord_list):
            if len(coord_list) == 2:
                x, y = coord_list
                # Check if already in SCALE_FACTOR range (if values > 1.5, assume already scaled)
                if x < 1.5 and y < 1.5:
                    return [int(x * SCALE_FACTOR), int(y * SCALE_FACTOR)]
                return [int(x), int(y)]
            elif len(coord_list) == 4:
                x1, y1, x2, y2 = coord_list
                if x1 < 1.5 and y1 < 1.5:
                    return [int(x1 * SCALE_FACTOR), int(y1 * SCALE_FACTOR),
                            int(x2 * SCALE_FACTOR), int(y2 * SCALE_FACTOR)]
                return [int(x1), int(y1), int(x2), int(y2)]
            return coord_list

        if "coordinate" in action_json:
            action_json["coordinate"] = convert_coord(action_json["coordinate"])
        if "start_coordinate" in action_json:
            action_json["start_coordinate"] = convert_coord(action_json["start_coordinate"])[:2]
        if "end_coordinate" in action_json:
            action_json["end_coordinate"] = convert_coord(action_json["end_coordinate"])[:2]

        tool_call_dict = {
            "name": "desktop_use",
            "arguments": action_json,
        }
        tool_call_json = json.dumps(tool_call_dict, separators=(",", ":"))
        # Skip empty thinking to prevent propagation of empty tags
        thinking_content = thinking if thinking else "(proceeding with action)"
        return f"<thinking>\n{thinking_content}\n</thinking>\n<invoke>\n{tool_call_json}\n</invoke>"

    def mem2ask_user_response(self, step: TrajStep) -> str:
        return step.ask_user_response

    def mem2mcp_response(self, step: TrajStep) -> str:
        return step.mcp_response

    def mem2execution_result(self, step: TrajStep) -> str:
        """Get execution result/conclusion from a trajectory step."""
        return step.conclusion

    def _prepare_images(self, screenshot_bytes: bytes) -> List[Image.Image]:
        """
        Prepare current screenshot as PIL Image.

        Args:
            screenshot_bytes: Current screenshot as bytes.

        Returns:
            List containing single PIL Image (current screenshot only).
        """
        # Convert bytes to PIL Image
        if isinstance(screenshot_bytes, bytes):
            image = Image.open(BytesIO(screenshot_bytes))
        elif isinstance(screenshot_bytes, Image.Image):
            image = screenshot_bytes
        else:
            raise TypeError(f"Expected bytes or PIL Image, got {type(screenshot_bytes)}")

        if image.mode != "RGB":
            image = image.convert("RGB")

        return [image]

    def _build_messages(
        self,
        instruction: str,
        images: List[Image.Image],
    ) -> List[Dict[str, Any]]:
        """
        Build the message list for the LLM API call.

        Args:
            instruction: Task instruction from user.
            images: List containing single current screenshot image.
        Returns:
            List of message dictionaries for the API.
        """
        messages = [
            {
                "role": "system",
                "content": [{"type": "text", "text": self.system_prompt}],
            },
            {
                "role": "user",
                "content": [{"type": "text", "text": instruction}],
            },
        ]

        # Add history (assistant responses, execution results, etc.)
        for step in self.traj_memory.steps:
            # Add the assistant response (thinking + action)
            history_response = self.mem2response(step)
            messages.append({
                "role": "assistant",
                "content": [{"type": "text", "text": history_response}],
            })

            # Add ask_user_response or mcp_response if present
            ask_user_response = self.mem2ask_user_response(step)
            if ask_user_response:
                messages.append({
                    "role": "user",
                    "content": [{"type": "text", "text": ask_user_response}],
                })
            mcp_response = self.mem2mcp_response(step)
            if mcp_response:
                messages.append({
                    "role": "user",
                    "content": [{"type": "text", "text": mcp_response}],
                })
            # Add execution result if present (feedback from action execution)
            execution_result = self.mem2execution_result(step)
            if execution_result:
                messages.append({
                    "role": "user",
                    "content": [{"type": "text", "text": f"[EXECUTION RESULT]: {execution_result}"}],
                })

        # Add current screenshot (only one image - the current desktop state)
        cur_image = images[0]
        encoded_string = pil_to_base64(cur_image)
        messages.append({
            "role": "user",
            "content": [{
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{encoded_string}"},
            }],
        })

        return messages

    def predict(
        self,
        instruction: str,
        obs: Dict[str, Any],
        **kwargs: Any,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Predict the next action based on the current observation.

        Args:
            instruction: Task instruction/goal.
            obs: Current observation containing:
                - screenshot: PIL Image or bytes of current screen
                - ask_user_response: Optional response from asking user
                - mcp_response: Optional response from MCP tools
                - execution_result: Optional result from previous action execution (feedback)
        Returns:
            Tuple of (prediction_text, action_dict) where:
                - prediction_text: Raw model response or error message
                - action_dict: Parsed action dictionary
        """
        # Set task goal if not already set
        if not self.traj_memory.task_goal:
            self.traj_memory.task_goal = instruction

        # Log step info
        step_num = len(self.traj_memory.steps)
        self._save_log(f"\n{'='*60}")
        self._save_log(f"Step {step_num}: {instruction}")
        self._save_log(f"{'='*60}")

        # Process screenshot
        screenshot_pil = obs["screenshot"]
        screenshot_bytes = safe_pil_to_bytes(screenshot_pil)

        # Prepare images
        images = self._prepare_images(screenshot_bytes)

        # Build messages
        messages = self._build_messages(instruction, images)

        # Make API call with retry logic
        max_retries = 3
        prediction = None
        action_json = None

        for attempt in range(max_retries):
            try:
                messages_print = mask_image_urls_for_logging(messages)
                self._save_log(f"\nMessages (attempt {attempt + 1}):\n{messages_print}")
                print(f"  → Calling model...", end="", flush=True)

                response = self.llm.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    top_p=self.top_p,
                    frequency_penalty=0.0,
                    presence_penalty=0.0,
                    extra_body={"repetition_penalty": 1.0, "top_k": self.top_k},
                    seed=42,
                )
                prediction = response.choices[0].message.content.strip()
                self._save_log(f"Raw response:\n{prediction}\n")

                # Parse response
                parsed_response = parse_action_to_structure_output(prediction)
                thinking = parsed_response["thinking"]
                action_json = parsed_response["action_json"]
                self._save_log(f"Parsed response:\n{parsed_response}\n")
                print(f" ✓")

                # 重复动作检测 - 防止AI无限循环执行相同动作
                if len(self.traj_memory.steps) > 0:
                    last_step = self.traj_memory.steps[-1]
                    last_action = last_step.action
                    current_action_type = action_json.get("action", "")

                    # 对于连续的type/click/launch动作，检查是否重复
                    if last_action and current_action_type == last_action.get("action", ""):
                        is_duplicate = False
                        if current_action_type == "click":
                            last_coord = last_action.get("coordinate", [])
                            curr_coord = action_json.get("coordinate", [])
                            if len(last_coord) == 2 and len(curr_coord) == 2:
                                dist = ((last_coord[0] - curr_coord[0])**2 + (last_coord[1] - curr_coord[1])**2)**0.5
                                if dist < 0.03:  # 小于3%屏幕距离视为重复
                                    is_duplicate = True
                        elif current_action_type == "type":
                            last_text = last_action.get("text", "")
                            curr_text = action_json.get("text", "")
                            # 简单比较：如果文本完全相同就是重复
                            if last_text == curr_text and last_text:
                                is_duplicate = True
                        elif current_action_type == "launch":
                            last_text = last_action.get("text", "").lower()
                            curr_text = action_json.get("text", "").lower()
                            if last_text == curr_text:
                                is_duplicate = True

                        if is_duplicate:
                            self._save_log(f"⚠️ DUPLICATE ACTION BLOCKED: {current_action_type}\n")
                            print(f" ✓")
                            print(f"  ⛔ 重复动作被阻止：上一步已执行过相同动作")
                            # 返回提示动作，告诉AI要前进
                            action_json = {"action": "wait", "duration": 2.0}
                            prediction = f"<thinking>{thinking}</thinking> ⛔ 重复动作被阻止"
                            break

                break

            except Exception as e:
                self._save_log(f"Error on attempt {attempt + 1}: {e}\n{traceback.format_exc()}\n")
                print(f" ✗")
                print(f"  Error: {e}")
                prediction = None
                action_json = None

        # Return error if all retries failed
        if prediction is None or action_json is None:
            self._save_log("Max retry attempts reached, returning error flag.\n")
            print("Max retry attempts reached, returning error flag.")
            return "llm client error", {"action": None}

        # Create and store trajectory step
        # Get execution result from obs (feedback from previous action execution)
        execution_result = obs.get("execution_result", "")
        if not execution_result:
            execution_result = ""  # Empty if no execution result provided

        traj_step = TrajStep(
            screenshot=screenshot_pil,
            accessibility_tree=obs.get("accessibility_tree"),
            prediction=prediction,
            action=action_json,
            conclusion=execution_result,  # Store execution result as conclusion
            thought=thinking,
            step_index=len(self.traj_memory.steps),
            agent_type="MAIDesktopAgent",
            model_name=self.model_name,
            screenshot_bytes=screenshot_bytes,
            structured_action={"action_json": action_json},
        )
        self.traj_memory.steps.append(traj_step)

        return prediction, action_json

    def reset(self, runtime_logger: Any = None) -> None:
        """
        Reset the trajectory memory for a new task.

        Args:
            runtime_logger: Optional logger (unused, kept for API compatibility).
        """
        super().reset()


