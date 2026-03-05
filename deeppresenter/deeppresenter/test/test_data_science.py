"""
Test data science tools with complete pipeline.
"""

import pytest


class TestDataSciencePipeline:
    """Test data science tools with complete pipeline."""

    @pytest.mark.asyncio
    async def test_full_data_visualization_pipeline(
        self, agent_env, workspace, tool_call_helper
    ):
        """Test complete pipeline: numpy+pandas+matplotlib+seaborn with chinese labels."""
        script_content = """
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns

# Configure chinese fonts
plt.rcParams['font.sans-serif'] = ['Noto Sans CJK SC', 'WenQuanYi Zen Hei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# Generate sample data
np.random.seed(42)
data = pd.DataFrame({
    '日期': pd.date_range('2024-01-01', periods=100),
    '数值': np.random.randn(100).cumsum(),
    '类别': np.random.choice(['产品A', '产品B', '产品C'], 100),
    '销量': np.random.randint(10, 100, 100)
})

# Save raw data to CSV
data.to_csv('原始数据.csv', index=False, encoding='utf-8')

# Create complex visualizations
fig, axes = plt.subplots(2, 2, figsize=(14, 12))

# Plot 1: Time series line plot
axes[0, 0].plot(data['日期'], data['数值'], linewidth=2, color='steelblue')
axes[0, 0].set_title('时间序列趋势图', fontsize=14, fontweight='bold')
axes[0, 0].set_xlabel('日期', fontsize=12)
axes[0, 0].set_ylabel('累计数值', fontsize=12)
axes[0, 0].grid(True, alpha=0.3)

# Plot 2: Distribution histogram with seaborn
axes[0, 1].hist(data['数值'], bins=20, edgecolor='black', alpha=0.7, color='coral')
axes[0, 1].set_title('数值分布直方图', fontsize=14, fontweight='bold')
axes[0, 1].set_xlabel('数值范围', fontsize=12)
axes[0, 1].set_ylabel('频次', fontsize=12)

# Plot 3: Seaborn box plot by category
sns.boxplot(data=data, x='类别', y='销量', ax=axes[1, 0], palette='Set2')
axes[1, 0].set_title('各产品销量箱线图', fontsize=14, fontweight='bold')
axes[1, 0].set_xlabel('产品类别', fontsize=12)
axes[1, 0].set_ylabel('销量', fontsize=12)

# Plot 4: Seaborn scatter plot with regression
for cat in data['类别'].unique():
    cat_data = data[data['类别'] == cat]
    axes[1, 1].scatter(cat_data.index, cat_data['数值'], label=cat, alpha=0.6, s=50)
axes[1, 1].set_title('散点分布图（按类别）', fontsize=14, fontweight='bold')
axes[1, 1].set_xlabel('时间索引', fontsize=12)
axes[1, 1].set_ylabel('数值', fontsize=12)
axes[1, 1].legend(fontsize=10)
axes[1, 1].grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('数据可视化报告.png', dpi=100, bbox_inches='tight')

# Create detailed summary report
summary = f'''数据分析与可视化报告
{'='*50}

数据集信息:
- 总记录数: {len(data)}
- 日期范围: {data["日期"].min().strftime("%Y-%m-%d")} 至 {data["日期"].max().strftime("%Y-%m-%d")}
- 数值范围: {data["数值"].min():.2f} 至 {data["数值"].max():.2f}
- 平均数值: {data["数值"].mean():.2f}
- 标准差: {data["数值"].std():.2f}

各类别统计:
{data.groupby("类别")["销量"].describe().to_string()}

生成文件:
- 原始数据.csv: 原始数据导出
- 数据可视化报告.png: 综合可视化图表

使用工具:
- NumPy {np.__version__}
- Pandas {pd.__version__}
- Matplotlib {matplotlib.__version__}
- Seaborn {sns.__version__}
'''

with open('分析报告.txt', 'w', encoding='utf-8') as f:
    f.write(summary)

print('Pipeline completed successfully')
print(f'Files created: 原始数据.csv, 数据可视化报告.png, 分析报告.txt')
"""
        write_call = tool_call_helper(
            "write_file",
            {"path": str(workspace / "pipeline.py"), "content": script_content},
        )
        await agent_env.tool_execute(write_call)

        exec_call = tool_call_helper(
            "execute_command",
            {"command": f"python {workspace / 'pipeline.py'}"},
        )
        exec_result = await agent_env.tool_execute(exec_call)
        assert not exec_result.is_error, f"pipeline failed: {exec_result.text}"
        assert "Pipeline completed successfully" in exec_result.text

        # Verify all files created
        list_call = tool_call_helper(
            "list_directory",
            {"path": str(workspace)},
        )
        list_result = await agent_env.tool_execute(list_call)
        assert "原始数据.csv" in list_result.text
        assert "数据可视化报告.png" in list_result.text
        assert "分析报告.txt" in list_result.text
