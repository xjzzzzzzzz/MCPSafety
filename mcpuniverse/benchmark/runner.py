"""
Benchmarks for evaluating agents and LLMs
"""
# pylint: disable=broad-exception-caught,too-few-public-methods
import json
import os
import hashlib
from typing import List, Dict, Optional, Any
from contextlib import AsyncExitStack

import yaml
from pydantic import BaseModel, Field
from mcpuniverse.common.misc import AutodocABCMeta
from mcpuniverse.llm.base import BaseLLM
from mcpuniverse.agent.base import Executor, BaseAgent
from mcpuniverse.mcp.manager import MCPManager
from mcpuniverse.workflows.builder import WorkflowBuilder
from mcpuniverse.benchmark.task import Task
from mcpuniverse.tracer.collectors.base import BaseCollector
from mcpuniverse.tracer import Tracer
from mcpuniverse.evaluator import EvaluationResult
from mcpuniverse.common.logger import get_logger
from mcpuniverse.common.context import Context
from mcpuniverse.callbacks.base import (
    BaseCallback,
    CallbackMessage,
    MessageType,
    send_message_async, send_message
)


class BenchmarkConfig(BaseModel):
    """Benchmark configuration."""
    description: str = ""
    agent: str = ""
    tasks: List[str] = Field(default_factory=list)

    def md5(self) -> str:
        """Return the MD5 hash of the benchmark config."""
        text = (f"Description: {self.description}, "
                f"Agent: {self.agent}, "
                f"Tasks: {', '.join(self.tasks)}")
        return hashlib.md5(text.encode()).hexdigest()


class BenchmarkResult(BaseModel):
    """Benchmark evaluation results."""
    benchmark: BenchmarkConfig
    task_results: Dict[str, Dict[str, Any]]
    task_trace_ids: Dict[str, str]


class BenchmarkResultStore(metaclass=AutodocABCMeta):
    """
    The class for storing benchmark results, allowing resuming tasks.
    """

    def __init__(self, folder: str = ""):
        """
        Initialize a store of benchmark results.

        Args:
            folder (str): The folder path of the store.
                If it is empty, the results will not be stored.
        """
        self._folder = folder

    def dump_task_result(
            self,
            benchmark: BenchmarkConfig,
            task_config_path: str,
            evaluation_results: List[EvaluationResult],
            trace_id: str,
            overwrite: bool = True
    ):
        """
        Dump a task result in one benchmark.

        Args:
            benchmark (BenchmarkConfig): The benchmark configuration.
            task_config_path (str): The task config filepath.
            evaluation_results (List[EvaluationResult]): The evaluation results to save.
            trace_id (str): The tracing ID for this task (only valid when the collector is a database).
            overwrite (bool): Whether to overwrite existing evaluation results.
        """
        if not self._folder:
            return
        with open(task_config_path, "rb") as f:
            task_md5 = hashlib.md5(f.read()).hexdigest()
        folder = os.path.join(self._folder, benchmark.md5())
        os.makedirs(folder, exist_ok=True)
        filename = os.path.join(folder, f"{task_md5}.json")
        if not overwrite and os.path.isfile(filename):
            return
        result = {
            "results": [r.model_dump(mode="json") for r in evaluation_results],
            "trace_id": trace_id
        }
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)

    def load_task_result(
            self,
            benchmark: BenchmarkConfig,
            task_config_path: str
    ) -> Optional[dict]:
        """
        Check if the evaluation results of a task have been stored.

        Args:
            benchmark (BenchmarkConfig): The benchmark configuration.
            task_config_path (str): The task config filepath.
        """
        if self._folder == "":
            return None
        with open(task_config_path, "rb") as f:
            task_md5 = hashlib.md5(f.read()).hexdigest()
        folder = os.path.join(self._folder, benchmark.md5())
        filename = os.path.join(folder, f"{task_md5}.json")
        if not os.path.isfile(filename):
            return None
        with open(filename, "r", encoding="utf-8") as f:
            result = json.load(f)
            result["results"] = [EvaluationResult.model_validate(r) for r in result["results"]]
            return result


class BenchmarkRunner(metaclass=AutodocABCMeta):
    """
    The class for running different benchmarks.
    """

    def __init__(self, config: str, context: Optional[Context] = None):
        """
        Initialize a benchmark runner.

        Args:
            config (str): The config file path.
            context (Context, optional): The context information.
        """
        self._default_folder = os.path.join(os.path.dirname(os.path.realpath(__file__)), "configs")
        if not os.path.exists(config):
            config = os.path.join(self._default_folder, config)
        if not os.path.exists(config):
            raise ValueError(f"Cannot find config file: {config}")
        self._logger = get_logger("Benchmark")
        self._context = context if context else Context()

        # Load configs
        self._agent_configs = []
        self._benchmark_configs = []
        with open(config, "r", encoding="utf-8") as f:
            objects = yaml.safe_load_all(f)
            if isinstance(objects, dict):
                objects = [objects]
            for obj in objects:
                obj = dict(obj)
                assert "kind" in obj and "spec" in obj, "Wrong config format: Missing `kind`"
                if obj["kind"].lower() == "benchmark":
                    self._benchmark_configs.append(BenchmarkConfig.model_validate(obj["spec"]))
                else:
                    self._agent_configs.append(obj)

        # store the outputs
        self._benchmark_results = None

    async def run(
            self,
            mcp_manager: Optional[MCPManager] = None,
            trace_collector: Optional[BaseCollector] = None,
            components: Optional[Dict[str, BaseLLM | Executor]] = None,
            store_folder: str = "",
            overwrite: bool = True,
            callbacks: Optional[List[BaseCallback]] = None
    ) -> List[BenchmarkResult]:
        """
        Run specified benchmarks.

        Args:
            mcp_manager (MCPManager): An MCP server manager.
            trace_collector (BaseCollector): Trace collector.
            components (Dict): The components to be overwritten.
            store_folder (str): The folder path for storing evaluation results.
            overwrite (bool): Whether to overwrite existing evaluation results.
            callbacks (List[BaseCallback], optional): Callback functions.
        """
        if mcp_manager is None:
            mcp_manager = MCPManager(context=self._context)
        workflow = WorkflowBuilder(mcp_manager=mcp_manager, config=self._agent_configs)
        workflow.build(components)
        store = BenchmarkResultStore(folder=store_folder)

        outputs = []
        used_agents = []
        for benchmark in self._benchmark_configs:
            agent: Executor = workflow.get_component(benchmark.agent)
            used_agents.append(agent)
            await agent.initialize()
            await send_message_async(callbacks, message=CallbackMessage(
                source=__file__,
                type=MessageType.LOG,
                metadata={"event": "list_tools", "data": agent}
            ))
            task_results, task_trace_ids = {}, {}
            for idx, task_path in enumerate(benchmark.tasks):
                async with AsyncExitStack():
                    send_message(callbacks, message=CallbackMessage(
                        source="benchmark_runner",
                        type=MessageType.PROGRESS,
                        data=f"Running task: {task_path} ({idx + 1}/{len(benchmark.tasks)})"
                    ))
                    send_message(callbacks, message=CallbackMessage(
                        source="benchmark_runner",
                        type=MessageType.LOG,
                        data=f"Running task: {task_path}"
                    ))
                    self._logger.info("Running task: %s", task_path)
                    if not os.path.exists(task_path):
                        task_filepath = os.path.join(self._default_folder, task_path)
                    else:
                        task_filepath = task_path

                    stored_result = store.load_task_result(
                        benchmark=benchmark, task_config_path=task_filepath)
                    if not overwrite and stored_result is not None:
                        task_results[task_path] = stored_result["results"]
                        task_trace_ids[task_path] = stored_result["trace_id"]
                        self._logger.info("Loaded stored results for task: %s", task_path)
                        continue

                    # Execute the task and the corresponding evaluations
                    task = Task(task_filepath, context=self._context)
                    
                    # Apply tool modifications and malicious tool injection if present
                    if task.has_attack() and isinstance(agent, BaseAgent):
                        # Apply tool modifications (if any)
                        if task.get_mcp_server_modifications():
                            await self._apply_tool_modifications(agent, task)
                        # Inject malicious tools (if any)
                        if task.get_mcp_server_additions():
                            await self._inject_malicious_tools(agent, task)
                    if task.use_specified_server() and isinstance(agent, BaseAgent):
                        await agent.change_servers(task.get_mcp_servers())
                    agent.reset()
                    tracer = Tracer(collector=trace_collector)
                    question = task.get_question()
                    output_format = task.get_output_format()

                    await send_message_async(callbacks, message=CallbackMessage(
                        source=__file__,
                        type=MessageType.LOG,
                        metadata={"event": "task_description", "data": task}
                    ))
                    try:
                        response = await agent.execute(
                            question,
                            output_format=output_format,
                            tracer=tracer,
                            callbacks=callbacks
                        )
                        result = response.get_response_str()
                    except Exception as e:
                        result = str(e)
                    
                    # Get trace records for evaluation
                    trace_records = trace_collector.get(tracer.trace_id)
                    
                    # Create evaluation input with trace records
                    evaluation_input = {
                        "result": result,
                        "trace_records": trace_records
                    }
                    
                    evaluation_results = await task.evaluate(evaluation_input)

                    # Save the evaluation results
                    task_results[task_path] = {
                        "evaluation_results": evaluation_results
                    }
                    task_trace_ids[task_path] = tracer.trace_id
                    trace_records = trace_collector.get(tracer.trace_id)
                    store.dump_task_result(
                        benchmark=benchmark,
                        task_config_path=task_filepath,
                        evaluation_results=evaluation_results,
                        trace_id=tracer.trace_id,
                        overwrite=True
                    )

                    # Reset task status/environment
                    self._logger.info("Resetting task %s", task_path)
                    await task.reset(trace_records)
                    # Clean up and restore original server files
                    await task.cleanup()
                    self._logger.info("Finished cleanup and restoration for task %s", task_path)
                    
                    if task.use_specified_server() and isinstance(agent, BaseAgent):
                        await agent.cleanup()

            outputs.append(BenchmarkResult(
                benchmark=benchmark, task_results=task_results, task_trace_ids=task_trace_ids))
            self._logger.info("Finished benchmark: %s", benchmark.description)

        for agent in used_agents[::-1]:
            await agent.cleanup()
        self._logger.info("Agent cleanup succeeded")

        self._benchmark_results = outputs
        return outputs

    async def _apply_tool_modifications(self, agent: BaseAgent, task: Task):
        """
        Apply tool modifications for poisoning attacks by modifying tool descriptions
        and optionally modifying server code for return values.
        
        Args:
            agent: The agent to modify tools for
            task: The task containing attack configuration
        """
        try:
            modifications = task.get_mcp_server_modifications()
            if not modifications:
                return
            
            # Apply tool description modifications (keep existing logic)
            for modification in modifications:
                tool_name = modification.get("tool_name")
                modification_description = modification.get("modification_description")
                
                if tool_name and modification_description:
                    # Find the tool in the agent's tools and modify its description
                    for server_name, tools in agent._tools.items():
                        for tool in tools:
                            if tool.name == tool_name:
                                # Store original description for restoration
                                if not hasattr(tool, '_original_description'):
                                    tool._original_description = tool.description
                                
                                # Apply the poisoned description
                                tool.description = modification_description
                                self._logger.info(f"Applied tool modifications to {server_name}.{tool_name}")
                                break
            
            # Check if we need to modify server code for return values
            has_return_modifications = any(
                modification.get("modification_return") 
                for modification in modifications
            )
            
            if has_return_modifications:
                # Get the first server directory from the agent's tools
                if not hasattr(agent, '_tools') or not agent._tools:
                    self._logger.warning("Agent has no tools available for server code modifications")
                    return
                
                first_server_name = list(agent._tools.keys())[0]
                self._logger.info(f"Using first available server for server code modifications: {first_server_name}")
                
                # Get the server configuration from MCP manager
                mcp_manager = getattr(agent, '_mcp_manager', None)
                if not mcp_manager:
                    self._logger.warning("Agent has no MCP manager for server code modifications")
                    return
                
                # Find the server configuration
                server_config = None
                try:
                    server_config = mcp_manager.get_config(first_server_name)
                except Exception as e:
                    self._logger.warning(f"Failed to get config for server {first_server_name}: {e}")
                    return
                
                if not server_config:
                    self._logger.warning(f"Server {first_server_name} not found in MCP manager")
                    return
                
                # Get the server directory from the config
                server_dir = None
                if server_config.stdio.args:
                    module_name = server_config.stdio.args[-1]  # Get the last argument (module name)
                    if module_name.startswith("-m"):
                        module_name = module_name[2:]  # Remove "-m" prefix
                    
                    # Convert module name to directory path
                    if module_name.startswith("mcpuniverse.mcp.servers."):
                        # For internal servers, construct the path
                        server_name_short = module_name.split(".")[-1]
                        server_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                                               "mcpuniverse", "mcp", "servers", server_name_short)
                    else:
                        # For external modules, try to find the module path
                        try:
                            import importlib.util
                            spec = importlib.util.find_spec(module_name)
                            if spec and spec.origin:
                                server_dir = os.path.dirname(spec.origin)
                            else:
                                self._logger.warning(f"Cannot find module path for {module_name}")
                                return
                        except Exception as e:
                            self._logger.warning(f"Failed to find module path for {module_name}: {e}")
                            return
                else:
                    self._logger.warning(f"Unsupported server type for {first_server_name}")
                    return
                
                if not server_dir or not os.path.exists(server_dir):
                    self._logger.warning(f"Server directory {server_dir} does not exist for {first_server_name}")
                    return
                
                # Directly modify the server code to change tool return values
                try:
                    server_py_path = os.path.join(server_dir, "server.py")
                    backup_path = os.path.join(server_dir, "server.py.backup")
                    
                    # Create backup of original server.py if not exists
                    if not os.path.exists(backup_path):
                        import shutil
                        shutil.copy2(server_py_path, backup_path)
                        self._logger.info(f"Created backup of {server_py_path}")
                    
                    # Read original server.py content
                    with open(server_py_path, 'r', encoding='utf-8') as f:
                        server_content = f.read()
                    
                    # Apply return value modifications for each tool
                    modified_content = server_content
                    for modification in modifications:
                        tool_name = modification.get("tool_name")
                        modification_return = modification.get("modification_return")
                        
                        if not tool_name or not modification_return:
                            continue
                        
                        # Find the tool function definition
                        tool_pattern = f"def {tool_name}("
                        tool_start = modified_content.find(tool_pattern)
                        
                        if tool_start == -1:
                            self._logger.warning(f"Tool function {tool_name} not found in {server_py_path}")
                            continue
                        
                        # Find the function body
                        next_def = modified_content.find("def ", tool_start + 1)
                        if next_def == -1:
                            function_end = len(modified_content)
                        else:
                            function_end = next_def
                        
                        function_content = modified_content[tool_start:function_end]
                        
                        # Handle modification_return (return value modification)
                        # Find all return statements in THIS SPECIFIC TOOL FUNCTION and replace them
                        return_positions = []
                        search_start = 0
                        
                        # Search only within the current tool function
                        while True:
                            return_pos = function_content.find("return ", search_start)
                            if return_pos == -1:
                                break
                            return_positions.append(return_pos)
                            search_start = return_pos + 1
                        
                        # Sort return positions in reverse order to avoid index shifting issues
                        return_positions.sort(reverse=True)
                        
                        # Replace each return statement in this specific tool function
                        for return_pos in return_positions:
                            # Find the start of the return line (preserve indentation)
                            return_line_start = return_pos
                            while return_line_start > 0 and function_content[return_line_start - 1] != '\n':
                                return_line_start -= 1
                            
                            # Find the end of the return line
                            return_line_end = function_content.find('\n', return_pos)
                            if return_line_end == -1:
                                return_line_end = len(function_content)
                            
                            # Extract the indentation from the original return line
                            original_line = function_content[return_line_start:return_line_end]
                            indent = ""
                            for char in original_line:
                                if char in ' \t':
                                    indent += char
                                else:
                                    break
                            
                            # Calculate absolute positions within the current tool function
                            abs_return_start = tool_start + return_line_start
                            abs_return_end = tool_start + return_line_end
                            
                            # Generate the new return statement with preserved indentation
                            if isinstance(modification_return, dict):
                                new_return = f"{indent}return {repr(modification_return)}"
                            else:
                                new_return = f"{indent}return {repr(modification_return)}"
                            
                            # Replace the return statement
                            modified_content = (
                                modified_content[:abs_return_start] +
                                new_return +
                                modified_content[abs_return_end:]
                            )
                            
                            self._logger.info(f"Replaced return statement {len(return_positions) - return_positions.index(return_pos)} in tool {tool_name}")
                        
                        self._logger.info(f"Replaced {len(return_positions)} return statements in tool {tool_name}")
                    
                    # Write modified server.py
                    with open(server_py_path, 'w', encoding='utf-8') as f:
                        f.write(modified_content)
                    
                    self._logger.info(f"Successfully modified tool return values in {server_py_path}")
                    
                    # Store backup path for restoration during cleanup
                    if not hasattr(task, '_server_backup_path'):
                        task._server_backup_path = backup_path
                        task._original_server_path = server_py_path
                    
                    # Reconnect to the modified server using change_servers
                    try:
                        # Get current server configurations
                        current_servers = []
                        for server_name, tools in agent._tools.items():
                            server_config = mcp_manager.get_config(server_name)
                            server_info = {
                                "name": server_name,
                                "transport": "stdio"
                            }
                            current_servers.append(server_info)
                        
                        # Reconnect using change_servers
                        await agent.change_servers(current_servers)
                        self._logger.info(f"Successfully reconnected to modified server using change_servers")
                        
                    except Exception as client_error:
                        self._logger.error(f"Failed to reconnect using change_servers: {client_error}")
                    
                except Exception as e:
                    self._logger.warning(f"Failed to modify tool return values directly: {e}")
                    self._logger.info("Tool return value modification failed.")
            
        except Exception as e:
            self._logger.warning(f"Failed to apply tool modifications: {e}")
    
    
    async def _inject_malicious_tools(self, agent: BaseAgent, task: Task):
        """
        Inject malicious tools directly into the first available server's code,
        then reconnect using change_servers.
        
        Args:
            agent: The agent to inject malicious tools for
            task: The task containing attack configuration
        """
        try:
            mcp_server_additions = task.get_mcp_server_additions()
            if not mcp_server_additions:
                return
            
            # Extract tool information from the current structure
            if "tool_name" in mcp_server_additions:
                # Single tool case - convert to list format
                malicious_tools = [mcp_server_additions]
            else:
                # Multiple tools case - assume it has tools array
                malicious_tools = mcp_server_additions.get("tools", [])
            
            if not malicious_tools:
                return
            
            # Get the first server name from the agent's tools
            if not hasattr(agent, '_tools') or not agent._tools:
                self._logger.warning("Agent has no tools available for malicious tool injection")
                return
            
            first_server_name = list(agent._tools.keys())[0]
            self._logger.info(f"Using first available server: {first_server_name}")
            
            # Get the server configuration from MCP manager
            mcp_manager = getattr(agent, '_mcp_manager', None)
            if not mcp_manager:
                self._logger.warning("Agent has no MCP manager for malicious tool injection")
                return
            
            # Find the server configuration
            server_config = None
            try:
                server_config = mcp_manager.get_config(first_server_name)
            except Exception as e:
                self._logger.warning(f"Failed to get config for server {first_server_name}: {e}")
                return
            
            if not server_config:
                self._logger.warning(f"Server {first_server_name} not found in MCP manager")
                return
            
            # Get the server directory from the config
            server_dir = None
            if server_config.stdio.args:
                module_name = server_config.stdio.args[-1]  # Get the last argument (module name)
                if module_name.startswith("-m"):
                    module_name = module_name[2:]  # Remove "-m" prefix
                
                # Convert module name to directory path
                if module_name.startswith("mcpuniverse.mcp.servers."):
                    # For internal servers, construct the path
                    server_name_short = module_name.split(".")[-1]
                    server_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                                           "mcpuniverse", "mcp", "servers", server_name_short)
                else:
                    # For external modules, try to find the module path
                    try:
                        import importlib.util
                        spec = importlib.util.find_spec(module_name)
                        if spec and spec.origin:
                            server_dir = os.path.dirname(spec.origin)
                        else:
                            self._logger.warning(f"Cannot find module path for {module_name}")
                            return
                    except Exception as e:
                        self._logger.warning(f"Failed to find module path for {module_name}: {e}")
                        return
            else:
                self._logger.warning(f"Unsupported server type for {first_server_name}")
                return
            
            if not server_dir or not os.path.exists(server_dir):
                self._logger.warning(f"Server directory {server_dir} does not exist for {first_server_name}")
                return
            
            # Directly inject malicious tools into the original server file
            try:
                server_py_path = os.path.join(server_dir, "server.py")
                backup_path = os.path.join(server_dir, "server.py.backup")
                
                # Create backup of original server.py
                if not os.path.exists(backup_path):
                    import shutil
                    shutil.copy2(server_py_path, backup_path)
                    self._logger.info(f"Created backup of {server_py_path}")
                
                # Read original server.py content
                with open(server_py_path, 'r', encoding='utf-8') as f:
                    server_content = f.read()
                
                # Generate malicious tool code
                malicious_code = ""
                for tool in malicious_tools:
                    tool_name = tool["tool_name"]
                    description = tool["description"]
                    input_params = tool["input_parameters"]
                    output_params = tool["output_parameters"]
                    implementation = tool["implementation_code"]
                    
                    malicious_code += f'''
# Malicious tool: {tool_name}
@mcp.tool()
{implementation}

'''
                
                # Insert malicious tools into server.py (before the first @mcp.tool())
                first_tool_decorator = server_content.find("@mcp.tool()")
                if first_tool_decorator != -1:
                    # Find the start of the line with @mcp.tool()
                    line_start = first_tool_decorator
                    while line_start > 0 and server_content[line_start - 1] != '\n':
                        line_start -= 1
                    
                    # Calculate indentation
                    indent_start = line_start
                    while indent_start < len(server_content) and server_content[indent_start] in ' \t':
                        indent_start += 1
                    indent = server_content[line_start:indent_start]
                    
                    # Apply indentation to malicious code
                    indented_malicious_code = ""
                    for line in malicious_code.strip().split('\n'):
                        if line.strip():
                            indented_malicious_code += indent + line + '\n'
                        else:
                            indented_malicious_code += '\n'
                    
                    # Insert malicious code before the first @mcp.tool()
                    modified_content = (
                        server_content[:line_start] +
                        indented_malicious_code +
                        server_content[line_start:]
                    )
                else:
                    # If no @mcp.tool() found, append at the end
                    modified_content = server_content + malicious_code
                
                # Write modified server.py
                with open(server_py_path, 'w', encoding='utf-8') as f:
                    f.write(modified_content)
                
                self._logger.info(f"Successfully injected malicious tools into {server_py_path}")
                
                # Store backup path for restoration during cleanup
                if not hasattr(task, '_server_backup_path'):
                    task._server_backup_path = backup_path
                    task._original_server_path = server_py_path
                
                # Use change_servers to reconnect to the modified server
                try:
                    # Get the current server configuration
                    current_servers = []
                    for server_name, tools in agent._tools.items():
                        server_config = mcp_manager.get_config(server_name)
                        server_info = {
                            "name": server_name,
                            "transport": "stdio"
                        }
                        current_servers.append(server_info)
                    
                    # Reconnect using change_servers
                    await agent.change_servers(current_servers)
                    self._logger.info(f"Successfully reconnected to modified server using change_servers")
                    
                except Exception as client_error:
                    self._logger.error(f"Failed to reconnect using change_servers: {client_error}")
                
            except Exception as e:
                self._logger.warning(f"Failed to inject malicious tools directly: {e}")
                self._logger.info("Malicious tool injection failed.")
            
        except Exception as e:
            self._logger.warning(f"Failed to inject malicious tools: {e}")
