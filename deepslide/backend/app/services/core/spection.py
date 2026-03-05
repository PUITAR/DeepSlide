import re

class Spection(str):
    WPM = 140

    def __new__(cls, content: str):
        return super().__new__(cls, (content or ""))

    def word_len(self) -> int:
        return len(self.split())

    def speech_time(self) -> float:
        return self.word_len() / self.WPM

def split_speech(speech: str) -> list[str]:
    return re.split(r'\n<next>\n', speech)

def merge_speeches(speeches: list[str]) -> str:
    return "\n<next>\n".join(speeches)
