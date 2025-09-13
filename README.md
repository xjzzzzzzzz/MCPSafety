# YFinance 测试指南

## ⚙️ 评测配置

**YAML 配置文件**: mcpuniverse/benchmark/configs/test/financial_analysis.yaml

在YAML配置文件中填入要评测的LLM 和 Agent

执行 python tests/benchmark/test_benchmark_financial_analysis.py进行评测

报告将保存到 log/ 文件夹下

# Web Search 测试指南

在.env中填入SERP_API_KEY，OPENAI_API_KEY，CHROMA_DATA_DIR，其中OPENAI_API_KEY是利用评估gpt-4.1执行结果

执行 python /home/zong/Documents/MCPSafety/tests/benchmark/test_benchmark_web_search.py 进行评测

## Docker 
### build
``` shell
docker build -t mcpsafety .
```

### Run
``` shell
docker run --rm -v $(pwd):/app -w /app mcpsafety bash -c "PYTHONPATH=. python tests/benchmark/test_benchmark_financial_analysis.py"
```