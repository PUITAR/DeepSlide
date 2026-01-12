#! /bin/bash    

set -x

rm -rf index-tts/

wget https://github.com/index-tts/index-tts/archive/refs/heads/main.zip -O index-tts.zip
# wget https://gh.llkk.cc/https://github.com/index-tts/index-tts.git -O index-tts.zip

unzip index-tts.zip -d index-tts/

if [ ! -d "index-tts/index-tts-main" ]; then
    echo "index-tts-main not found"
    exit 1
fi

rm index-tts.zip

# fix some env problem for the code
cat index-tts-helper/webui.py >> index-tts/index-tts-main/webui.py
cat index-tts-helper/infer_v2.py >> index-tts/index-tts-main/indextts/infer_v2.py
cat index-tts-helper/run.sh >> index-tts/index-tts-main/run.sh