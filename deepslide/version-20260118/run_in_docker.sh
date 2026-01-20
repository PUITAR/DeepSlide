# 读取传入的命令参数
cmd="$1"

# 如果未提供命令，则提示用法并退出
if [ -z "$cmd" ]; then
  echo "Usage: $0 <cmd>"
  exit 1
fi

sudo docker exec deepslide-container bash -lc \
    "python3 -m venv /opt/venv &&\
     source /opt/venv/bin/activate &&\
     $cmd"

