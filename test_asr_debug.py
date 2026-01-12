import os
import sys
import traceback
from modelscope.pipelines import pipeline
from modelscope.utils.constant import Tasks

# Configuration
AUDIO_PATH = "/home/ym/DeepSlide/deepslide/tmp_uploads/voice_f3079d.wav"
MODEL_ID = 'damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch'
CACHE_DIR = "/home/ym/DeepSlide/local_llm_server/models"

def test_asr():
    print(f"Testing ASR on file: {AUDIO_PATH}")
    
    if not os.path.exists(AUDIO_PATH):
        print("Error: Audio file not found!")
        return

    file_size = os.path.getsize(AUDIO_PATH)
    print(f"Audio file size: {file_size} bytes")

    # Check model path
    model_path = os.path.join(CACHE_DIR, MODEL_ID)
    if os.path.exists(model_path):
        print(f"Using local model at: {model_path}")
        model_spec = model_path
    else:
        print(f"Local model not found at {model_path}, using ID: {MODEL_ID}")
        model_spec = MODEL_ID

    try:
        print("Loading pipeline...")
        inference_pipeline = pipeline(
            task=Tasks.auto_speech_recognition, 
            model=model_spec,
            device='cpu' # Force CPU to avoid CUDA issues if any
        )
        print("Pipeline loaded.")

        print("Running inference...")
        rec_result = inference_pipeline(audio_input=AUDIO_PATH)
        print(f"Raw Result: {rec_result}")
        print(f"Result Type: {type(rec_result)}")

        if isinstance(rec_result, dict):
            print(f"Text: {rec_result.get('text', '')}")
        elif isinstance(rec_result, list):
            print(f"Text (from list): {rec_result[0] if rec_result else 'empty'}")
        
    except Exception as e:
        print(f"Error occurred: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    test_asr()
