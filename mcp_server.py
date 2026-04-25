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
        self.server = Server("super-productivity")
        self.setup_directories()
        self.setup_logging()
        self.api_schemas = self.load_api_schemas()
        self.setup_tools()
    
    def load_api_schemas(self) -> dict:
        """Load API schemas from file"""
        schema_file = self.base_dir / 'api_schemas.json'
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
    
    def map_params(self, params: dict) -> dict:
        """No mapping needed - using camelCase from schema"""
        return params
        
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
                # Tool name = action lowercase
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
                
                # Map lowercase tool name back to proper action name
                tool_name_lower = name.lower()
                action = name
                
                # Find the proper camelCase action name from schemas
                for schema_action in self.api_schemas.keys():
                    if schema_action.lower() == tool_name_lower:
                        action = schema_action
                        break
                
                # Pass params directly
                data = self.filter_params(arguments)
                
                result = await self.send_command(action, **data)
                return [types.TextContent(type="text", text=str(result))]

            except Exception as e:
                logging.error(f"Error in tool {name}: {str(e)}")
                return [types.TextContent(type="text", text=f"Error: {str(e)}")]
    
    async def send_command(self, action: str, **kwargs) -> Dict[str, Any]:
        """Send a command to Super Productivity plugin via file-based IPC.
        
        Communication mechanism:
        1. Write command JSON to plugin_commands/ directory
        2. Plugin reads command, processes it, writes response to plugin_responses/
        3. This method polls for response file (timeout: 30 seconds)
        
        Args:
            action: The action/command name (e.g., 'addTask', 'getTasks')
            **kwargs: Additional command parameters
            
        Returns:
            Dict containing the plugin's response
        """
        command = {
            "action": action,
            "id": f"{action}_{asyncio.get_event_loop().time()}",
            "timestamp": asyncio.get_event_loop().time(),
            **kwargs
        }
        
        # Write command file
        command_file = self.command_dir / f"{command['id']}.json"
        with open(command_file, 'w') as f:
            json.dump(command, f, indent=2)
        
        logging.info(f"Sent command: {action} -> {command_file}")
        
        # Wait for response (with timeout)
        response_file = self.response_dir / f"{command['id']}_response.json"
        
        for _ in range(30):  # Wait up to 30 seconds
            if response_file.exists():
                try:
                    with open(response_file, 'r') as f:
                        response = json.load(f)
                    
                    # Clean up response file
                    response_file.unlink()
                    
                    logging.info(f"Received response for {action}: {response.get('success', 'unknown')}")
                    return response
                    
                except Exception as e:
                    logging.error(f"Error reading response file: {e}")
                    break
                    
            await asyncio.sleep(1)
        
        # Timeout
        logging.warning(f"Timeout waiting for response to {action}")
        return {"success": False, "error": "Timeout waiting for response"}
    
    async def create_task(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new task"""
        title = args.get("title", "")
        
        # Create the task data - Claude should have already converted natural language to SP syntax
        task_data = {
            "title": title,  # Use title as provided by Claude (should already have @syntax)
            "notes": args.get("notes", ""),
            "timeEstimate": args.get("time_estimate", 0),
            "projectId": args.get("project_id"),
            "parentId": args.get("parent_id"),
            "tagIds": []
        }
        
        return await self.send_command("addTask", data=task_data)
    
    async def get_tasks(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get tasks with optional server-side filtering.

        Note: SP uses IndexedDB without indexes on tagIds/projectId, so filtering
        is always O(n) whether done in SP or here. We filter server-side to reduce
        context usage when working with large task lists.
        """
        result = await self.send_command("getTasks")

        if not result.get("success"):
            return result

        tasks = result.get("data", result.get("result", []))
        if not isinstance(tasks, list):
            return result

        # Filter by tag
        tag_id = args.get("tag_id")
        if tag_id:
            tasks = [t for t in tasks if tag_id in t.get("tagIds", [])]

        # Filter by project
        project_id = args.get("project_id")
        if project_id:
            tasks = [t for t in tasks if t.get("projectId") == project_id]

        # Filter out done tasks if requested
        if not args.get("include_done", True):
            tasks = [t for t in tasks if not t.get("isDone")]

        # Update result with filtered tasks
        if "data" in result:
            result["data"] = tasks
        else:
            result["result"] = tasks

        return result
    
    async def update_task(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Update a task"""
        task_id = args.get("task_id")
        if not task_id:
            return {"success": False, "error": "task_id is required"}
        
        updates = {}
        
        # Handle title - Claude should have already converted natural language to SP syntax
        if "title" in args:
            updates["title"] = args["title"]
        
        if "notes" in args:
            updates["notes"] = args["notes"]
        if "is_done" in args:
            updates["isDone"] = args["is_done"]
            if args["is_done"]:
                updates["doneOn"] = asyncio.get_event_loop().time() * 1000
            else:
                updates["doneOn"] = None
        if "time_estimate" in args:
            updates["timeEstimate"] = args["time_estimate"]
        if "time_spent" in args:
            updates["timeSpent"] = args["time_spent"]
        
        return await self.send_command("updateTask", taskId=task_id, data=updates)
    
    async def complete_task(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Complete a task (mark as done)."""
        task_id = args.get("task_id")
        if not task_id:
            return {"success": False, "error": "task_id is required"}

        return await self.send_command("setTaskDone", taskId=task_id)

    async def reorder_tasks(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Reorder tasks using SP's native PluginAPI.reorderTasks().

        This uses SP's proper API - task order is stored in the project's taskIds[]
        array or parent task's subTaskIds[] array. Array position = priority.

        Perfect for LLM-assisted prioritization via binary comparisons.
        """
        task_ids = args.get("task_ids")
        context_id = args.get("context_id")
        context_type = args.get("context_type")

        if not task_ids:
            return {"success": False, "error": "task_ids array is required"}
        if not context_id:
            return {"success": False, "error": "context_id is required"}
        if context_type not in ["project", "task"]:
            return {"success": False, "error": "context_type must be 'project' or 'task'"}

        return await self.send_command(
            "reorderTasks",
            taskIds=task_ids,
            contextId=context_id,
            contextType=context_type
        )

    async def delete_task(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Delete tasks.
        
        Supports:
        - task_id: Delete a single task
        - task_ids: Delete multiple tasks at once
        - clear_all=true: Delete ALL tasks (including incomplete)
        - None of above: Delete all completed tasks
        """
        task_id = args.get("task_id")
        task_ids = args.get("task_ids")
        clear_all = args.get("clear_all", False)
        
        return await self.send_command(
            "deleteTasks",
            taskId=task_id,
            taskIds=task_ids,
            clearAll=clear_all
        )
    
    async def get_task(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get a single task by ID.
        
        Note: SP plugin doesn't provide getTaskById, so we fetch all tasks
        and filter client-side. This is O(n) but unavoidable with current
        plugin API.
        """
        task_id = args.get("task_id")
        if not task_id:
            return {"success": False, "error": "task_id is required"}
        
        response = await self.send_command("getTasks")
        if isinstance(response, dict) and "result" in response:
            all_tasks = response["result"]
        elif isinstance(response, list):
            all_tasks = response
        else:
            return {"success": False, "error": "Invalid response format"}
        
        if isinstance(all_tasks, list):
            for task in all_tasks:
                if task.get("id") == task_id:
                    return task
        return {"success": False, "error": "Task not found"}
    
    async def move_task_to_project(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Move a task to a different project"""
        task_id = args.get("task_id")
        project_id = args.get("project_id")
        
        if not task_id or not project_id:
            return {"success": False, "error": "task_id and project_id are required"}
        
        return await self.send_command("updateTask", taskId=task_id, data={"projectId": project_id})
    
    async def add_time_spent(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Add time spent to a task.
        
        Note: SP doesn't have an "addTimeSpent" command, so we must:
        1. Fetch current task to get existing timeSpent
        2. Calculate new total (current + add)
        3. Use updateTask to set the new total
        """
        task_id = args.get("task_id")
        time_ms = args.get("time_ms", 0)
        
        if not task_id:
            return {"success": False, "error": "task_id is required"}
        
        task = await self.get_task({"task_id": task_id})
        if isinstance(task, dict) and not task.get("success", True):
            return task
        
        current_time = task.get("timeSpent", 0) if isinstance(task, dict) else 0
        return await self.send_command("updateTask", taskId=task_id, data={"timeSpent": current_time + time_ms})
    
    async def set_time_estimate(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Set time estimate for a task"""
        task_id = args.get("task_id")
        time_ms = args.get("time_ms", 0)
        
        if not task_id:
            return {"success": False, "error": "task_id is required"}
        
        return await self.send_command("updateTask", taskId=task_id, data={"timeEstimate": time_ms})
    
    async def get_projects(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get all projects"""
        return await self.send_command("getAllProjects")
    
    async def create_project(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new project"""
        project_data = {
            "title": args.get("title", ""),
            "description": args.get("description", ""),
            "color": args.get("color", "#2196F3")
        }
        
        return await self.send_command("addProject", data=project_data)
    
    async def archive_project(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Archive a project"""
        project_id = args.get("project_id")
        if not project_id:
            return {"success": False, "error": "project_id is required"}
        
        return await self.send_command("updateProject", projectId=project_id, data={"isArchived": True})
    
    async def update_project(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Update a project"""
        project_id = args.get("project_id")
        if not project_id:
            return {"success": False, "error": "project_id is required"}
        
        updates = {}
        if args.get("title"):
            updates["title"] = args["title"]
        if args.get("description"):
            updates["description"] = args["description"]
        if args.get("color"):
            updates["color"] = args["color"]
        if args.get("is_archived") is not None:
            updates["isArchived"] = args["is_archived"]
        
        return await self.send_command("updateProject", projectId=project_id, data=updates)
    
    async def get_tags(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get all tags"""
        return await self.send_command("getAllTags")
    
    async def create_tag(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new tag"""
        tag_data = {
            "title": args.get("title", ""),
            "color": args.get("color", "#FF9800")
        }

        return await self.send_command("addTag", data=tag_data)

    async def update_tag(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing tag"""
        tag_id = args.get("tag_id")
        if not tag_id:
            return {"success": False, "error": "tag_id is required"}

        updates = {}
        if "title" in args:
            updates["title"] = args["title"]
        if "color" in args:
            updates["color"] = args["color"]
        if "icon" in args:
            updates["icon"] = args["icon"]

        return await self.send_command("updateTag", tagId=tag_id, data=updates)

    async def show_notification(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Show a notification"""
        return await self.send_command("showSnack", message=args.get("message", ""))
    
    async def batch_create_projects_with_tasks(self, projects: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Batch create projects with tasks
        
        Args:
            projects: List of projects, each containing title, color, description, tasks
        
        Returns:
            {
                "success": bool,
                "projects": [...],
                "created": int,
                "failed": int,
                "errors": []
            }
        """
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
        """Debug tool to check MCP communication directories status.
        
        Returns:
            - base_directory: Main MCP server directory
            - command_directory: Where commands are written
            - response_directory: Where responses are read
            - directories_exist: Status of each directory
        """
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
        
        # Initialize server
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="super-productivity",
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