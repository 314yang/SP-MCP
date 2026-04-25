# batch_create_projects_with_tasks Design Spec

## Overview

批量创建项目和任务，支持子任务的 MCP 工具。

## Input

```json
[
  {
    "title": "项目A",
    "color": "#2196F3",
    "description": "可选",
    "tasks": [
      {"title": "任务A1", "timeEstimate": 3600000},
      {
        "title": "任务A2",
        "subTasks": [
          {"title": "子任务A2-1"},
          {"title": "子任务A2-2"}
        ]
      }
    ]
  }
]
```

### Supported Fields

**Project**:
- `title` (required)
- `color` (optional, default: #2196F3)
- `description` (optional)
- `tasks` (optional): array of task objects

**Task**:
- `title` (required)
- `notes`, `timeEstimate`, `tagIds` 等 PluginAPI 原生字段
- `parentId`: 父��务 ID (原生支持子任务)
- `subTasks`: 简写语法，自动填充 parentId

## Processing Flow

1. 并发创建所有项目 (asyncio.gather)
2. 对每个项目，并发创建其任务 (asyncio.gather)
3. 对每个包含 subTasks 的任务，创建子任务
4. 汇总结果返回

## Output

```json
{
  "success": true,
  "projects": [
    {
      "id": "proj_1",
      "title": "项目A",
      "tasks": [
        {"id": "task_1", "title": "任务A1"},
        {"id": "task_2", "title": "任务A2", "subTasks": [
          {"id": "sub_1", "title": "子任务A2-1"},
          {"id": "sub_2", "title": "子任务A2-2"}
        ]}
      ]
    }
  ],
  "created": 5,
  "failed": 0,
  "errors": []
}
```

## Error Handling

- 单个操作失败不影响其他操作
- `errors` 数组记录每个失败的详情
- 返回 `failed` 数量统计

## Implementation

- Location: mcp_server.py
- MCP schema: 添加 batch_create_projects_with_tasks

## Cleanup

移除 plugin.js 中的冗余 batch 逻辑：
- 删除 `case 'batchOperation':` (plugin.js:694-696)
- 删除 `executeBatchOperation()` 方法 (plugin.js:736-766)

Batch 操作统一在 MCP 层处理。