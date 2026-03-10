# 读取传入的命令参数
cmd="$1"

# 如果未提供命令，则提示用法并退出
if [ -z "$cmd" ]; then
  echo "Usage: $0 <cmd>"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker not found. Please install Docker, and ensure you can run 'docker' without sudo." >&2
  exit 127
fi

image="${DEEPSLIDE_TEX_DOCKER_IMAGE:-deepslide:latest}"

workspace_root="$(cd "$(dirname "$0")/../../../../.." && pwd)"

if ! docker image inspect "$image" >/dev/null 2>&1; then
  echo "Error: Docker image '$image' not found." >&2
  echo "Build it from repo root:" >&2
  echo "  docker build -t $image -f container/dockerfile ." >&2
  exit 2
fi

docker run --rm \
  -v "${workspace_root}:/app" \
  -w /app \
  "$image" \
  bash -lc "$cmd"
