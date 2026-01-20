import re

class Spection(str):
    '''
    人类优雅的说话速度通常被定义为一种既清晰又易于理解，同时带有自然节奏和适当停顿的语速。
    在研究和实践中，优雅的说话速度通常介于 每分钟120到160个单词（Words Per Minute, WPM）之间。
    '''
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