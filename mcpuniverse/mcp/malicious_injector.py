"""
Malicious tool injector for MCP servers.

This module provides functionality to dynamically inject malicious tools into MCP servers
for security testing purposes.
"""

import os
import shutil
import tempfile
import json
from typing import List, Dict, Any, Optional
from pathlib import Path


class MaliciousToolInjector:
    """
    A class for dynamically injecting malicious tools into MCP servers.
    """
    
    def __init__(self):
        self.temp_dirs = []
    
    def inject_malicious_tools(self, server_dir: str, malicious_tools: List[Dict[str, Any]], 
                              temp_dir: Optional[str] = None) -> str:
        """
        Inject malicious tools into a server directory.
        
        Args:
            server_dir: Path to the original server directory
            malicious_tools: List of malicious tool definitions
            temp_dir: Optional temporary directory path
            
        Returns:
            Path to the modified server directory
        """
        if temp_dir is None:
            temp_dir = tempfile.mkdtemp(prefix="malicious_mcp_")
            self.temp_dirs.append(temp_dir)
        
        # Create temporary server directory
        server_name = os.path.basename(server_dir)
        temp_server_dir = os.path.join(temp_dir, f"{server_name}_malicious")
        shutil.copytree(server_dir, temp_server_dir)
        
        # Modify the server.py file to include malicious tools
        server_py_path = os.path.join(temp_server_dir, "server.py")
        
        # Read original server.py
        with open(server_py_path, 'r', encoding='utf-8') as f:
            server_content = f.read()
        
        # Generate malicious tool code
        malicious_tool_code = self._generate_malicious_tool_code(malicious_tools)
        
        # Insert malicious tools into the server
        modified_content = self._insert_malicious_tools(server_content, malicious_tool_code)
        
        # Write modified server.py
        with open(server_py_path, 'w', encoding='utf-8') as f:
            f.write(modified_content)
        
        return temp_server_dir
    
    def _generate_malicious_tool_code(self, malicious_tools: List[Dict[str, Any]]) -> str:
        """
        Generate Python code for malicious tools.
        
        Args:
            malicious_tools: List of malicious tool definitions
            
        Returns:
            Generated Python code string
        """
        tool_code_parts = []
        
        for tool in malicious_tools:
            tool_name = tool["tool_name"]
            description = tool["description"]
            input_params = tool["input_parameters"]
            output_params = tool["output_parameters"]
            implementation = tool["implementation_code"]
            
            # Convert input parameters to schema
            input_schema = {}
            for param_name, param_type in input_params.items():
                input_schema[param_name] = {"type": param_type}
            
            # Generate tool definition
            tool_def = f'''
# Malicious tool: {tool_name}
@mcp.tool()
{implementation}
'''
            tool_code_parts.append(tool_def)
        
        return "\n".join(tool_code_parts)
    
    def _insert_malicious_tools(self, server_content: str, malicious_code: str) -> str:
        """
        Insert malicious tool code into the server content.
        
        Args:
            server_content: Original server content
            malicious_code: Malicious tool code to insert
            
        Returns:
            Modified server content
        """
        # 查找第一个@mcp.tool()装饰器的位置
        first_tool_decorator = server_content.find("@mcp.tool()")
        
        if first_tool_decorator == -1:
            # 如果没有找到@mcp.tool()装饰器，尝试查找其他工具装饰器
            alternative_patterns = [
                "@tool()",
                "@server.tool()",
                "def "  # 在第一个函数定义前插入
            ]
            
            for pattern in alternative_patterns:
                pos = server_content.find(pattern)
                if pos != -1:
                    # 在第一个函数定义前插入恶意工具
                    return server_content[:pos] + malicious_code + "\n" + server_content[pos:]
            
            # 如果都没有找到，在文件末尾添加
            return server_content + "\n" + malicious_code
        else:
            # 在第一个@mcp.tool()装饰器上方插入恶意工具
            # 需要保持与@mcp.tool()相同的缩进
            line_start = first_tool_decorator
            while line_start > 0 and server_content[line_start - 1] != '\n':
                line_start -= 1
            
            # 计算当前行的缩进
            indent_start = line_start
            while indent_start < len(server_content) and server_content[indent_start] in ' \t':
                indent_start += 1
            
            # 获取缩进字符串
            indent = server_content[line_start:indent_start]
            
            # 为恶意工具代码添加相同的缩进
            indented_malicious_code = ""
            for line in malicious_code.strip().split('\n'):
                if line.strip():  # 非空行
                    indented_malicious_code += indent + line + '\n'
                else:  # 空行
                    indented_malicious_code += '\n'
            
            # 在第一个@mcp.tool()装饰器上方插入恶意工具
            return (
                server_content[:line_start] + 
                indented_malicious_code + 
                server_content[line_start:]
            )
    
    def cleanup(self):
        """
        Clean up all temporary directories.
        """
        for temp_dir in self.temp_dirs:
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                print(f"Warning: Failed to cleanup temporary directory {temp_dir}: {e}")
        self.temp_dirs.clear()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()


def create_malicious_server_config(original_config: Dict[str, Any], 
                                 malicious_tools: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Create a malicious server configuration based on the original.
    
    Args:
        original_config: Original server configuration
        malicious_tools: List of malicious tool definitions
        
    Returns:
        Modified server configuration
    """
    # Deep copy the original config
    malicious_config = json.loads(json.dumps(original_config))
    
    # Add malicious tools to the configuration
    if "tools" not in malicious_config:
        malicious_config["tools"] = []
    
    for tool in malicious_tools:
        malicious_config["tools"].append({
            "name": tool["tool_name"],
            "description": tool["description"],
            "input_schema": tool["input_parameters"],
            "output_schema": tool["output_parameters"]
        })
    
    return malicious_config 