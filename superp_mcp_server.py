#!/usr/bin/env python3
# MCP Server for Super Productivity Integration

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions


class SuperProductivityMCPServer:
    def __init__(self):
        self.server = Server("sp")
        self.setup_directories()
        self.setup_logging()
        self.api_schemas = self.load_api_schemas()
        self.setup_tools()
    
    def load_api_schemas(self) -> dict:
        """Load API schemas from superp_mcp_server.py 同目录"""
        schema_file = Path(__file__).parent / 'superp_mcp_schemas.json'
        if schema_file.exists():
            try:
                with open(schema_file) as f:
                    schemas = json.load(f)
                logging.info(f"Loaded API schemas from {schema_file}")
                return schemas
            except Exception as e:
                logging.warning(f"Failed to load schemas: {e}")
        
        return {}
    
    def reload_api_schemas(self):
        """Reload API schemas from file"""
        self.api_schemas = self.load_api_schemas()
        logging.info("Reloaded API schemas")
    
    def filter_params(self, data: dict) -> dict:
        """Filter null values"""
        if not data:
            return {}
        return {k: v for k, v in data.items() if v is not None}
    
    def setup_directories(self):
        """Set up communication directories for MCP server.
        
        Can be overridden via environment variables:
        - SP_MCP_BASE_DIR_WINDOWS: Base directory for Windows. default: %APPDATA%
        - SP_MCP_BASE_DIR_LINUX: Base directory for Linux/WSL. default: $XDG_DATA_HOME or ~/.local/share
        
        Directory structure:
        - super-productivity-mcp/          # base directory
          - plugin_commands/               # commands sent to plugin
          - plugin_responses/             # responses received from plugin
        """
        if os.name == 'nt':  # Windows
            data_dir = os.environ.get('SP_MCP_BASE_DIR_WINDOWS')
            if not data_dir:
                data_dir = os.environ.get('APPDATA', os.path.expanduser('~/AppData/Roaming'))
        else:  # Linux/Mac
            data_dir = os.environ.get('SP_MCP_BASE_DIR_LINUX')
            if not data_dir:
                data_dir = os.environ.get('XDG_DATA_HOME', os.path.expanduser('~/.local/share'))
        
        self.base_dir = Path(data_dir) / 'super-productivity-mcp'
        self.command_dir = self.base_dir / 'plugin_commands'
        self.response_dir = self.base_dir / 'plugin_responses'
        
        # Create directories
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.command_dir.mkdir(parents=True, exist_ok=True)
        self.response_dir.mkdir(parents=True, exist_ok=True)
        
        logging.info(f"MCP Server using directory: {self.base_dir}")
        logging.info(f"Command directory: {self.command_dir}")
        logging.info(f"Response directory: {self.response_dir}")
        
        
    def setup_logging(self):
        log_file = self.base_dir / 'mcp_server.log'
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stderr)
            ]
        )
        
    def setup_tools(self):
        """Set up MCP tools"""
        
        @self.server.list_tools()
        async def handle_list_tools() -> List[types.Tool]:
            tools = []
            for action, schema in self.api_schemas.items():
                tool_name = action.lower()
                description = f"Call {action} via PluginAPI"
                tools.append(types.Tool(
                    name=tool_name,
                    description=description,
                    inputSchema=schema
                ))
            tools.append(types.Tool(
                name="batch_create_projects_with_tasks",
                description="Batch create projects with tasks. Supports nested subTasks.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "projects": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "color": {"type": "string"},
                                    "description": {"type": "string"},
                                    "tasks": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "title": {"type": "string"},
                                                "notes": {"type": "string"},
                                                "timeEstimate": {"type": "number"},
                                                "parentId": {"type": "string"},
                                                "subTasks": {"type": "array"}
                                            }
                                        }
                                    }
                                },
                                "required": ["title"]
                            }
                        }
                    },
                    "required": ["projects"]
                }
            ))
            tools.append(types.Tool(
                name="debug_directories",
                description="Debug directories",
                inputSchema={"type": "object", "properties": {}}
            ))
            return tools
        
        @self.server.call_tool()
        async def handle_call_tool(
            name: str, arguments: Dict[str, Any]
        ) -> List[types.TextContent]:
            """Handle tool calls"""
            try:
                if name == "batch_create_projects_with_tasks":
                    result = await self.batch_create_projects_with_tasks(arguments.get("projects", []))
                    return [types.TextContent(type="text", text=json.dumps(result))]
                
                if name == "debug_directories":
                    result = await self.debug_directories(arguments)
                    return [types.TextContent(type="text", text=str(result))]
                
                action = None
                for schema_action in self.api_schemas.keys():
                    if name.lower() == schema_action.lower():
                        action = schema_action
                        break
                
                if not action:
                    return [types.TextContent(type="text", text=f"Unknown tool: {name}")]
                
                data = self.filter_params(arguments)
                result = await self.send_command(action, **data)
                return [types.TextContent(type="text", text=str(result))]

            except Exception as e:
                logging.error(f"Error in tool {name}: {str(e)}")
                return [types.TextContent(type="text", text=f"Error: {str(e)}")]
    
    async def send_command(self, action: str, **kwargs) -> Dict[str, Any]:
        """Send a command to Super Productivity plugin via file-based IPC."""
        command = {
            "action": action,
            "id": f"{action}_{asyncio.get_event_loop().time()}",
            "timestamp": asyncio.get_event_loop().time(),
            **kwargs
        }
        
        command_file = self.command_dir / f"{command['id']}.json"
        with open(command_file, 'w') as f:
            json.dump(command, f, indent=2)
        
        logging.info(f"Sent command: {action} -> {command_file}")
        
        response_file = self.response_dir / f"{command['id']}_response.json"
        
        for _ in range(30):
            if response_file.exists():
                try:
                    with open(response_file, 'r') as f:
                        response = json.load(f)
                    
                    response_file.unlink()
                    logging.info(f"Received response for {action}: {response.get('success', 'unknown')}")
                    return response
                    
                except Exception as e:
                    logging.error(f"Error reading response file: {e}")
                    break
                    
            await asyncio.sleep(1)
        
        logging.warning(f"Timeout waiting for response to {action}")
        return {"success": False, "error": "Timeout waiting for response"}
    
    async def batch_create_projects_with_tasks(self, projects: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Batch create projects with tasks"""
        results = []
        errors = []
        created = 0
        failed = 0
        
        async def create_project_with_tasks(project_data: Dict[str, Any]) -> Dict[str, Any]:
            nonlocal created, failed
            
            project_title = project_data.get("title", "")
            tasks_data = project_data.get("tasks", [])
            
            project_result = await self.send_command("addProject", data={
                "title": project_title,
                "description": project_data.get("description", ""),
                "color": project_data.get("color", "#2196F3")
            })
            
            if not project_result.get("success"):
                failed += 1
                errors.append({"type": "project", "title": project_title, "error": project_result.get("error")})
                return {"title": project_title, "error": project_result.get("error")}
            
            project_id = project_result.get("result") or project_result.get("id")
            
            async def create_tasks_recursive(tasks: List[Dict], parent_id: str = None) -> List[Dict]:
                nonlocal created, failed
                task_results = []
                
                for task_data in tasks:
                    sub_tasks = task_data.pop("subTasks", [])
                    task_data["projectId"] = project_id
                    if parent_id:
                        task_data["parentId"] = parent_id
                    
                    task_result = await self.send_command("addTask", data=task_data)
                    
                    if task_result.get("success"):
                        task_id = task_result.get("result") or task_result.get("id")
                        created += 1
                        sub_results = await create_tasks_recursive(sub_tasks, task_id)
                        task_results.append({
                            "id": task_id,
                            "title": task_data.get("title"),
                            "subTasks": sub_results
                        })
                    else:
                        failed += 1
                        errors.append({"type": "task", "title": task_data.get("title"), "error": task_result.get("error")})
                    
                    task_data["subTasks"] = sub_tasks
                
                return task_results
            
            task_results = await create_tasks_recursive(tasks_data)
            
            return {
                "id": project_id,
                "title": project_title,
                "tasks": task_results
            }
        
        project_results = await asyncio.gather(*[
            create_project_with_tasks(p) for p in projects
        ], return_exceptions=True)
        
        for result in project_results:
            if isinstance(result, Exception):
                failed += 1
                errors.append({"type": "project", "error": str(result)})
            else:
                results.append(result)
        
        return {
            "success": failed == 0,
            "projects": results,
            "created": created,
            "failed": failed,
            "errors": errors
        }
    
    async def debug_directories(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Debug tool to check MCP communication directories status."""
        return {
            "success": True,
            "base_directory": str(self.base_dir),
            "command_directory": str(self.command_dir),
            "response_directory": str(self.response_dir),
            "directories_exist": {
                "base": self.base_dir.exists(),
                "commands": self.command_dir.exists(),
                "responses": self.response_dir.exists()
            }
        }
    
    async def run(self):
        """Run the MCP server"""
        logging.info("Starting Super Productivity MCP Server...")
        
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="sp",
                    server_version="1.0.0",
                    capabilities=self.server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )


async def main():
    """Main entry point"""
    server = SuperProductivityMCPServer()
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())