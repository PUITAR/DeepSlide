import streamlit as st
import os
import json
import pandas as pd
from dotenv import load_dotenv
import sys
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

with st.sidebar:
    st.header("输入逻辑链条")
    default_text = "\n".join([
        "1. 深度学习简介",
        "2. 神经网络基础",
        "3. 反向传播算法",
        "4. 自然语言处理应用",
        "5. 未来趋势"
    ])
    logic_text = st.text_area("每行一个节点", value=default_text, height=180)
    if st.button("生成矩阵"):
        nodes = [line.strip() for line in logic_text.splitlines() if line.strip()]
        st.session_state.nodes = nodes
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            env_path = os.path.join(project_root, 'deepslide', 'config', 'env', '.env')
            load_dotenv(env_path)
            generator = MatrixGenerator()
            matrix = generator.generate_matrix(nodes)
        except Exception:
            n = len(nodes)
            matrix = [["" for _ in range(n)] for _ in range(n)]
        st.session_state.matrix_strings = matrix
        n = len(nodes)
        bool_matrix = [[bool(matrix[i][j]) and i != j for j in range(n)] for i in range(n)]
        df = pd.DataFrame(bool_matrix, index=[f"{i+1}. {nodes[i]}" for i in range(n)], columns=[f"{i+1}" for i in range(n)])
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
        df = st.session_state.adjacency
        edges = []
        for i in range(len(nodes)):
            for j in range(len(nodes)):
                if i == j:
                    continue
                val = df.iloc[i, j]
                if bool(val):
                    reason = matrix_strings[i][j] if i < len(matrix_strings) and j < len(matrix_strings[i]) and matrix_strings[i][j] else ""
                    edges.append({"from_index": i, "to_index": j, "from": nodes[i], "to": nodes[j], "reason": reason})
        st.session_state.final_edges = edges
        st.session_state.stage = "CONFIRM"
        st.rerun()
    if col2.button("重置"):
        st.session_state.stage = "INPUT"
        st.session_state.nodes = []
        st.session_state.matrix_strings = []
        st.session_state.adjacency = None
        st.session_state.final_edges = []
        st.rerun()

elif st.session_state.stage == "CONFIRM":
    st.subheader("确认最终逻辑链条")
    nodes = st.session_state.nodes
    edges = st.session_state.detailed_edges or st.session_state.final_edges
    st.write(f"节点数：{len(nodes)}，关系数：{len(edges)}")
    dot_lines = ["digraph G {"]
    for i, n in enumerate(nodes):
        label = f"{i+1}. {n}"
        dot_lines.append(f'  "{label}"')
    for e in edges:
        src = f'{e["from_index"]+1}. {e["from"]}'
        dst = f'{e["to_index"]+1}. {e["to"]}'
        dot_lines.append(f'  "{src}" -> "{dst}"')
    dot_lines.append("}")
    st.graphviz_chart("\n".join(dot_lines))
    st.write("关系列表")
    st.json(edges)
    col1, col2, col3 = st.columns(3)
    with col1:
        result = {
            "nodes": nodes,
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
                st.session_state.detailed_edges = explainer.explain(nodes, st.session_state.final_edges)
            st.rerun()
        except Exception as e:
            st.error(f"生成说明失败: {e}")
            st.session_state.detailed_edges = st.session_state.final_edges
            # st.rerun() # 出错不强制刷新，保留错误提示

    if st.button("✅ 完成流程"):
        # 自动保存到本地 presenter 目录
        try:
            local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logic_chain.json")
            result = {
                "nodes": nodes,
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
