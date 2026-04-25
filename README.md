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
   "super-productivity": {
     "command": "python3",
     "args": [
       "/path/to/superp_mcp/superp_mcp_server.py"
     ],
     "env": {
       "SP_MCP_BASE_DIR_LINUX": "/custom/path"
     }
   }
   ```
   - `env` is optional - defaults to system data directory

4. **Install the plugin:**
   - Open Super Productivity → Settings → Plugins
   - Click "Upload Plugin"
   - Select `superp-mcp-plugin.zip`

5. **Restart Claude Desktop**

## Data & Communication

The data directory stores plugin commands and responses. It's created automatically on first run:

- Windows: `%APPDATA%\super-productivity-mcp\`
- Linux: `~/.local/share/super-productivity-mcp/`
- macOS: `~/Library/Application Support/super-productivity-mcp/`

Override via `SP_MCP_BASE_DIR_WINDOWS` or `SP_MCP_BASE_DIR_LINUX` environment variables.

Commands are exchanged through `plugin_commands/` and `plugin_responses/` subdirectories.

## Usage

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
| `task_id` | Delete a single task by ID |
| `task_ids` | Delete multiple tasks at once |
| `clear_all` | Delete ALL tasks (including incomplete) - **use with caution** |
| Default | Delete all completed tasks if no parameters provided |

### Project Management
```
"Show me all projects"
"Create a new project called 'Website Redesign'"
"Archive the project 'Old Project'"
"Update project 'Website' with description 'New redesign'"
"Update project 'Website' with color '#FF5722'"
```

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

## Dashboard

Access the SP-MCP dashboard from the menu. The dashboard shows:
- Real-time statistics
- Connection status
- Activity logs
- Settings (polling frequency: default 2 seconds)

## Troubleshooting

### Plugin Not Loading
- Check Super Productivity version (14.0.0+ required)
- Verify plugin permissions include `nodeExecution`

### Commands Not Working
- Verify both plugin and MCP server are running
- Check file permissions on communication directories
- Check `mcp_server.log` in the data directory
