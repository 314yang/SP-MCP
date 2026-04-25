# batch_create_projects_with_tasks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan step-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 添加 batch_create_projects_with_tasks 工具到 MCP server，实现批量创建项目和任务

**Architecture:** 在 mcp_server.py 中添加新的异步方法，使用 asyncio.gather 并发处理，plugin.js 清除冗余 batch 逻辑

**Tech Stack:** Python, asyncio, MCP server

---

### Task 1: 在 mcp_server.py 添加 batch_create_projects_with_tasks 方法

**Files:**
- Modify: `mcp_server.py:196-210` (在 create_task 方法后添加)

- [ ] **Step 1: 编写方法实现**

```python
async def batch_create_projects_with_tasks(self, projects: List[Dict[str, Any]]) -> Dict[str, Any]:
    """批量创建项目和任务
    
    Args:
        projects: 项目列表，每个项目包含 title, color, description, tasks
    
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
        
        # Step 1: 创建项目
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
        
        # Step 2: 递归创建任务和子任务
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
            
            return task_results
        
        task_results = await create_tasks_recursive(tasks_data)
        
        return {
            "id": project_id,
            "title": project_title,
            "tasks": task_results
        }
    
    # 并发创建所有项目
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
```

- [ ] **Step 2: 在 setup_tools 中注册工具**

在 `mcp_server.py` 的 `setup_tools()` 方法中，`debug_directories` 工具前添加：

```python
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
```

- [ ] **Step 3: 在 handle_call_tool 中添加处理逻辑**

在 `handle_call_tool` 方法中，`debug_directories` 判断后添加：

```python
elif name == "batch_create_projects_with_tasks":
    result = await self.batch_create_projects_with_tasks(arguments.get("projects", []))
    return [types.TextContent(type="text", text=json.dumps(result))]
```

- [ ] **Step 4: 提交**

```bash
git add mcp_server.py
git commit -m "feat: add batch_create_projects_with_tasks tool"
```

---

### Task 2: 清除 plugin.js 中的冗余 batch 逻辑

**Files:**
- Modify: `plugin.js:694-696`, `plugin.js:736-766`

- [ ] **Step 1: 删除 case 'batchOperation'**

删除 plugin.js 第 694-696 行：
```javascript
case 'batchOperation':
  result = await this.executeBatchOperation(command.operations);
  break;
```

- [ ] **Step 2: 删除 executeBatchOperation 方法**

删除 plugin.js 第 736-766 行的 `executeBatchOperation` 方法

- [ ] **Step 3: 提交**

```bash
git add plugin.js
git commit -m "refactor: remove redundant batchOperation from plugin.js"
```

---

### Task 3: 测试验证

**Files:**
- Test: 手动测试 batch_create_projects_with_tasks

- [ ] **Step 1: 重启 MCP server 和 plugin**

- [ ] **Step 2: 测试批量创建**

调用工具：
```json
{
  "projects": [
    {
      "title": "测试项目",
      "color": "#FF5722",
      "tasks": [
        {"title": "任务1"},
        {"title": "任务2", "subTasks": [
          {"title": "子任务2-1"},
          {"title": "子任务2-2"}
        ]}
      ]
    }
  ]
}
```

- [ ] **Step 3: 验证结果**

- 项目是否创建成功
- 任务是否创建成功
- 子任务 parentId 是否正确
- 返回的 created 数量是否正确

---

## Self-Review Checklist

- [ ] Spec coverage: 所有功能已实现
- [ ] 无 placeholder (TBD, TODO)
- [ ] 类型一致性: 方法名、参数名一致
- [ ] 错误处理完整

---

**Plan complete.** Two execution options:

**1. Subagent-Driven (recommended)** - dispatch a fresh subagent per task

**2. Inline Execution** - execute tasks in this session with checkpoints

Which approach?