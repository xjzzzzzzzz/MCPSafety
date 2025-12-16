# MCP-SafetyBench
MCP-SafetyBench is a comprehensive benchmark designed to systematically evaluate the safety and robustness of LLM agents operating in the Model Context Protocol (MCP) ecosystem.
It addresses critical gaps in existing MCP safety benchmarks by supporting real-world servers, multi-step reasoning, and diverse attack scenarios.
<img src="fig/example.png" alt="img" width="800">
## Key Features

- **Real-world integration**: Built on real-world MCP servers, rather than simulated environments.  
- **Systematic coverage**: Encompasses 20 attack types spanning the Server, Host, and User layers.  
- **Multi-step tasks**: Includes complex reasoning workflows that require planning, tool selection, and context management.  

## Results
<img src="fig/result.png" alt="result1_domain" width="800">
<img src="fig/result2.png" alt="result_attacktype" width="800">
## Getting Started
### ⚠️ Security Recommendations

🔒 **IMPORTANT SECURITY NOTICE**

Please read and follow these security guidelines carefully before running benchmarks:

🚨 **GitHub Integration: CRITICAL** - We strongly recommend using a dedicated test GitHub account for benchmark evaluation. The AI agent will perform real operations on GitHub repositories, which could potentially modify or damage your personal repositories.

🔐 **API Key Management:**
- Store API keys securely and never commit them to version control
- Use environment variables or secure key management systems
- Regularly rotate your API keys for enhanced security

🛡️ **Access Permissions:**
- Grant minimal necessary permissions for each service integration
- Review and limit API key scopes to only required operations
- Monitor API usage and set appropriate rate limits

⚠️ **System Safety:** This benchmark contains various attack scenarios that may modify system files, create/delete repositories, and perform other potentially destructive operations. We strongly recommend running all tests in a Docker environment or isolated virtual machine to prevent unintended system modifications.

### Prerequisites

* **Python**: Requires version 3.10 or higher.
* **Docker**: Used for running Dockerized MCP servers.

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   pip install -r dev-requirements.txt
   ```

2. **Environment configuration**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and configuration
   ```
### API Keys and Configuration

Configure the following environment variables in your `.env` file. The required keys depend on which benchmark domains you plan to evaluate:

##### Core LLM Providers
| Environment Variable | Provider | Description | Required For |
|---------------------|----------|-------------|--------------|
| `OPENAI_API_KEY` | OpenAI | API key for GPT models (gpt-5, etc.) | All domains |
| `ANTHROPIC_API_KEY` | Anthropic | API key for Claude models | All domains |
| `GEMINI_API_KEY` | Google | API key for Gemini models | All domains |

> **Note**: You only need to configure the API key for the LLM provider you intend to use in your evaluation.

### Domain-Specific Services

| Environment Variable | Service | Description | Setup Instructions |
|---------------------|---------|-------------|-------------------|
| `SERP_API_KEY` | SerpAPI | Web search API for search benchmark evaluation | [Get API key](https://serpapi.com/) |
| `SERPER_API_KEY` | Serper | Alternative web search API for Google search | [Get API key](https://serper.dev/) |
| `GOOGLE_MAPS_API_KEY` | Google Maps | Geolocation and mapping services | [Setup Guide](https://console.cloud.google.com/google/maps-apis/credentials) |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | GitHub | Personal access token for repository operations | [Token Setup](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens) |
| `GITHUB_PERSONAL_ACCOUNT_NAME` | GitHub | Your GitHub username | N/A |
| `CHROMA_API_KEY` | Chroma | API key for Chroma vector database cloud service | [Get API key](https://www.trychroma.com/) |
| `FILESYSTEM_DIRECTORY` | Filesystem | Directory path for filesystem server operations | Set to desired working directory path |
| `TERMINAL_WORKING_DIRECTORY` | Terminal | Working directory for terminal server command execution | Set to desired working directory path |

### Execution
#### Docker(Recommend)
##### Build
``` shell
docker build -t mcpsafety .
```
##### Run
``` bash
# Financial Analysis
docker run --rm -v $(pwd):/app -w /app mcpsafety bash -c "PYTHONPATH=. python tests/benchmark/test_benchmark_financial_analysis.py"

# Web Search
docker run --rm -v $(pwd):/app -w /app mcpsafety bash -c "PYTHONPATH=. python tests/benchmark/test_benchmark_web_search.py"

# Location Navigation
docker run --rm -v $(pwd):/app -w /app mcpsafety bash -c "PYTHONPATH=. python tests/benchmark/test_benchmark_location_navigation.py"

# Browser Automation  
docker run --rm -v $(pwd):/app -w /app mcpsafety bash -c "PYTHONPATH=. python tests/benchmark/test_benchmark_browser_automation.py"

# Repository Management
docker run --rm -v $(pwd):/app -w /app mcpsafety bash -c "PYTHONPATH=. python tests/benchmark/test_benchmark_repository_management.py"
```

#### Python

Execute specific domain benchmarks using the following commands:

```bash
# Set Python path and run individual benchmarks
export PYTHONPATH=.

# Location Navigation
python tests/benchmark/test_benchmark_location_navigation.py

# Browser Automation  
python tests/benchmark/test_benchmark_browser_automation.py

# Financial Analysis
python tests/benchmark/test_benchmark_financial_analysis.py

# Repository Management
python tests/benchmark/test_benchmark_repository_management.py

# Web Search
python tests/benchmark/test_benchmark_web_search.py