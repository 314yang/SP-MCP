# SP-MCP

Bridge between the amazing [Super Productivity](https://github.com/johannesjo/super-productivity/) app and MCP (Model Context Protocol) servers for Claude Desktop integration.

This MCP and plugin allows Claude Desktop to directly interact with Super Productivity through the MCP protocol. Create, update, tasks, manage projects and tags, and get information from Super Productivity.

Make sure to backup your Super Productivity before using in case of data loss.

## Requirements

- Super Productivity 14.0.0 or higher
- Claude Desktop
- Python 3.8 or higher

## Installation

1. Download `superp_mcp.zip` from GitHub releases
2. Extract to current directory:
   ```bash
   unzip superp_mcp.zip
   ```

3. Configure Claude Desktop:
   ```json
   "sp": {
     "command": "python3",
     "args": [
       "/path/to/superp_mcp/superp_mcp_server.py"
     ]
   }
   ```

4. **Install the plugin:**
   - Open Super Productivity → Settings → Plugins
   - Click "Upload Plugin"
   - Select `superp-mcp-plugin.zip`

5. **Restart Claude Desktop**

6. **Configure data directory (optional):**
   - Open SP-MCP Dashboard from the Super Productivity menu
   - Enter your desired base directory path
   - Supports `%APPDATA%` (Windows) or custom paths

## Data & Communication

The data directory stores plugin commands and responses. It's created automatically on first run:

- Windows: `%APPDATA%\super-productivity-mcp\`
- Linux: `~/.local/share/super-productivity-mcp/`
- macOS: `~/Library/Application Support/super-productivity-mcp/`

Commands are exchanged through `plugin_commands/` and `plugin_responses/` subdirectories.

### Configuration

**MCP Server** - Configure via environment variables:
```json
"sp": {
  "command": "python3",
  "args": ["/path/to/superp_mcp/superp_mcp_server.py"],
  "env": {
    "SP_MCP_BASE_DIR_WINDOWS": "D:\\mcp-data",
    "SP_MCP_BASE_DIR_LINUX": "/home/user/mcp-data"
  }
}
```

**Plugin Dashboard** - Configure separately from the Super Productivity menu:
- Open SP-MCP Dashboard
- Enter base directory path (e.g., `D:\mcp-data` on Windows, `/home/user/mcp-data` on Linux)

**Important**: Both MCP server and plugin must use the same directory path to communicate. Configure them separately but identically.

## Usage

All tools use camelCase names matching the Super Productivity PluginAPI actions (e.g., `addtask`, `deletetask`, `deleteproject`).

### Creating Tasks
```
"Create a task to review the quarterly budget #finance +work"
```

### Task Management
```
"Show me all my tasks"
"Mark the budget review task as complete"
"Update the task 'Meeting prep' with notes about the agenda"
"Delete the task 'Old task title'"
"Delete all completed tasks"
"Delete tasks with IDs ['task-id-1', 'task-id-2']"
"Get task by ID"
"Move task to project 'Website Redesign'"
"Add 30 minutes to the 'Research' task"
"Set 2 hours time estimate for 'Design review'"
```

#### Task Deletion Options
| Option | Description |
|--------|-------------|
| `taskId` | Delete a single task by ID |
| `taskIds` | Delete multiple tasks at once |
| `clearAll` | Delete ALL tasks (including incomplete) - **use with caution** |
| Default | Delete all completed tasks if no parameters provided |

#### Delete Tasks in Project
Delete all tasks belonging to a specific project:
```json
{
  "projectId": "项目ID"
}
```

### Project Management
```
"Show me all projects"
"Create a new project called 'Website Redesign'"
"Archive the project 'Old Project'"
"Update project 'Website' with description 'New redesign'"
"Update project 'Website' with color '#FF5722'"
```

> **Note**: Direct project deletion is not supported via PluginAPI. Use archive instead, or delete in the Super Productivity UI.

### Tag Management
```
"Show me all tags"
"Create a new tag called 'urgent'"
"Update tag 'urgent' with color '#FF0000'"
```

### Notifications
```
"Show notification 'Task completed!'"
```

### Batch Operations
```
"Batch create projects with tasks"
```

## Dashboard

Access the SP-MCP dashboard from the Super Productivity menu. The dashboard shows:
- Real-time statistics
- Connection status
- Activity logs
- MCP directories (MCP Directory, Commands Dir, Responses Dir)
- Settings configuration

### Base Directory Configuration

Configure the MCP data directory separately from the MCP server:

1. Open the SP-MCP Dashboard from the menu
2. Enter your base directory path in the "Base Directory" field:
   - **Windows**: Custom path like `D:\mcp-data` (use `%APPDATA%` for standard location)
   - **Linux**: Custom path like `/home/user/mcp-data`

3. Press Enter or click outside the input field to save

The configured path creates the `super-productivity-mcp/` subdirectory with `plugin_commands/` and `plugin_responses/` folders.

**Note**: The plugin dashboard and MCP server have separate configurations. For them to communicate, you must configure both to use the same directory path.

## Troubleshooting

### Plugin Not Loading
- Check Super Productivity version (14.0.0+ required)
- Verify plugin permissions include `nodeExecution`

### Commands Not Working
- Verify both plugin and MCP server are running
- Check file permissions on communication directories
- Check `mcp_server.log` in the data directory