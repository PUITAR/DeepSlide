# bash/bin

set -x

# 清空tmp_uploads目录，里面有一堆上传的文件
rm -rf tmp_uploads/*
# rm -rf deepslide/tmp_uploads/*

VERSION="version-beamer-20251230"

# 清空会话历史数据
rm -rf deepslide/${VERSION}/context_files/*