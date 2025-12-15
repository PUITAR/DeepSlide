from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import os

app = Flask(__name__)
CORS(app)

# demo graph data
DEMO = {
  "nodes": [
    {"id": "1", "label": "abs"},
    {"id": "2", "label": "intro"},
    {"id": "3", "label": "method"},
  ],
  "sequence": ["1", "2", "3"],
  "relations": [
    {"from": "1", "to": "2", "weight": 0.8, "desc": "detail"},
    {"from": "3", "to": "1", "weight": 0.4, "desc": "recall"},
  ],
}

def validate_graph(g):
  """
  验证图数据的有效性：
  1. 顺序边必须是哈密尔顿路径（包含所有节点，不重复）。
  2. 关联边必须引用存在的节点，且权重为数字，描述为文本。
  """
  ids = {n["id"] for n in g.get("nodes", [])}
  seq = g.get("sequence", [])
  
  # 顺序边校验
  if len(seq) != len(ids):
    return False, "sequence length must equal nodes count"
  if len(set(seq)) != len(seq):
    return False, "sequence contains duplicates"
  if set(seq) != ids:
    return False, "sequence must include all node ids"
  
  # 关联边校验
  for r in g.get("relations", []):
    if r.get("from") not in ids or r.get("to") not in ids:
      return False, "relation references unknown node"
    if not isinstance(r.get("weight"), (int, float)):
      return False, "relation weight must be numeric"
    if not isinstance(r.get("desc"), str):
      return False, "relation desc must be text"
  
  return True, "ok"

@app.route("/api/graph", methods=["GET", "POST"])
def api_graph():
  if request.method == "GET":
    return jsonify(DEMO)
  try:
    data = request.get_json(force=True)
  except:
    return jsonify({"ok": False, "error": "Invalid JSON format"}), 400
      
  ok, msg = validate_graph(data)
  
  if not ok:
    return jsonify({"ok": False, "error": msg}), 400
  
  return jsonify({"ok": True, "graph": data})

@app.route("/")
def serve_index():
  return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    # 确保只提供同目录下的静态文件
  return send_from_directory(os.getcwd(), path)

if __name__ == "__main__":
    # 需要安装 Flask 和 flask_cors: pip install Flask flask-cors
  app.run(host="0.0.0.0", port=8101, debug=True)