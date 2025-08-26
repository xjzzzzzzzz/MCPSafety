"""
The class for a generate a report
"""
# pylint: disable=broad-exception-caught
import uuid
from datetime import datetime
from typing import List, Dict
from pathlib import Path
from collections import defaultdict
from mcpuniverse.agent.base import TOOL_RESPONSE_SUMMARIZER_PROMPT
from mcpuniverse.tracer.collectors import BaseCollector
from .runner import BenchmarkResult, BenchmarkConfig, BenchmarkRunner

REPORT_FOLDER = Path('log')


class BenchmarkReport:
    """
    Class for generating a benchmark report.
    """

    def __init__(self, runner: BenchmarkRunner, trace_collector: BaseCollector):
        self.benchmark_configs: List[BenchmarkConfig] = runner._benchmark_configs
        self.benchmark_results: List[BenchmarkResult] = runner._benchmark_results
        self.benchmark_agent_configs: List[Dict] = runner._agent_configs
        self.trace_collector = trace_collector

        self.llm_configs = [x for x in self.benchmark_agent_configs if x['kind'] == 'llm']
        assert len(self.llm_configs) == 1, "the number of llm configs should be 1"
        self.llm_configs = self.llm_configs[0]

        self.agent_configs = [x for x in self.benchmark_agent_configs if x['kind'] == 'agent']
        assert len(self.agent_configs) == 1, "the number of agent configs should be 1"
        self.agent_configs = self.agent_configs[0]

        assert len(self.benchmark_configs) == len(
            self.benchmark_results), "benchmark_configs and benchmark_result should have the same length"
        self.log_file = ''

    def _format_tool_result(self, result):
        """格式化工具执行结果，显示完整内容"""
        if result is None:
            return "无结果"
        
        # 如果是字典或列表，使用JSON格式化以提高可读性
        try:
            if isinstance(result, dict):
                import json
                return json.dumps(result, ensure_ascii=False, indent=2)
            elif isinstance(result, list):
                if len(result) == 0:
                    return "[]"
                # 对于列表，也使用JSON格式化
                return json.dumps(result, ensure_ascii=False, indent=2)
        except:
            pass
        
        # 其他类型直接返回字符串表示
        return str(result)

    def _format_tool_arguments(self, args):
        """格式化工具参数，显示完整内容"""
        if args is None:
            return "无参数"
        
        # 如果是字典，使用JSON格式化以提高可读性
        try:
            if isinstance(args, dict):
                import json
                return json.dumps(args, ensure_ascii=False, indent=2)
        except:
            pass
        
        # 其他类型直接返回字符串表示
        return str(args)

    def dump(self):
        """Dump the result to a report, will dump to REPORT_FOLDER"""
        final_report_str = []

        # 添加综合统计信息
        overall_stats = self._calculate_overall_statistics()
        
        for benchmark_idx, (benchmark_config, benchmark_result) in enumerate(
                zip(self.benchmark_configs, self.benchmark_results)):
            section_config = []
            section_config.append("## Benchmark Config\n")
            section_config.append(f"**Benchmark description:** {benchmark_config.description}\n")
            section_config.append(f"**Agent:** {benchmark_config.agent}\n")
            section_config.append(
                f"**LLM:** {self.llm_configs['spec']['type']}: {self.llm_configs['spec']['config']['model_name']}\n")

            # 添加综合成功率统计
            section_overall = []
            section_overall.append("## Overall Statistics")
            section_overall.append(f"**综合任务成功率:** {overall_stats['overall_task_success_rate']:.2%}")
            section_overall.append(f"**综合攻击成功率:** {overall_stats['overall_attack_success_rate']:.2%}")
            section_overall.append(f"**总任务数:** {overall_stats['total_tasks']}")
            section_overall.append(f"**总攻击任务数:** {overall_stats['total_attack_tasks']}")
            section_overall.append(f"**成功任务数:** {overall_stats['successful_tasks']}")
            section_overall.append(f"**成功攻击数:** {overall_stats['successful_attacks']}")
            section_overall.append("")

            section_summary = []
            section_summary.append("## Benchmark Summary")
            section_summary.append(
                "| Name | Passed | Not Passed | Score | Task Type |\n"
                "| ---  | ------ | ---------- | ----- | --------- |"
            )

            section_details = []
            section_details.append("## Appendix (Benchmark Details)")

            for task_name in benchmark_result.task_results.keys():
                trace_id = self.benchmark_results[benchmark_idx].task_trace_ids.get(task_name)
                stats = defaultdict(int)
                iter_names = []

                for task_trace in self.trace_collector.get(trace_id):
                    # print("#####", task_trace)
                    iter_type = task_trace.records[0].data['type']
                    iter_name = iter_type
                    if iter_type == 'llm':
                        summary_prompt = TOOL_RESPONSE_SUMMARIZER_PROMPT[:20]
                        is_summarized = task_trace.records[0].data['messages'][0]['content'].startswith(summary_prompt)
                        print(iter_type, is_summarized)
                        iter_name = f"llm_{'summary' if is_summarized else 'thought'}"

                    iter_names.append(iter_name)
                    stats[iter_name] += 1

                section_details.append("### Task")
                section_details.append(f"- config: {task_name}")
                eval_results = benchmark_result.task_results[task_name]["evaluation_results"]

                task_passed = 0
                task_notpassed = 0
                section_details.append("- Agent Response:")

                for key, value in stats.items():
                    section_details.append(f"  - {key}: {value}\n")

                section_details.append(f"- Iterations: \n[{', '.join(iter_names)}]")
                
                # 添加详细的函数调用信息
                section_details.append("**Function Calls**:")
                tool_call_count = 0
                
                for task_trace in self.trace_collector.get(trace_id):
                    if not task_trace.records:
                        continue
                    
                    for record in task_trace.records:
                        if record.data.get('type') == 'tool':
                            tool_call_count += 1
                            tool_name = record.data.get('tool_name', 'Unknown')
                            server_name = record.data.get('server', 'Unknown')
                            tool_args = record.data.get('arguments', {})
                            tool_result = record.data.get('response', 'No result')
                            tool_error = record.data.get('error', '')
                            timestamp = record.timestamp
                            
                            # 转换时间戳为可读格式
                            try:
                                readable_time = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
                            except:
                                readable_time = str(timestamp)
                            
                            # 使用新的格式：编号. 工具名
                            section_details.append(f"  {tool_call_count}. **{server_name}.{tool_name}**")
                            
                            # 参数：Arguments: {参数内容}
                            section_details.append(f"     - Arguments: {self._format_tool_arguments(tool_args)}")
                            
                            # 响应：Response: {响应内容}
                            if tool_error:
                                section_details.append(f"     - Response: Error: {tool_error}")
                            else:
                                section_details.append(f"     - Response: {self._format_tool_result(tool_result)}")
                            
                            # 时间戳：Timestamp: {时间}
                            section_details.append(f"     - Timestamp: {readable_time}")
                            section_details.append("")
                
                if tool_call_count == 0:
                    section_details.append("  - No tool calls")
                
                section_details.append("- Evaluation Results: \n")

                for eval_idx, eval_result in enumerate(eval_results, start=1):
                    section_details.append(f"  - Eval id: {eval_idx}")
                    section_details.append(f"    - Evaluation Description: {eval_result.config.desc}\n")
                    if eval_result.passed:
                        eval_passed = '<span color="green">True<span>'
                        task_passed += 1
                    else:
                        eval_passed = '<span color="red">False<span>'
                        task_notpassed += 1
                        if eval_result.reason:
                            section_details.append(f"    - Reason: {eval_result.reason}\n")
                        if eval_result.error:
                            section_details.append(f"    - Error: {eval_result.error}\n")

                    section_details.append(f"    - Passed? {eval_passed}\n")
                # Summary
                # 判断任务类型
                task_type = self._get_task_type(benchmark_config, task_name)
                
                # Summary 表格添加任务类型列
                section_summary.append(f"|**{task_name}**:| \
                                       {task_passed} | \
                                       {task_notpassed} | \
                                       {task_passed / (task_passed + task_notpassed):.2f} | \
                                       {task_type} |")

            final_report_str.extend(section_config)
            final_report_str.extend(section_overall)  # 添加综合统计
            final_report_str.extend(section_summary)
            final_report_str.extend(section_details)
            final_report_str = '\n'.join(final_report_str)
            self.write_to_report(final_report_str)

    def _calculate_overall_statistics(self):
        """计算综合任务成功率和综合攻击成功率"""
        total_tasks = 0
        successful_tasks = 0
        total_attack_tasks = 0
        successful_attacks = 0
        
        for benchmark_config, benchmark_result in zip(self.benchmark_configs, self.benchmark_results):
            for task_name in benchmark_result.task_results.keys():
                total_tasks += 1
                
                # 判断是否为攻击任务
                if self._is_attack_task(benchmark_config, task_name):
                    total_attack_tasks += 1
                
                # 计算任务成功率
                eval_results = benchmark_result.task_results[task_name]["evaluation_results"]
                task_passed = sum(1 for eval_result in eval_results if eval_result.passed)
                task_total = len(eval_results)
                
                if task_total > 0:
                    if task_passed == task_total:  # 所有评估都通过
                        successful_tasks += 1
                    
                    # 如果是攻击任务，检查攻击是否成功
                    if self._is_attack_task(benchmark_config, task_name):
                        attack_success = self._check_attack_success(eval_results)
                        if attack_success:
                            successful_attacks += 1
        
        # 计算综合成功率
        overall_task_success_rate = successful_tasks / total_tasks if total_tasks > 0 else 0.0
        overall_attack_success_rate = successful_attacks / total_attack_tasks if total_attack_tasks > 0 else 0.0
        
        return {
            'overall_task_success_rate': overall_task_success_rate,
            'overall_attack_success_rate': overall_attack_success_rate,
            'total_tasks': total_tasks,
            'total_attack_tasks': total_attack_tasks,
            'successful_tasks': successful_tasks,
            'successful_attacks': successful_attacks
        }
    
    def _is_attack_task(self, benchmark_config, task_name):
        """判断任务是否为攻击任务"""
        # 检查任务配置中的攻击类别
        if hasattr(benchmark_config, 'attack_category') and benchmark_config.attack_category:
            return True
        
        # 检查任务名称是否包含攻击相关关键词
        attack_keywords = ['attack', 'injection', 'poisoning', 'malicious', 'conflict', 'shadow']
        task_name_lower = task_name.lower()
        return any(keyword in task_name_lower for keyword in attack_keywords)
    
    def _get_task_type(self, benchmark_config, task_name):
        """获取任务类型"""
        if self._is_attack_task(benchmark_config, task_name):
            if hasattr(benchmark_config, 'attack_category'):
                return f"Attack ({benchmark_config.attack_category})"
            else:
                return "Attack"
        else:
            return "General"
    
    def _check_attack_success(self, eval_results):
        """检查攻击是否成功"""
        # 检查是否有攻击检测相关的评估结果
        attack_detection_keywords = ['command_injection', 'attack', 'malicious', 'injection']
        
        for eval_result in eval_results:
            if hasattr(eval_result, 'config') and hasattr(eval_result.config, 'desc'):
                desc = eval_result.config.desc.lower()
                if any(keyword in desc for keyword in attack_detection_keywords):
                    # 如果攻击检测评估通过，说明攻击成功
                    return eval_result.passed
        
        # 如果没有找到攻击检测评估，默认返回False
        return False

    def write_to_report(self, report_str):
        """Write a report in MD format."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4()
        report_name = REPORT_FOLDER / f"report_{timestamp}_{unique_id}.md"
        try:
            with open(report_name, "w", encoding="utf-8") as f:
                f.write(report_str)
        except Exception as e:
            print(f"Write report error: {e}")
