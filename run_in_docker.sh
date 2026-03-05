# 读取传入的命令参数
cmd="$1"

# 如果未提供命令，则提示用法并退出
if [ -z "$cmd" ]; then
  echo "Usage: $0 <cmd>"
  exit 1
fi

# DEBUG: Log the command
echo "=== ROOT RUN_IN_DOCKER.SH DEBUG (NO FIX) ===" >&2
echo "Original command: $cmd" >&2
echo "Using command as-is (files are at /app/projects/... in container)" >&2
echo "=== END DEBUG ===" >&2

sudo docker exec -i deepslide-container bash -lc     "python3 -m venv /opt/venv &&     source /opt/venv/bin/activate &&     $cmd"
