import os

from typing import Any
from langchain import PromptTemplate
from langchain.chains import RetrievalQA
from langchain.chat_models import AzureChatOpenAI
from azure.identity import DefaultAzureCredential
from azure.ai.generative import AIClient
from azureml.rag.mlindex import MLIndex
from consts import search_index_folder

def setup_credentials():
    # Azure OpenAI credentials
    import openai
    openai.api_type = os.environ["OPENAI_API_TYPE"]
    openai.api_key = os.environ["OPENAI_API_KEY"]
    openai.api_version = os.environ["OPENAI_API_VERSION"]
    openai.api_base = os.environ["OPENAI_API_BASE"]

    # Azure Cognitive Search credentials
    os.environ["AZURE_COGNITIVE_SEARCH_TARGET"] = os.environ["AZURE_AI_SEARCH_ENDPOINT"]
    os.environ["AZURE_COGNITIVE_SEARCH_KEY"] = os.environ["AZURE_AI_SEARCH_KEY"]

async def chat_completion(messages: list[dict], stream: bool = False, 
    session_state: Any = None, context: dict[str, Any] = {}):  

    question = messages[-1]["content"]
    llm = AzureChatOpenAI(
        deployment_name=os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"],
        model_name=os.environ["AZURE_OPENAI_CHAT_MODEL"],
        temperature=context.get('temperature', 0.7)
    )

    template = """
    System:
    You are an AI assistant helping users with queries related to outdoor outdooor/camping gear and clothing.
    Use the following pieces of context to answer the questions about outdoor/camping gear and clothing as completely, correctly, and concisely as possible.
    If the question is not related to outdoor/camping gear and clothing, just say Sorry, I only can answer question related to outdoor/camping gear and clothing. So how can I help? Don't try to make up an answer.
    If the question is related to outdoor/camping gear and clothing but vague ask for clarifying questions.
    Do not add documentation reference in the response.

    {context}

    ---

    Question: {question}

    Answer:"
    """
    prompt_template = PromptTemplate(
        template=template,
        input_variables=["context", "question"]
    )

    # connects to project defined in the config.json file at the root of the repo
    client = AIClient.from_config(DefaultAzureCredential())
    setup_credentials()

    # convert MLIndex to a langchain retriever
    mlindex = MLIndex(search_index_folder)
    index_langchain_retriever = mlindex.as_langchain_retriever()

    qa = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=index_langchain_retriever,
        return_source_documents=True,
        chain_type_kwargs={
            "prompt": prompt_template,
        }
    )

    response = qa(question)
    return response["result"]