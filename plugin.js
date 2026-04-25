// MCP Bridge Plugin for Super Productivity

class MCPBridgePlugin {
  constructor() {
    this.mcpServerPath = null;
    this.commandWatchInterval = null;
    this.lastProcessedCommand = 0;
    this.isInitialized = false;
    this.commandQueue = [];
    this.lastNoCommandsLog = 0;
    
// Configuration
    this.config = {
      commandCheckIntervalMs: 2000,
      mcpCommandDir: null,          
      mcpResponseDir: null,         
      debugMode: true,
      maxConcurrentCommands: 5,
      configFile: null,
      baseDir: null
    };

    // Statistics
    this.stats = {
      commandsProcessed: 0,
      lastCommandTime: null,
      errors: 0,
      startTime: Date.now()
    };
  }

  async initializeConfigPath() {
    try {
      const result = await PluginAPI.executeNodeScript({
        script: `
          const fs = require('fs');
          const path = require('path');
          const os = require('os');
          
          // Determine data directory based on platform
          let dataDir;
          if (os.platform() === 'win32') {
            dataDir = path.join(os.homedir(), 'AppData', 'Roaming');
          } else {
            dataDir = path.join(os.homedir(), '.local', 'share');
          }
          
          const mcpDir = path.join(dataDir, 'super-productivity-mcp');
          const configFile = path.join(mcpDir, 'mcp_bridge_config.json');
          
          return { success: true, configFile: configFile };
        `,
        timeout: 5000
      });
      
      if (result && result.success && result.result && result.result.success) {
        this.config.configFile = result.result.configFile;
        return true;
      }
    } catch (error) {
      await this.log(`Failed to initialize config path: ${error.message}`);
    }
    return false;
  }

  async loadConfig() {
    // Ensure config path is set
    if (!this.config.configFile) {
      await this.initializeConfigPath();
    }
    
    try {
      const result = await PluginAPI.executeNodeScript({
        script: `
          const fs = require('fs');
          const path = require('path');
          
          const configFile = args[0];
          
          try {
            if (fs.existsSync(configFile)) {
              const configData = fs.readFileSync(configFile, 'utf8');
              return { success: true, config: JSON.parse(configData) };
            } else {
              // Return default config
              return { 
                success: true, 
                config: { 
                  commandCheckIntervalMs: 2000, 
                  baseDir: null 
                } 
              };
            }
          } catch (error) {
            return { success: false, error: error.message };
          }
        `,
        args: [this.config.configFile],
        timeout: 5000
      });
      
      if (result && result.success && result.result && result.result.success) {
        const savedConfig = result.result.config;
        this.config.commandCheckIntervalMs = savedConfig.commandCheckIntervalMs || 2000;
        this.config.baseDir = savedConfig.baseDir || null;
        return true;
      }
    } catch (error) {
      await this.log(`Failed to load config: ${error.message}`);
    }
    return false;
  }

  async saveConfig() {
    // Ensure config path is set
    if (!this.config.configFile) {
      await this.initializeConfigPath();
    }
    
    try {
      const configData = {
        commandCheckIntervalMs: this.config.commandCheckIntervalMs,
        baseDir: this.config.baseDir
      };
      
      const result = await PluginAPI.executeNodeScript({
        script: `
          const fs = require('fs');
          
          const configFile = args[0];
          const configData = args[1];
          
          try {
            fs.writeFileSync(configFile, JSON.stringify(configData, null, 2));
            return { success: true };
          } catch (error) {
            return { success: false, error: error.message };
          }
        `,
        args: [this.config.configFile, configData],
        timeout: 5000
      });
      
      if (result && result.success && result.result && result.result.success) {
        return true;
      }
    } catch (error) {
      await this.log(`Failed to save config: ${error.message}`);
    }
    return false;
  }

  async updatePollingFrequency(frequencySeconds) {
    const newIntervalMs = frequencySeconds * 1000;
    if (newIntervalMs >= 1000 && newIntervalMs <= 60000) {
      this.config.commandCheckIntervalMs = newIntervalMs;
      await this.saveConfig();
      
      // Restart command processing with new interval
      this.startCommandProcessing();
      
      this.updateUI({
        config: { pollingFrequency: frequencySeconds },
        log: { message: `Polling updated to ${frequencySeconds}s`, type: 'info' }
      });
      return true;
    }
    return false;
  }

  async init() {
    await this.log('MCP Bridge Plugin initializing...');
    
    try {
      // 1. Set up config file path
      await this.initializeConfigPath();
      
      // 2. Load saved config
      await this.loadConfig();
      
      // 3. CRITICAL: If baseDir is empty, reset all paths immediately
      const hasBaseDir = this.config.baseDir && this.config.baseDir.trim();
      if (!hasBaseDir) {
        this.config.baseDir = null;
        this.mcpServerPath = null;
        this.config.mcpCommandDir = null;
        this.config.mcpResponseDir = null;
        console.log('[Init] No config, paths reset to null');
      } else {
        console.log('[Init] Has config baseDir:', this.config.baseDir);
      }
      
      // 4. Setup MCP dirs
      await this.setupMCPCommunication();
      
      // 5. Start command processing loop
      this.startCommandProcessing();
      
      // 6. Register event hooks
      this.registerHooks();
      
      // 7. Register UI elements
      this.registerUI();
      
      this.isInitialized = true;
      await this.log('MCP Bridge Plugin initialized successfully!');
      
      console.log('🔗 MCP Bridge ready. MCP path:', this.mcpServerPath);
      
      // 8. Send init status to UI
      this.updateUI({
        status: { type: 'connected', message: '✅ Connected and ready' },
        mcpPath: this.mcpServerPath,
        commandDir: this.config.mcpCommandDir,
        responseDir: this.config.mcpResponseDir,
        config: {
          pollingFrequency: Math.floor(this.config.commandCheckIntervalMs / 1000)
        }
      });
      
    } catch (error) {
      await this.log(`Failed to initialize: ${error.message}`);
      console.error('MCP Bridge failed:', error.message);
      this.updateUI({
        status: { type: 'disconnected', message: `❌ ${error.message}` }
      });
    }
  }

async setupMCPCommunication() {
    console.log('[SETUP] START. config.baseDir:', this.config.baseDir);
    
    // Always reset paths first
    this.mcpServerPath = null;
    this.config.mcpCommandDir = null;
    this.config.mcpResponseDir = null;
    
    const baseDir = this.config.baseDir;
    console.log('[SETUP] baseDir variable:', baseDir);
    console.log('[SETUP] baseDir type:', typeof baseDir);
    
    // If no config, skip setup - just show empty paths
    if (!baseDir) {
      await this.log('No baseDir configured. Please configure in Dashboard.');
      return;
    }
    
// First try - use executeNodeScript args properly
    try {
      console.log('[SETUP] Calling executeNodeScript with baseDir:', baseDir);
      
      const result = await PluginAPI.executeNodeScript({
        script: `
          try {
            const fs = require('fs');
            const path = require('path');
            const os = require('os');
            
            const baseDirArg = args[0];
            
            // If no baseDir configured, return empty paths
            if (!baseDirArg || (typeof baseDirArg === 'string' && !baseDirArg.trim())) {
              return {
                success: true,
                mcpServerPath: null,
                commandDir: null,
                responseDir: null,
                empty: true
              };
            }
            
            // Convert common env var patterns to actual paths using os.homedir()
            function resolveEnvVar(input) {
              if (input === '%APPDATA%' && os.platform() === 'win32') {
                return path.join(os.homedir(), 'AppData', 'Roaming');
              }
              if (input === '%HOME%' || input === '%USERPROFILE%') {
                return os.homedir();
              }
              if (input === '%LOCALAPPDATA%' && os.platform() === 'win32') {
                return path.join(os.homedir(), 'AppData', 'Local');
              }
              return input;
            }
            
            let dataDir = resolveEnvVar(baseDirArg.trim());
            
            const mcpDir = path.join(dataDir, 'super-productivity-mcp');
            const commandDir = path.join(mcpDir, 'plugin_commands');
            const responseDir = path.join(mcpDir, 'plugin_responses');
            
            if (!fs.existsSync(mcpDir)) {
              fs.mkdirSync(mcpDir, { recursive: true });
            }
            if (!fs.existsSync(commandDir)) {
              fs.mkdirSync(commandDir, { recursive: true });
            }
            if (!fs.existsSync(responseDir)) {
              fs.mkdirSync(responseDir, { recursive: true });
            }
            
            return {
              success: true,
              mcpServerPath: mcpDir,
              commandDir: commandDir,
              responseDir: responseDir
            };
            
          } catch (error) {
            return {
              success: false,
              error: error.message
            };
          }
        `,
        args: [baseDir],
        timeout: 10000
      });
      
      console.log('[SETUP] executeNodeScript result:', JSON.stringify(result));
      
      let scriptResult = result;
      if (result && result.success && result.result) {
        scriptResult = result.result;
      }
      
      console.log('[SETUP] scriptResult:', JSON.stringify(scriptResult, null, 2));
      
      if (scriptResult && scriptResult.success) {
        this.mcpServerPath = scriptResult.mcpServerPath;
        this.config.mcpCommandDir = scriptResult.commandDir;
        this.config.mcpResponseDir = scriptResult.responseDir;
        console.log('[SETUP] SUCCESS. Paths set to:', this.mcpServerPath);
        return;
      } else {
        console.log('[SETUP] Script returned error:', scriptResult?.error);
        await this.log('Script setup failed: ' + (scriptResult?.error || 'unknown'));
      }
    } catch (e) {
      console.log('[SETUP] executeNodeScript threw:', e.message);
      await this.log('Setup failed: ' + e.message);
    }
    
    // If we get here (setup failed), paths are already reset to null at the start
  }


  /**
   * Start the command processing loop
   */
  startCommandProcessing() {
    if (this.commandWatchInterval) {
      clearInterval(this.commandWatchInterval);
    }

    this.commandWatchInterval = setInterval(async () => {
      try {
        await this.processNewCommands();
      } catch (error) {
        await this.log(`Command processing error: ${error.message}`);
        this.stats.errors++;
      }
    }, this.config.commandCheckIntervalMs);

    console.log(`Command processing started with ${this.config.commandCheckIntervalMs}ms interval`);
  }

  /**
   * Process new commands from MCP server
   */
  async processNewCommands() {
    if (!this.config.mcpCommandDir) {
      return;
    }

    try {

      const result = await PluginAPI.executeNodeScript({
        script: `
          const fs = require('fs');
          const path = require('path');
          
          const commandDir = args[0];
          const lastProcessed = args[1];
          
          // Always return a result with the expected structure
          try {
            // Log what we're working with
            console.log('Processing commands in:', commandDir);
            console.log('Last processed timestamp:', lastProcessed);
            
            if (!fs.existsSync(commandDir)) {
              console.log('Command directory does not exist');
              return { success: true, commands: [], message: 'Directory not found' };
            }
            
            const files = fs.readdirSync(commandDir);
            console.log('Found files:', files);
            
            const commandFiles = files.filter(f => f.endsWith('.json'));
            console.log('JSON files:', commandFiles);
            
            // Find new command files
            const newCommands = [];
            for (const file of commandFiles) {
              const filePath = path.join(commandDir, file);
              console.log('Checking file:', filePath);
              
              try {
                const stats = fs.statSync(filePath);
                console.log('File mtime:', stats.mtime.getTime(), 'vs lastProcessed:', lastProcessed);
                
                if (stats.mtime.getTime() > lastProcessed) {
                  console.log('Processing new file:', file);
                  
                  try {
                    const content = fs.readFileSync(filePath, 'utf8');
                    const command = JSON.parse(content);
                    
                    newCommands.push({
                      filename: file,
                      path: filePath,
                      command: command,
                      timestamp: stats.mtime.getTime()
                    });
                  } catch (parseError) {
                    console.log('Parse error for file', file, ':', parseError.message);
                  }
                } else {
                  console.log('File', file, 'is not newer than last processed');
                }
              } catch (statError) {
                console.log('Stat error for file', file, ':', statError.message);
              }
            }
            
            // Sort by timestamp
            newCommands.sort((a, b) => a.timestamp - b.timestamp);
            
            console.log('Returning', newCommands.length, 'new commands');
            
            const finalResult = {
              success: true,
              commands: newCommands,
              totalFiles: files.length,
              jsonFiles: commandFiles.length,
              processedFiles: newCommands.length
            };
            
            console.log('Final result:', JSON.stringify(finalResult, null, 2));
            return finalResult;
            
          } catch (error) {
            console.log('Error in command processing:', error.message);
            return { 
              success: false, 
              error: error.message,
              commands: [] // Always include commands array
            };
          }
        `,
        args: [this.config.mcpCommandDir, this.lastProcessedCommand],
        timeout: 10000
      });

      // Add comprehensive null checking
      if (!result) {
        await this.log('executeNodeScript returned null/undefined result');
        return;
      }
      
      if (!result.hasOwnProperty('success')) {
        await this.log('executeNodeScript result missing success property');
        return;
      }
      
      if (!result.success) {
        await this.log(`Command processing failed: ${result.error || 'Unknown error'}`);
        return;
      }
      
      // The result from executeNodeScript is wrapped in a 'result' property
      const commandResult = result.result;
      
      if (!commandResult || !commandResult.hasOwnProperty('commands')) {
        await this.log('executeNodeScript result.result missing commands property');
        return;
      }
      
      if (!Array.isArray(commandResult.commands)) {
        await this.log('executeNodeScript result.result.commands is not an array');
        return;
      }
      
      if (commandResult.commands.length > 0) {
        for (const commandInfo of commandResult.commands) {
          try {
            await this.executeCommand(commandInfo);
            this.lastProcessedCommand = Math.max(this.lastProcessedCommand, commandInfo.timestamp);
          } catch (error) {
            await this.log(`Command execution failed: ${error.message}`);
          }
        }
      }
      
    } catch (error) {
      await this.log(`Error in processNewCommands: ${error.message}`);
      this.stats.errors++;
    }
  }
  

  async executeCommand(commandInfo) {
    const { command, filename, path: commandPath } = commandInfo;
    
    try {
      let result;
      const startTime = Date.now();
      
      // Execute the appropriate API call based on command.action
      switch (command.action) {
        // Task operations
        case 'getTasks':
          result = await PluginAPI.getTasks();
          break;
        
        case 'getTask':
          try {
            const taskId = command.taskId;
            const allTasks = await PluginAPI.getTasks();
            const task = allTasks.find(t => t.id === taskId);
            result = task || null;
          } catch (error) {
            result = { error: error.message };
          }
          break;
          
        case 'getArchivedTasks':
          result = await PluginAPI.getArchivedTasks();
          break;
          
        case 'getCurrentContextTasks':
          result = await PluginAPI.getCurrentContextTasks();
          break;
          
        case 'addTask':
          // Check if this is a subtask with SP syntax (@, #, +)
          if (command.data.parentId && (command.data.title.includes('@') || command.data.title.includes('#') || command.data.title.includes('+'))) {
            await this.log(`Subtask with syntax detected: ${command.data.title}`);
            
            // Step 1: Create subtask without SP syntax
            const titleWithoutSyntax = command.data.title
              .replace(/@\w+/g, '')
              .replace(/#\w+/g, '')
              .replace(/\+\w+/g, '')
              .trim();
            const taskData = { ...command.data, title: titleWithoutSyntax };
            
            await this.log(`Creating subtask without syntax: ${titleWithoutSyntax}`);
            const taskId = await PluginAPI.addTask(taskData);
            
            // Step 2: Update with original title to trigger syntax parsing
            await this.log(`Updating subtask with original title: ${command.data.title}`);
            await PluginAPI.updateTask(taskId, { title: command.data.title });
            
            result = taskId;
          } else {
            // Regular task creation
            result = await PluginAPI.addTask(command.data);
          }
          break;
          
        case 'updateTask':
          result = await PluginAPI.updateTask(command.taskId, command.data);
          break;
          
        case 'deleteTasks':
        case 'deleteTask':
        case 'removeTask':
        case 'deleteCompletedTasks':
        case 'removeCompletedTasks':
        case 'clearAllTasks':
          try {
            let tasksToDelete = [];
            
            if (command.clearAll) {
              tasksToDelete = await PluginAPI.getTasks();
            } else if (command.taskIds && Array.isArray(command.taskIds)) {
              const allTasks = await PluginAPI.getTasks();
              tasksToDelete = allTasks.filter(t => command.taskIds.includes(t.id));
            } else if (command.taskId) {
              tasksToDelete = [{ id: command.taskId }];
            } else {
              const allTasks = await PluginAPI.getTasks();
              tasksToDelete = allTasks.filter(t => t.isDone === true);
            }
            
const deleteResults = [];
            for (const task of tasksToDelete) {
              try {
                await PluginAPI.deleteTask(task.id);
                deleteResults.push({ 
                  id: task.id, 
                  title: task.title || task.id, 
                  success: true 
                });
              } catch (err) {
                deleteResults.push({ id: task.id, title: task.title || task.id, success: false, error: err.message });
              }
            }
            
            result = {
              deletedCount: deleteResults.filter(r => r.success).length,
              results: deleteResults
            };
          } catch (error) {
            result = { success: false, error: error.message };
          }
          break;

        case 'deleteTasksInProject':
          try {
            const projectId = command.projectId;
            const allTasks = await PluginAPI.getTasks();
            const projectTasks = allTasks.filter(t => t.projectId === projectId);
            
            const deleteResults = [];
            for (const task of projectTasks) {
              try {
                await PluginAPI.deleteTask(task.id);
                deleteResults.push({ id: task.id, title: task.title || task.id, success: true });
              } catch (err) {
                deleteResults.push({ id: task.id, title: task.title || task.id, success: false, error: err.message });
              }
            }
            
            result = {
              deletedCount: deleteResults.filter(r => r.success).length,
              totalTasks: projectTasks.length,
              results: deleteResults
            };
          } catch (error) {
            result = { success: false, error: error.message };
          }
          break;

        case 'setTaskDone':
        case 'markTaskDone':
        case 'completeTask':
          result = await PluginAPI.updateTask(command.taskId, { isDone: true, doneOn: Date.now() });
          break;

        case 'setTaskUndone':
        case 'markTaskUndone':
        case 'uncompleteTask':
          result = await PluginAPI.updateTask(command.taskId, { isDone: false, doneOn: null });
          break;

        case 'addTimeToTask':
        case 'addTimeSpent':
          // Get current task to add time to existing timeSpent
          const tasks = await PluginAPI.getTasks();
          const task = tasks.find(t => t.id === command.taskId);
          if (task) {
            const newTimeSpent = task.timeSpent + (command.timeMs || 0);
            result = await PluginAPI.updateTask(command.taskId, { timeSpent: newTimeSpent });
          } else {
            result = { error: 'Task not found' };
          }
          break;

        case 'setTimeEstimate':
          result = await PluginAPI.updateTask(command.taskId, { timeEstimate: command.timeMs || 0 });
          break;

        case 'moveTaskToProject':
          result = await PluginAPI.updateTask(command.taskId, { projectId: command.projectId });
          break;

        case 'addTagToTask':
          // Get current task to add tag to existing tagIds
          const tasksForTag = await PluginAPI.getTasks();
          const taskForTag = tasksForTag.find(t => t.id === command.taskId);
          if (taskForTag) {
            const newTagIds = [...taskForTag.tagIds];
            if (!newTagIds.includes(command.tagId)) {
              newTagIds.push(command.tagId);
            }
            result = await PluginAPI.updateTask(command.taskId, { tagIds: newTagIds });
          } else {
            result = { error: 'Task not found' };
          }
          break;

        case 'removeTagFromTask':
          // Get current task to remove tag from existing tagIds
          const tasksForTagRemoval = await PluginAPI.getTasks();
          const taskForTagRemoval = tasksForTagRemoval.find(t => t.id === command.taskId);
          if (taskForTagRemoval) {
            const newTagIds = taskForTagRemoval.tagIds.filter(id => id !== command.tagId);
            result = await PluginAPI.updateTask(command.taskId, { tagIds: newTagIds });
          } else {
            result = { error: 'Task not found' };
          }
          break;
          
        case 'reorderTasks':
          result = await PluginAPI.reorderTasks ? await PluginAPI.reorderTasks(command.taskIds, command.contextId, command.contextType) : 'reorderTasks not available';
          break;

        // Project operations
        case 'getAllProjects':
          result = await PluginAPI.getAllProjects();
          break;
          
        case 'addProject':
          result = await PluginAPI.addProject(command.data);
          break;
          
        case 'updateProject':
          result = await PluginAPI.updateProject(command.projectId, command.data);
          break;
          
        case 'deleteProject':
          try {
            const projectId = command.projectId;
            if (typeof window !== 'undefined' && window.__store) {
              window.__store.dispatch({ type: '[Project] Delete Project', payload: projectId });
              result = { success: true };
            } else {
              result = { success: false, error: 'Store not available' };
            }
          } catch (error) {
            result = { success: false, error: error.message };
          }
          break;

        // Tag operations
        case 'getAllTags':
          result = await PluginAPI.getAllTags();
          break;
          
        case 'addTag':
          result = await PluginAPI.addTag(command.data);
          break;
          
        case 'updateTag':
          result = await PluginAPI.updateTag(command.tagId, command.data);
          break;
          
        case 'deleteTag':
          result = { error: 'Tag deletion not supported via Plugin API.' };
          break;

        // UI operations
        case 'showSnack':
          try {
            result = await PluginAPI.showSnack({
              message: command.message,
              type: 'SUCCESS'
            });
          } catch (e) {
            // Fallback - just log the message
            console.log('Snack message:', command.message);
            result = { success: true, fallback: true };
          }
          break;
          
        case 'notify':
          try {
            result = await PluginAPI.notify(command.message);
          } catch (e) {
            // Fallback - just log the message
            console.log('Notification:', command.message);
            result = { success: true, fallback: true };
          }
          break;
          
        case 'openDialog':
          result = await PluginAPI.openDialog(command.dialogConfig);
          break;

        // Data persistence
        case 'persistDataSynced':
          result = await PluginAPI.persistDataSynced(command.key, command.data);
          break;
          
        case 'loadSyncedData':
          result = await PluginAPI.loadSyncedData(command.key);
          break;

// Custom batch operations
        default:
          throw new Error(`Unknown command action: ${command.action}`);
      }
      
      const executionTime = Date.now() - startTime;
      
      // Write response back to MCP server
      await this.writeCommandResponse(command.id || filename, {
        success: true,
        result: result,
        executionTime: executionTime,
        timestamp: Date.now()
      });
      
      // Clean up command file
      await this.deleteCommandFile(commandPath);
      
      this.stats.commandsProcessed++;
      this.stats.lastCommandTime = Date.now();
      
      
    } catch (error) {
      await this.log(`Command failed: ${command.action} - ${error.message}`);
      
      // Write error response
      await this.writeCommandResponse(command.id || filename, {
        success: false,
        error: error.message,
        timestamp: Date.now()
      });
      
      // Clean up command file even on error
      await this.deleteCommandFile(commandPath);
      
      this.stats.errors++;
    }
  }

  async writeCommandResponse(commandId, response) {
    if (!this.config.mcpResponseDir) {
      return;
    }

    try {
      const result = await PluginAPI.executeNodeScript({
      script: `
        const fs = require('fs');
        const path = require('path');
        
        const responseDir = args[0];
        const commandId = args[1];
        const response = args[2];
        
        try {
          const responseFile = path.join(responseDir, \`\${commandId}_response.json\`);
          fs.writeFileSync(responseFile, JSON.stringify(response, null, 2));
          return { success: true, file: responseFile };
        } catch (error) {
          return { success: false, error: error.message };
        }
      `,
        args: [this.config.mcpResponseDir, commandId, response],
        timeout: 5000
      });
      
      
    } catch (error) {
      await this.log(`Error writing command response: ${error.message}`);
    }
  }

  async deleteCommandFile(commandPath) {
    try {
      const result = await PluginAPI.executeNodeScript({
      script: `
        const fs = require('fs');
        
        try {
          fs.unlinkSync(args[0]);
          return { success: true };
        } catch (error) {
          return { success: false, error: error.message };
        }
      `,
        args: [commandPath],
        timeout: 5000
      });
      
      
    } catch (error) {
      await this.log(`Error deleting command file: ${error.message}`);
    }
  }

  registerHooks() {
    // Task events
    PluginAPI.registerHook('taskUpdate', async (taskData) => {
      await this.sendEventToMCP('taskUpdate', taskData);
    });

    PluginAPI.registerHook('taskComplete', async (taskData) => {
      await this.sendEventToMCP('taskComplete', taskData);
    });

    PluginAPI.registerHook('taskDelete', async (taskData) => {
      await this.sendEventToMCP('taskDelete', taskData);
    });

    PluginAPI.registerHook('currentTaskChange', async (taskData) => {
      await this.sendEventToMCP('currentTaskChange', taskData);
    });

  }

  registerUI() {
    // Register menu entry only (no header button to avoid duplicates)
    PluginAPI.registerMenuEntry({
      label: 'MCP Bridge Dashboard',
      icon: 'dashboard',
      onClick: () => {
        PluginAPI.showIndexHtmlAsView();
      }
    });

  }

  async sendEventToMCP(eventType, eventData) {
    if (!this.isInitialized || !this.config.mcpResponseDir) return;
    
    try {
      const timestamp = Date.now();
      const eventFile = `${timestamp}_${eventType}_event.json`;
      
      const result = await PluginAPI.executeNodeScript({
        script: `
          const fs = require('fs');
          const path = require('path');
          
          const responseDir = args[0];
          const eventFile = args[1];
          const eventData = args[2];
          
          try {
            const filePath = path.join(responseDir, eventFile);
            fs.writeFileSync(filePath, JSON.stringify(eventData, null, 2));
            return { success: true, file: filePath };
          } catch (error) {
            return { success: false, error: error.message };
          }
        `,
        args: [this.config.mcpResponseDir, eventFile, {
          eventType: eventType,
          eventData: eventData,
          timestamp: timestamp,
          source: 'super-productivity'
        }],
        timeout: 5000
      });
      
      
    } catch (error) {
      await this.log(`Failed to send event to MCP: ${error.message}`);
    }
  }

  updateUI(data) {
    // Send message to iframe UI
    if (typeof window !== 'undefined' && window.postMessage) {
      try {
        window.postMessage({
          type: 'mcp-bridge-update',
          data: {
            ...data,
            stats: this.stats,
            timestamp: Date.now()
          }
        }, '*');
      } catch (e) {
        // Ignore postMessage errors
      }
    }
  }

  getStatus() {
    return {
      isInitialized: this.isInitialized,
      mcpServerPath: this.mcpServerPath,
      commandDir: this.config.mcpCommandDir,
      responseDir: this.config.mcpResponseDir,
      stats: this.stats,
      config: {
        pollingFrequency: Math.floor(this.config.commandCheckIntervalMs / 1000),
        debugMode: this.config.debugMode
      }
    };
  }

  async forceCommandCheck() {
    await this.processNewCommands();
    this.updateUI({
      log: { message: 'Force command check completed', type: 'success' }
    });
  }

async updateSettings(frequency, baseDir) {
    console.log('[UPDATE] START. baseDir:', baseDir);
    
    // Ensure config path is set
    if (!this.config.configFile) {
      await this.initializeConfigPath();
    }
    
    // If clearing config, reset everything to null
    if (!baseDir || typeof baseDir !== 'string' || !baseDir.trim()) {
      this.config.baseDir = null;
      this.mcpServerPath = null;
      this.config.mcpCommandDir = null;
      this.config.mcpResponseDir = null;
      await this.saveConfig();
      
      this.updateUI({
        mcpPath: null,
        commandDir: null,
        responseDir: null,
        log: { message: 'Configuration cleared', type: 'info' }
      });
      return;
    }
    
    const trimmedBaseDir = baseDir.trim();
    console.log('[UPDATE] After trim. baseDir:', trimmedBaseDir);
    
    this.config.baseDir = trimmedBaseDir;
    console.log('[UPDATE] config.baseDir set to:', this.config.baseDir);
    await this.saveConfig();
    console.log('[UPDATE] Saved. Now calling setupMCPCommunication...');
    await this.setupMCPCommunication();
    console.log('[UPDATE] setupMCPCommunication done. mcpServerPath:', this.mcpServerPath);
    
    this.updateUI({
      mcpPath: this.mcpServerPath,
      commandDir: this.config.mcpCommandDir,
      responseDir: this.config.mcpResponseDir,
      log: { message: `Settings updated. MCP dirs: ${this.mcpServerPath}`, type: 'success' }
    });
  }

  async cleanup() {
    if (this.commandWatchInterval) {
      clearInterval(this.commandWatchInterval);
      this.commandWatchInterval = null;
    }
    
    await this.log('MCP Bridge Plugin cleaned up');
  }

  async log(message) {
    if (this.config.debugMode) {
      const timestamp = new Date().toISOString();
      console.log(`[${timestamp}] MCP Bridge: ${message}`);
      
      // Send to UI
      this.updateUI({
        log: { message: message, type: 'info' }
      });
    }
  }
}

// Initialize the plugin
const mcpBridge = new MCPBridgePlugin();
mcpBridge.init().catch(console.error);

// Export for cleanup and UI access
window.mcpBridge = mcpBridge;