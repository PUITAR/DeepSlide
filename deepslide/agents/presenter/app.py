import streamlit as st
import os
import json
import pandas as pd
from dotenv import load_dotenv
import sys
from html import escape as html_escape
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if project_root not in sys.path:
    sys.path.append(project_root)
from deepslide.agents.presenter.matrix_generator import MatrixGenerator
from deepslide.agents.presenter.relationship_explainer import RelationshipExplainer

st.set_page_config(page_title="逻辑链条矩阵编辑器", layout="wide")
st.title("🧩 逻辑链条矩阵编辑器")

if "stage" not in st.session_state:
    st.session_state.stage = "INPUT"
if "nodes" not in st.session_state:
    st.session_state.nodes = []
if "matrix_strings" not in st.session_state:
    st.session_state.matrix_strings = []
if "adjacency" not in st.session_state:
    st.session_state.adjacency = None
if "final_edges" not in st.session_state:
    st.session_state.final_edges = []
if "detailed_edges" not in st.session_state:
    st.session_state.detailed_edges = []
if "raw_nodes_data" not in st.session_state:
    st.session_state.raw_nodes_data = []

# Load upstream data
upstream_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "combine124_output.json")
upstream_data = None
if os.path.exists(upstream_path):
    try:
        with open(upstream_path, "r", encoding="utf-8") as f:
            upstream_data = json.load(f)
    except Exception:
        pass

def get_node_label(node):
    role = node.get("role", "Node")
    text = node.get("text", "")
    # Truncate text for display
    short_text = (text[:15] + '..') if len(text) > 15 else text
    return f"{role}: {short_text}"

with st.sidebar:
    st.header("输入逻辑链条")
    
    template = "自定义"
    selected_nodes = []
    
    if upstream_data and "chains" in upstream_data:
        templates = list(upstream_data["chains"].keys())
        template = st.selectbox("选择逻辑链条模版", ["自定义"] + templates, index=1 if templates else 0)
    
    if template == "自定义":
        default_text = "\n".join([
            "1. 深度学习简介",
            "2. 神经网络基础",
            "3. 反向传播算法",
            "4. 自然语言处理应用",
            "5. 未来趋势"
        ])
        logic_text = st.text_area("每行一个节点", value=default_text, height=180)
        nodes_to_use = [line.strip() for line in logic_text.splitlines() if line.strip()]
        current_raw_nodes = []
        upstream_edges = []
    else:
        # Show Requirements
        if "requirements" in upstream_data:
            reqs = upstream_data["requirements"]
            st.markdown("### 需求摘要")
            st.markdown(f"**受众**: {reqs.get('audience', '-')}")
            st.markdown(f"**时长**: {reqs.get('duration', '-')}")
            st.markdown(f"**风格**: {reqs.get('style', '-')}")
            st.markdown("---")

        if "reasons" in upstream_data and template in upstream_data["reasons"]:
            st.info(upstream_data["reasons"][template])
        
        chain_data = upstream_data["chains"][template]
        raw_nodes = chain_data.get("nodes", [])
        nodes_to_use = [get_node_label(n) for n in raw_nodes]
        current_raw_nodes = raw_nodes
        upstream_edges = chain_data.get("edges", [])
        
        st.caption("节点预览：")
        st.code("\n".join(nodes_to_use), language=None)

    btn_label = "加载链条" if template != "自定义" else "生成矩阵"
    if st.button(btn_label):
        # Initialize generator and env first
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            env_path = os.path.join(project_root, 'deepslide', 'config', 'env', '.env')
            load_dotenv(env_path)
            generator = MatrixGenerator()
        except Exception:
            generator = None

        final_nodes = nodes_to_use
        
        # If using upstream data, try to summarize nodes using LLM
        if template != "自定义" and generator:
            with st.spinner("正在智能概括节点内容..."):
                try:
                    summarized = generator.summarize_nodes(current_raw_nodes)
                    if summarized and len(summarized) == len(current_raw_nodes):
                        final_nodes = summarized
                except Exception as e:
                    st.warning(f"概括失败，使用默认截断: {e}")

        st.session_state.nodes = final_nodes
        st.session_state.raw_nodes_data = current_raw_nodes
        st.session_state.current_template = template # Track template
        
        n = len(final_nodes)
        matrix = [["" for _ in range(n)] for _ in range(n)]

        if template != "自定义" and upstream_edges:
            # Load from upstream edges
            for e in upstream_edges:
                f_idx = e.get("from_index")
                t_idx = e.get("to_index")
                reason = e.get("reason", "Linked")
                if f_idx is not None and t_idx is not None and 0 <= f_idx < n and 0 <= t_idx < n:
                    matrix[f_idx][t_idx] = reason
        else:
            # Generate using LLM if generator is available
            if generator:
                try:
                    matrix = generator.generate_matrix(final_nodes)
                except Exception:
                    pass
        
        st.session_state.matrix_strings = matrix
        bool_matrix = [[bool(matrix[i][j]) and i != j for j in range(n)] for i in range(n)]
        df = pd.DataFrame(bool_matrix, index=[f"{i+1}. {final_nodes[i]}" for i in range(n)], columns=[f"{i+1}" for i in range(n)])
        st.session_state.adjacency = df
        st.session_state.stage = "EDIT"
        st.rerun()

if st.session_state.stage == "INPUT":
    st.info("在左侧输入逻辑链条并点击“生成矩阵”。")

elif st.session_state.stage == "EDIT":
    st.subheader("编辑二维逻辑联系图表")
    st.caption("行与列对应各节点。勾选表示存在直接逻辑联系。对角线将忽略。")
    edited = st.data_editor(
        st.session_state.adjacency,
        use_container_width=True,
        num_rows="fixed"
    )
    st.session_state.adjacency = edited
    col1, col2 = st.columns(2)
    if col1.button("确认矩阵"):
        nodes = st.session_state.nodes
        matrix_strings = st.session_state.matrix_strings
        raw_nodes = st.session_state.get("raw_nodes_data", [])
        df = st.session_state.adjacency
        edges = []
        for i in range(len(nodes)):
            for j in range(len(nodes)):
                if i == j:
                    continue
                val = df.iloc[i, j]
                if bool(val):
                    reason = matrix_strings[i][j] if i < len(matrix_strings) and j < len(matrix_strings[i]) and matrix_strings[i][j] else ""
                    
                    # Use raw node data if available and matching length
                    if raw_nodes and len(raw_nodes) == len(nodes):
                        from_val = raw_nodes[i]
                        to_val = raw_nodes[j]
                    else:
                        from_val = nodes[i]
                        to_val = nodes[j]
                        
                    edges.append({
                        "from_index": i, 
                        "to_index": j, 
                        "from": from_val, 
                        "to": to_val, 
                        "reason": reason
                    })
        st.session_state.final_edges = edges
        st.session_state.stage = "CONFIRM"
        st.rerun()
    if col2.button("重置"):
        st.session_state.stage = "INPUT"
        st.session_state.nodes = []
        st.session_state.matrix_strings = []
        st.session_state.adjacency = None
        st.session_state.final_edges = []
        st.session_state.raw_nodes_data = []
        st.session_state.current_template = "自定义"
        st.rerun()

elif st.session_state.stage == "CONFIRM":
    st.subheader("确认最终逻辑链条")
    nodes = st.session_state.nodes
    
    # Recovery mechanism: If raw_nodes_data is empty but we have a known template
    if not st.session_state.raw_nodes_data and st.session_state.get("current_template", "自定义") != "自定义":
        tmpl = st.session_state.current_template
        if upstream_data and "chains" in upstream_data and tmpl in upstream_data["chains"]:
            st.session_state.raw_nodes_data = upstream_data["chains"][tmpl].get("nodes", [])
            st.toast(f"已恢复上游原始数据 ({len(st.session_state.raw_nodes_data)} 节点)", icon="🔄")

    edges = st.session_state.detailed_edges or st.session_state.final_edges
    st.write(f"节点数：{len(nodes)}，关系数：{len(edges)}")
    
    # Modern SVG graph (replaces GraphViz)
    count = len(nodes)
    W, H = 880, 500
    cx, cy = W // 2, H // 2
    r = min(W, H) // 2 - 80
    positions = []
    for idx in range(count):
        angle = (2 * 3.1415926 * idx) / max(count, 1) - 3.1415926 / 2
        x = cx + r * (float(__import__('math').cos(angle)))
        y = cy + r * (float(__import__('math').sin(angle)))
        positions.append((x, y))

    # Style
    st.markdown(
        """
        <style>
          .ds-graph { border: 1px solid #e5e7eb; border-radius: 12px; background: #ffffff; box-shadow: 0 8px 24px rgba(2,6,23,0.08); }
          .ds-legend { display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap:14px; padding: 16px 18px; }
          .ds-node-pill { display:inline-flex; align-items:center; justify-content:center; width:24px; height:24px; border-radius:999px; background:#eef2ff; color:#4338ca; border:1px solid #c7d2fe; font-size:12px; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Build SVG
    svg_parts = []
    svg_parts.append(f"<svg width='{W}' height='{H}' xmlns='http://www.w3.org/2000/svg'>")
    svg_parts.append(
        "<defs>\n"
        "  <marker id='arrow' viewBox='0 0 10 10' refX='10' refY='5' markerUnits='strokeWidth' markerWidth='8' markerHeight='8' orient='auto'>\n"
        "    <path d='M 0 0 L 10 5 L 0 10 z' fill='#6366f1' />\n"
        "  </marker>\n"
        "</defs>"
    )
    # Edges
    for e in edges:
        if not (0 <= e["from_index"] < count and 0 <= e["to_index"] < count):
            continue
        fx, fy = positions[e["from_index"]]
        tx, ty = positions[e["to_index"]]
        dx, dy = tx - fx, ty - fy
        curve = 0.18
        cx1, cy1 = fx + dy * curve, fy - dx * curve
        cx2, cy2 = tx + dy * curve * 0.2, ty - dx * curve * 0.2
        
        detail = e.get("detail", "")
        reason = e.get("reason", "")
        tooltip = html_escape(detail if detail else reason)
        # Highlight edges with details
        stroke_width = "3" if detail else "2"
        stroke_color = "#2563eb" if detail else "#6366f1"
        opacity = "1.0" if detail else "0.9"

        svg_parts.append(
            f"<path d='M {fx:.1f} {fy:.1f} C {cx1:.1f} {cy1:.1f}, {cx2:.1f} {cy2:.1f}, {tx:.1f} {ty:.1f}' stroke='{stroke_color}' stroke-width='{stroke_width}' fill='none' marker-end='url(#arrow)' opacity='{opacity}'>"
        )
        svg_parts.append(f"<title>{tooltip}</title>")
        svg_parts.append("</path>")
    # Nodes
    for i, (x, y) in enumerate(positions):
        svg_parts.append(f"<g transform='translate({x:.1f},{y:.1f})'>")
        svg_parts.append("<circle r='22' fill='#f8fafc' stroke='#cbd5e1' stroke-width='2'/>")
        svg_parts.append(f"<text x='0' y='5' text-anchor='middle' font-size='12' fill='#0f172a'>{i+1}</text>")
        svg_parts.append("</g>")
    svg_parts.append("</svg>")
    st.markdown(f"<div class='ds-graph'>{''.join(svg_parts)}</div>", unsafe_allow_html=True)

    # Legend
    legend_items = []
    for i, n in enumerate(nodes):
        safe = html_escape(n)
        legend_items.append(
            f"<div class='flex items-center gap-2 text-sm text-gray-700'><span class='ds-node-pill'>{i+1}</span><span class='truncate' title='{safe}'>{safe}</span></div>"
        )
    st.markdown(f"<div class='ds-legend'>{''.join(legend_items)}</div>", unsafe_allow_html=True)
    st.write("关系列表")
    st.json(edges)
    col1, col2, col3 = st.columns(3)
    with col1:
        # Use full data if available
        final_nodes_output = st.session_state.raw_nodes_data if st.session_state.raw_nodes_data else nodes
        result = {
            "nodes": final_nodes_output,
            "edges": edges
        }
        st.download_button(
            label="📥 下载逻辑链条 JSON",
            data=json.dumps(result, ensure_ascii=False, indent=2),
            file_name="logic_chain.json",
            mime="application/json"
        )
    
    if col2.button("返回编辑"):
        st.session_state.stage = "EDIT"
        st.rerun()
    
    if col3.button("生成详细说明"):
        try:
            env_path = os.path.join(project_root, 'deepslide', 'config', 'env', '.env')
            load_dotenv(env_path)
            explainer = RelationshipExplainer()
            with st.spinner("正在分析逻辑关系..."):
                # Use full text for explanation to ensure quality
                if st.session_state.raw_nodes_data:
                    explainer_nodes = [n.get("text", "") for n in st.session_state.raw_nodes_data]
                else:
                    explainer_nodes = nodes
                st.session_state.detailed_edges = explainer.explain(explainer_nodes, st.session_state.final_edges)
            st.rerun()
        except Exception as e:
            st.error(f"生成说明失败: {e}")
            st.session_state.detailed_edges = st.session_state.final_edges
            # st.rerun() # 出错不强制刷新，保留错误提示

    if st.button("✅ 完成流程"):
        # 自动保存到本地 presenter 目录
        try:
            local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logic_chain.json")
            final_nodes_output = st.session_state.raw_nodes_data if st.session_state.raw_nodes_data else nodes
            result = {
                "nodes": final_nodes_output,
                "edges": edges
            }
            with open(local_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            st.toast(f"已自动保存至: {local_path}", icon="💾")
        except Exception as e:
            st.error(f"自动保存失败: {e}")
            
        st.session_state.stage = "DONE"
        st.rerun()

elif st.session_state.stage == "DONE":
    st.success("流程完成")
    st.button("重新开始", on_click=lambda: (
        st.session_state.update({
            "stage": "INPUT",
            "nodes": [],
            "matrix_strings": [],
            "adjacency": None,
            "final_edges": []
        }),
        st.rerun()
    ))
