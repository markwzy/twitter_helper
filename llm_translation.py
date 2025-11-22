from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from config import Config


class LLMTranslation:

    def __init__(self):
        config = Config()
        self.llm = ChatOpenAI(
            model_name=config.get_llm_model_name,
            openai_api_base=config.get_llm_api_base,
            openai_api_key=config.get_llm_api_key
        )

    def translate(self, text):
        template = """
请将以下英文描述完全直译成中文，要求：

1.保持原文所有细节，不做任何增删；
2.所有身体部位词汇（如 breasts, nipples, buttocks, pubic hair）必须直译，不得美化或隐喻；
3.情绪或姿态词（如 seductively, teasing, playful）保留最直白的中文表达；
4.用清晰、无修饰、无修辞的中文表达，适合用于 AI 图像生成提示词；
5.输出为一段连贯描述，不加感叹号、不加比喻、不加文学化表达。

{text}
        """
        prompt = PromptTemplate.from_template(template)
        context = prompt.format(text=text)
        res = self.llm.invoke(context)
        if hasattr(res, 'content'):
            return res.content
        else:
            return str(res)


if __name__ == '__main__':
    llm = LLMTranslation()
    text = "A woman stands in a room."
    llm.translate(text)
