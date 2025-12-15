let graphData = { nodes: [], sequence: [], relations: [], positions: {}, selected: null } 

const svg = document.getElementById('graph')
const seqList = document.getElementById('sequenceList')
const statusDiv = document.getElementById('status')
const ioJson = document.getElementById('ioJson')
const selectionInfo = document.getElementById('selectionInfo')
const selectedType = document.getElementById('selectedType')
const selectedDetails = document.getElementById('selectedDetails')
const deleteElementBtn = document.getElementById('deleteElement')

// --- 绑定事件处理函数 (保持不变) ---

document.getElementById('loadDemo').onclick = async () => {
    try {
        const res = await fetch('/api/graph')
        const data = await res.json()
        graphData = { ...data, positions: {} } 
        if (graphData.nodes.length > 0 && !graphData.positions[graphData.nodes[0].id]) {
            setDefaultPositions()
        }
        render()
        statusDiv.textContent = '已加载示例图。'
    } catch (e) {
        graphData = { nodes: [{id:'A',label:'Service A'},{id:'B',label:'DB B'},{id:'C',label:'Worker C'}], sequence:['A','B','C'], relations:[{from:'A',to:'B',weight:0.8,desc:'reads/writes'},{from:'C',to:'A',weight:0.4,desc:'consumes'}], positions: {}, selected: null }
        setDefaultPositions()
        render()
        statusDiv.textContent = '无法连接到后端 API，已加载本地示例数据。'
    }
}

document.getElementById('submitGraph').onclick = async () => {
    try {
        const payload = { nodes: graphData.nodes, sequence: graphData.sequence, relations: graphData.relations }
        const res = await fetch('/api/graph', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
        const j = await res.json()
        statusDiv.textContent = j.ok ? '已提交并通过校验' : ('校验失败：' + (j.error || '未知错误'))
    } catch (e) {
        statusDiv.textContent = '提交失败：网络错误或服务器未运行。'
    }
}

document.getElementById('addRel').onclick = () => {
    const from = document.getElementById('relFrom').value.trim()
    const to = document.getElementById('relTo').value.trim()
    const weight = parseFloat(document.getElementById('relWeight').value)
    const desc = document.getElementById('relDesc').value.trim()
    if (!from || !to || Number.isNaN(weight) || !desc) { statusDiv.textContent = '请输入完整关系'; return }
    const nodeIds = new Set(graphData.nodes.map(n => n.id))
    if (!nodeIds.has(from) || !nodeIds.has(to)) {
        statusDiv.textContent = '关联边引用的节点不存在。'; return
    }
    graphData.relations.push({ from, to, weight, desc })
    document.getElementById('relFrom').value = ''
    document.getElementById('relTo').value = ''
    document.getElementById('relWeight').value = ''
    document.getElementById('relDesc').value = ''
    statusDiv.textContent = `已添加关联边 ${from} -> ${to}。`
    render()
}

document.getElementById('addNodeBtn').onclick = () => {
    const id = document.getElementById('newNodeId').value.trim()
    const label = document.getElementById('newNodeLabel').value.trim()
    if (!id) { statusDiv.textContent = '节点ID不能为空'; return }
    if (graphData.nodes.some(n => n.id === id)) { statusDiv.textContent = `节点ID ${id} 已存在`; return }
    const W = svg.clientWidth || 800
    const H = svg.clientHeight || 600
    graphData.nodes.push({ id, label: label || id })
    graphData.sequence.push(id) 
    graphData.positions[id] = { x: W / 2, y: H / 2 }
    document.getElementById('newNodeId').value = ''
    document.getElementById('newNodeLabel').value = ''
    statusDiv.textContent = `已添加新节点 ${id}。`
    render()
}

document.getElementById('exportGraph').onclick = () => {
    const exportData = { 
        nodes: graphData.nodes, sequence: graphData.sequence, 
        relations: graphData.relations, positions: graphData.positions 
    }
    ioJson.value = JSON.stringify(exportData, null, 2)
    statusDiv.textContent = '图数据已导出到文本框。'
}

document.getElementById('importGraph').onclick = () => {
    try {
        const importData = JSON.parse(ioJson.value)
        if (importData.nodes && Array.isArray(importData.nodes) && importData.sequence && Array.isArray(importData.sequence)) {
            graphData.nodes = importData.nodes
            graphData.sequence = importData.sequence
            graphData.relations = importData.relations || []
            graphData.positions = importData.positions || {}
            if (Object.keys(graphData.positions).length === 0) {
                 setDefaultPositions()
            }
            graphData.selected = null
            selectionInfo.style.display = 'none'
            render()
            statusDiv.textContent = `图数据成功导入，包含 ${graphData.nodes.length} 个节点。`
        } else {
            throw new Error('JSON 格式不正确。')
        }
    } catch (e) {
        statusDiv.textContent = '导入失败：' + e.message
    }
}
deleteElementBtn.onclick = deleteElement


// --- 拖动功能实现 (保持不变) ---
let selectedElement = null
let offset = { x: 0, y: 0 }
function startDrag(e) {
    if (e.target.tagName === 'circle' || e.target.tagName === 'text') {
        const nodeGroup = e.target.closest('.node-group')
        if (!nodeGroup) return
        if (graphData.selected && graphData.selected.id === nodeGroup.dataset.id) {
             e.stopPropagation() 
        }
        selectedElement = nodeGroup
        const nodeID = nodeGroup.dataset.id
        const point = svg.createSVGPoint()
        point.x = e.clientX
        point.y = e.clientY
        const svgP = point.matrixTransform(svg.getScreenCTM().inverse())
        const currentPos = graphData.positions[nodeID] || { x: parseFloat(nodeGroup.getAttribute('data-x')), y: parseFloat(nodeGroup.getAttribute('data-y')) }
        offset.x = svgP.x - currentPos.x
        offset.y = svgP.y - currentPos.y
        svg.addEventListener('mousemove', drag)
        svg.addEventListener('mouseup', endDrag)
        e.preventDefault()
    }
}
function drag(e) {
    if (!selectedElement) return
    const point = svg.createSVGPoint()
    point.x = e.clientX
    point.y = e.clientY
    const svgP = point.matrixTransform(svg.getScreenCTM().inverse())
    let newX = svgP.x - offset.x
    let newY = svgP.y - offset.y
    const nodeID = selectedElement.dataset.id
    graphData.positions[nodeID] = { x: newX, y: newY }
    render(true) 
}
function endDrag() {
    if (selectedElement) {
        selectedElement = null
        svg.removeEventListener('mousemove', drag)
        svg.removeEventListener('mouseup', endDrag)
        statusDiv.textContent = '节点位置已更新。'
    }
}
svg.addEventListener('mousedown', startDrag)


// --- 交互和删除逻辑 ---

/**
 * 允许选择节点和关联边
 */
function selectElement(type, id, data) {
    // 1. 更新内部状态
    graphData.selected = { type, id }
    render(true) 

    // 2. 更新侧边栏
    selectionInfo.style.display = 'block'
    deleteElementBtn.style.display = 'block'
    
    if (type === 'node') {
        selectedType.textContent = `选中节点: ${id}`
        selectedDetails.innerHTML = `标签: ${data.label || data.id}<br>顺序: ${graphData.sequence.indexOf(id) + 1}`
        deleteElementBtn.textContent = `删除节点 ${id}`
    } else if (type === 'relation') {
        selectedType.textContent = `选中关联边: ${data.from} -> ${data.to}`
        selectedDetails.innerHTML = `权重: **${data.weight}**<br>描述: **${data.desc}**`
        deleteElementBtn.textContent = `删除关联边 (${data.desc})`
    }
    
    statusDiv.textContent = `已选中 ${type} ${id}。`
}

/**
 * 允许删除节点和关联边
 */
function deleteElement() {
    if (!graphData.selected) {
        statusDiv.textContent = '请先选择一个节点或边进行删除。'
        return
    }

    const { type, id } = graphData.selected
    
    if (type === 'node') {
        if (confirm(`确定要删除选中的节点 (${id}) 吗？删除节点将同时移除所有关联的边。`)) {
            // 删除节点
            graphData.nodes = graphData.nodes.filter(n => n.id !== id)
            graphData.sequence = graphData.sequence.filter(_id => _id !== id)
            graphData.relations = graphData.relations.filter(r => r.from !== id && r.to !== id)
            delete graphData.positions[id]
            statusDiv.textContent = `节点 ${id} 及其所有关联的边已删除。`
        } else {
            return
        }
    } else if (type === 'relation') {
        if (confirm(`确定要删除选中的关联边 (${id}) 吗？`)) {
            // 删除关联边
            // id 是 'from-to-desc'
            graphData.relations = graphData.relations.filter(r => `${r.from}-${r.to}-${r.desc}` !== id)
            statusDiv.textContent = `关联边 ${id} 已删除。`
        } else {
            return
        }
    } else {
        statusDiv.textContent = '不支持删除该类型的元素。' 
        return
    }

    // 重置选中状态并重新渲染
    graphData.selected = null
    selectionInfo.style.display = 'none'
    render()
}

// --- 辅助函数：曲线调整 (解决边重叠) ---

/**
 * 查找两节点间的所有关联边数量（用于自环和重叠边偏移计算）
 * @param {string} id1 
 * @param {string} id2 
 * @returns {number}
 */
function getEdgeCount(id1, id2) {
    // 使用排序后的键来获取所有 A->B 和 B->A 的边
    const key = [id1, id2].sort().join('-');
    return graphData.relations.filter(r => {
        const rKey = [r.from, r.to].sort().join('-');
        return rKey === key;
    }).length;
}

/**
 * 计算贝塞尔曲线的控制点，以创建弧度或自环
 * @param {object} p1 - 起点 {x, y, id}
 * @param {object} p2 - 终点 {x, y, id}
 * @param {number} R - 节点半径
 * @param {number} offsetIndex - 用于区分多条边的索引 (0, 1, 2...)
 * @param {boolean} isSelfLoop - 是否是自环
 * @returns {string} SVG Path 'M x1 y1 C cx1 cy1 cx2 cy2 x2 y2' (三次贝塞尔曲线)
 */
function adjustCurve(p1, p2, R, offsetIndex, isSelfLoop) {
    const dx = p2.x - p1.x;
    const dy = p2.y - p1.y;
    const dist = Math.sqrt(dx * dx + dy * dy);
    
    // 自环逻辑 (使用三次贝塞尔曲线)
    if (isSelfLoop) { 
        const loopRadius = 40 + offsetIndex * 15; 
        const angle = -Math.PI / 2; 
        const startAngle = angle - Math.PI/4;
        const endAngle = angle + Math.PI/4;
        
        // 调整起点和终点到圆周上
        const startX = p1.x + R * Math.cos(startAngle);
        const startY = p1.y + R * Math.sin(startAngle);
        const endX = p2.x + R * Math.cos(endAngle);
        const endY = p2.y + R * Math.sin(endAngle);
        
        // 控制点在上方形成弧度
        const c1X = p1.x + loopRadius * Math.cos(angle - 0.1); 
        const c1Y = p1.y + loopRadius * Math.sin(angle - 0.1);
        const c2X = p1.x + loopRadius * Math.cos(angle + 0.1);
        const c2Y = p2.y + loopRadius * Math.sin(angle + 0.1);

        return `M ${startX} ${startY} C ${c1X} ${c1Y}, ${c2X} ${c2Y}, ${endX} ${endY}`;
    }

    // --- 正常关联边逻辑 (强制曲线) ---

    // 调整起点和终点到圆周上
    const ratioStart = R / dist;
    const ratioEnd = R / dist;
    
    const startX = p1.x + dx * ratioStart;
    const startY = p1.y + dy * ratioStart;
    const endX = p2.x - dx * ratioEnd;
    const endY = p2.y - dy * ratioEnd;
    
    // 强制曲线：即使 offsetIndex=0，也应用基础偏移量。
    const baseOffset = 10; // 基础偏移量，确保和顺序边错开
    
    // 总偏移量 = 基础偏移 + 额外的边索引偏移
    const totalOffset = baseOffset + offsetIndex * 20; 
    
    // 旋转 90 度得到法线方向 (用于计算控制点偏移)
    const nx = -dy / dist; 
    const ny = dx / dist;
    
    // 计算中点
    const midX = (p1.x + p2.x) / 2;
    const midY = (p1.y + p2.y) / 2;
    
    // 控制点 C1 和 C2 沿法线方向偏移。为了平滑的单弧度，C1 和 C2 可以接近中点。
    
    // C1: 距离起点 1/3 处，偏移
    const control1X = p1.x + dx * (1/3) + nx * totalOffset;
    const control1Y = p1.y + dy * (1/3) + ny * totalOffset;

    // C2: 距离终点 1/3 处，偏移 (与 C1 对称)
    const control2X = p2.x - dx * (1/3) + nx * totalOffset;
    const control2Y = p2.y - dy * (1/3) + ny * totalOffset;
    
    // 使用三次贝塞尔曲线 (C)
    return `M ${startX} ${startY} C ${control1X} ${control1Y}, ${control2X} ${control2Y}, ${endX} ${endY}`;
}


// --- 渲染和布局 (保持不变) ---

function setDefaultPositions() {
    const W = svg.clientWidth || 800
    const H = svg.clientHeight || 600
    const ids = graphData.sequence.length ? graphData.sequence : graphData.nodes.map(n => n.id)
    const gap = Math.max(120, Math.floor((W - 80) / Math.max(1, ids.length)))
    const y = Math.floor(H / 2)
    ids.forEach((id, i) => { 
        if (!graphData.positions[id]) {
            graphData.positions[id] = { x: 60 + i * gap, y } 
        }
    })
}


function render(onlyUpdate = false) {
    const W = svg.clientWidth || 800
    const H = svg.clientHeight || 600
    const nodeRadius = 30 
    const ids = graphData.sequence.length ? graphData.sequence : graphData.nodes.map(n => n.id)
    const pos = graphData.positions
    const selectedId = graphData.selected ? graphData.selected.id : null

    if (!onlyUpdate) {
        svg.innerHTML = ''
        const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs')
  defs.innerHTML = `
    <marker id="arrowSeq" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#9aa3ad"></path>
    </marker>
    <marker id="arrowRel" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#ffb020"></path>
    </marker>`
        svg.appendChild(defs)
    } else {
        svg.querySelectorAll('.edge-seq, .edge-rel, .label-group').forEach(el => el.remove())
    }

    const edgeLayer = onlyUpdate ? svg : document.createElementNS('http://www.w3.org/2000/svg', 'g')
    if (!onlyUpdate) edgeLayer.setAttribute('id', 'edge-layer')
    
    // Map用于跟踪节点对 (A-B) 之间已经绘制了多少条边
    const edgePairIndex = {}

    // 1. 顺序边 (直线)
    for (let i = 0; i < ids.length - 1; i++) {
        const fromID = ids[i], toID = ids[i + 1]
        const a = pos[fromID], b = pos[toID]
        if (!a || !b) continue
        const [x1, y1, x2, y2] = adjustLineEnds(a.x, a.y, b.x, b.y, nodeRadius)
        // 顺序边使用 line 元素绘制直线，不可选中
        line(edgeLayer, x1, y1, x2, y2, 'edge-seq', `seq-${fromID}-${toID}`) 
    }

    // 2. 关联边 (曲线)
    graphData.relations.forEach(r => {
        const p1 = pos[r.from], p2 = pos[r.to]
        if (!p1 || !p2) return

        p1.id = r.from; p2.id = r.to; // 临时添加ID用于曲线计算
        const relationKey = `${r.from}-${r.to}-${r.desc}` 
        const cls = `edge-rel ${selectedId === relationKey ? 'selected' : ''}` 
        
        const isSelfLoop = r.from === r.to;
        
        // 使用规范化键 (从小到大排序)
        const key = isSelfLoop ? r.from : [r.from, r.to].sort().join('-') 
        
        // 获取当前边的偏移索引
        let currentOffsetIndex = edgePairIndex[key] || 0
        edgePairIndex[key] = currentOffsetIndex + 1
        
        // 计算曲线路径 (现在总是使用三次贝塞尔曲线)
        const dPath = adjustCurve(p1, p2, nodeRadius, currentOffsetIndex, isSelfLoop)
        
        const edgeEl = path(edgeLayer, dPath, cls, relationKey)

        // 绑定关联边的点击监听器
        if (edgeEl) {
            edgeEl.onclick = (e) => {
                e.stopPropagation() 
                selectElement('relation', relationKey, r)
            }
        }
        
        // 标签位置调整：取中点，并垂直偏移
        let midX = (p1.x + p2.x) / 2
        let midY = (p1.y + p2.y) / 2
        
        label(edgeLayer, midX, midY - 15 - currentOffsetIndex * 8, `${r.weight} · ${r.desc}`)
    })
    
    if (!onlyUpdate) svg.appendChild(edgeLayer)


    // --- 绘制节点 ---
    graphData.nodes.forEach(n => {
        const p = pos[n.id]
        if (!p) return

        let nodeGroup = svg.querySelector(`.node-group[data-id="${n.id}"]`)
        const isSelected = selectedId === n.id

        if (!onlyUpdate || !nodeGroup) {
            nodeGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g')
            nodeGroup.setAttribute('data-id', n.id)
            nodeGroup.setAttribute('data-label', n.label)
            
            circle(nodeGroup, p.x, p.y, nodeRadius)
            text(nodeGroup, p.x, p.y, n.label || n.id, 'node-text')
            
            // 绑定事件
            nodeGroup.ondblclick = (e) => editNode(n.id, e)
            nodeGroup.onclick = (e) => { 
                if (!selectedElement) {
                    e.stopPropagation()
                    selectElement('node', n.id, n) 
                }
            }
            
            svg.appendChild(nodeGroup)
        } 
        
        // 更新位置和选中状态
        nodeGroup.setAttribute('transform', `translate(${p.x - nodeRadius}, ${p.y - nodeRadius})`)
        nodeGroup.setAttribute('data-x', p.x)
        nodeGroup.setAttribute('data-y', p.y)

        nodeGroup.setAttribute('class', `node-group ${isSelected ? 'selected' : ''}`)
        
        const textEl = nodeGroup.querySelector('.node-text')
        if (textEl) {
             textEl.textContent = n.label || n.id
        }
    })

    // 取消选中逻辑：点击画布空白处
    if (!onlyUpdate) {
         svg.onclick = (e) => {
             if (e.target === svg) {
                 graphData.selected = null
                 selectionInfo.style.display = 'none'
                 render(true)
                 statusDiv.textContent = '已取消选中。'
             }
         }
    }

    // 侧边栏顺序列表
    seqList.innerHTML = ids.map(id => {
        const node = graphData.nodes.find(n => n.id === id)
        return `<li>**${id}** (${node ? node.label : '未知'})</li>`
    }).join('')
}

// --- 辅助函数：绘制 SVG 元素 (保持不变) ---

function path(parent, d, cls, id = '') {
    const el = document.createElementNS('http://www.w3.org/2000/svg', 'path')
    el.setAttribute('d', d)
    el.setAttribute('class', cls)
    if (id) el.setAttribute('id', id)
    parent.appendChild(el)
    return el 
}
function adjustLineEnds(x1, y1, x2, y2, r) {
    const dx = x2 - x1
    const dy = y2 - y1
    const dist = Math.sqrt(dx * dx + dy * dy)
    if (dist < 2 * r) { 
        return [x1, y1, x2, y2]
    }
    const ratio = r / dist
    const nx1 = x1 + dx * ratio
    const ny1 = y1 + dy * ratio
    const nx2 = x2 - dx * ratio
    const ny2 = y2 - dy * ratio
    return [nx1, ny1, nx2, ny2]
}
function line(parent, x1, y1, x2, y2, cls, id = '') {
    const el = document.createElementNS('http://www.w3.org/2000/svg', 'line')
    el.setAttribute('x1', x1); el.setAttribute('y1', y1)
    el.setAttribute('x2', x2); el.setAttribute('y2', y2)
    el.setAttribute('class', cls)
    if (id) el.setAttribute('id', id)
    parent.appendChild(el)
    return el 
}
function circle(parent, cx, cy, r) {
    const el = document.createElementNS('http://www.w3.org/2000/svg', 'circle')
    el.setAttribute('cx', r); el.setAttribute('cy', r); el.setAttribute('r', r)
    el.setAttribute('class', 'node-circle')
    parent.appendChild(el)
}
function text(parent, x, y, t, cls) {
    const r = 30 
    const el = document.createElementNS('http://www.w3.org/2000/svg', 'text')
    el.setAttribute('x', r); el.setAttribute('y', r) 
    el.textContent = t
    el.setAttribute('class', cls)
    parent.appendChild(el)
}
function label(parent, x, y, t) {
    const group = document.createElementNS('http://www.w3.org/2000/svg', 'g')
    group.setAttribute('class', 'label-group')
    group.setAttribute('transform', `translate(${x}, ${y})`)

    const el = document.createElementNS('http://www.w3.org/2000/svg', 'text')
    el.setAttribute('x', 0); el.setAttribute('y', 0)
    el.setAttribute('text-anchor', 'middle')
    el.textContent = t
    el.setAttribute('class', 'label')

    group.appendChild(el)
    parent.appendChild(group)
}

// --- 交互式编辑 (保持不变) ---
function editNode(nodeId, e) {
    const nodeGroup = e.currentTarget
    const node = graphData.nodes.find(n => n.id === nodeId)
    if (!node) return

    svg.removeEventListener('mousedown', startDrag)

    const input = document.createElement('input')
    input.type = 'text'
    input.value = node.label || node.id
    input.style.position = 'absolute'
    input.style.left = `${e.clientX}px`
    input.style.top = `${e.clientY}px`
    input.style.transform = 'translate(-50%, -50%)' 
    input.style.width = '120px'
    input.style.padding = '5px'
    input.style.fontSize = '14px'
    input.style.zIndex = '100'

    const finishEdit = () => {
        const newLabel = input.value.trim()
        if (newLabel) {
            node.label = newLabel
            nodeGroup.setAttribute('data-label', newLabel)
            nodeGroup.querySelector('.node-text').textContent = newLabel
            render(true) 
            statusDiv.textContent = `节点 ${nodeId} 标签已更新为 ${newLabel}。`
        }
        input.remove()
        svg.addEventListener('mousedown', startDrag)
    }

    input.onblur = finishEdit
    input.onkeydown = (e) => {
        if (e.key === 'Enter') {
            finishEdit()
        }
    }

    document.body.appendChild(input)
    input.focus()
}

// --- 初始化 (保持不变) ---
graphData = { 
    nodes: [{id:'1',label:'abs'},{id:'2',label:'intro'},{id:'3',label:'method'}], 
    sequence:['1','2','3'], 
    relations:[{from:'1',to:'2',weight:0.8,desc:'detail'},{from:'3',to:'1',weight:0.4,desc:'recall'}],
    positions: {},
    selected: null
} 
setDefaultPositions()
render()
