# enable type annotation syntax on Python versions earlier than 3.9
from __future__ import annotations

# set environment variables before importing any other code (in particular the openai module)
from dotenv import load_dotenv
load_dotenv()

import os
import asyncio
import platform
import json
import pathlib

from azure.ai.generative import AIClient
from azure.identity import DefaultAzureCredential

# build the index using the product catalog docs from data/3-product-info
def build_cogsearch_index(index_name, path_to_data):
    from azure.ai.generative.operations._index_data_source import LocalSource, ACSOutputConfig
    from azure.ai.generative.functions.build_mlindex import build_mlindex

    # Set up environment variables for cog search SDK
    os.environ["AZURE_COGNITIVE_SEARCH_TARGET"] = os.environ["AZURE_AI_SEARCH_ENDPOINT"]
    os.environ["AZURE_COGNITIVE_SEARCH_KEY"] = os.environ["AZURE_AI_SEARCH_KEY"]
    
    client = AIClient.from_config(DefaultAzureCredential())
    
    # Use the same index name when registering the index in AI Studio
    index = build_mlindex(
        output_index_name=index_name,
        vector_store="azure_cognitive_search",
        embeddings_model = f"azure_open_ai://deployment/{os.environ['AZURE_OPENAI_EMBEDDING_DEPLOYMENT']}/model/{os.environ['AZURE_OPENAI_EMBEDDING_MODEL']}",
        data_source_url="https://product_info.com",
        index_input_config=LocalSource(input_data=path_to_data),
        acs_config=ACSOutputConfig(
            acs_index_name=index_name,
        ),
    )

    # register the index so that it shows up in the project
    cloud_index = client.mlindexes.create_or_update(index)
    
    print(f"Created index '{cloud_index.name}'")
    print(f"Local Path: {index.path}")
    print(f"Cloud Path: {cloud_index.path}")
    
# TEMP: wrapper around chat completion function until chat_completion protocol is supported
def copilot_qna(question, chat_completion_fn):
    # Call the async chat function with a single question and print the response    

    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    result = asyncio.run(
        chat_completion_fn([{"role": "user", "content": question}])
    )
    response = result['choices'][0]
    return {
        "question": question,
        "answer": response["message"]["content"],
        "context": response["context"]
    }
 
 # Define helper methods
def load_jsonl(path):
    with open(path, "r") as f:
        return [json.loads(line) for line in f.readlines()]

def run_evaluation(chat_completion_fn, name, dataset_path):
    from azure.ai.generative.evaluate import evaluate

    # Evaluate the default vs the improved system prompt to see if the improved prompt
    # performs consistently better across a larger set of inputs
    path = pathlib.Path.cwd() / dataset_path
    dataset = load_jsonl(path)
    
    # temp: generate a single-turn qna wrapper over the chat completion function
    qna_fn = lambda question: copilot_qna(question, chat_completion_fn)
    
    client = AIClient.from_config(DefaultAzureCredential())
    result = evaluate(
        evaluation_name=name,
        asset=qna_fn,
        data=dataset,
        task_type="qa",
        prediction_data="answer",
        truth_data="truth",
        metrics_config={
            "openai_params": {
                "api_version": "2023-05-15",
                "api_base": os.getenv("OPENAI_API_BASE"),
                "api_type": "azure",
                "api_key": os.getenv("OPENAI_API_KEY"),
                "deployment_id": os.getenv("AZURE_OPENAI_EVALUATION_DEPLOYMENT")
            },
            "questions": "question",
            "contexts": "context",
        },
        tracking_uri=client.tracking_uri,
    )
    return result

def deploy_flow(deployment_name):
    client = AIClient.from_config(DefaultAzureCredential())
    deployment = Deployment(
        name=deployment_name,
        model=LocalModel(
            path="./src",
            conda_file="conda.yaml",
            loader_module="load",
        ),
    )
    client.deployments.create_or_update(deployment)

# Run a single chat message through one of the co-pilot implementations
if __name__ == "__main__":
    # configure asyncio
    import asyncio
    import platform

    # workaround for a bug on windows
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", help="The question to ask the copilot", type=str)
    parser.add_argument("--implementation", help="The implementation to use", default="aisdk", type=str)
    parser.add_argument("--deploy", help="Deploy copilot", action='store_true')
    parser.add_argument("--evaluate", help="Evaluate copilot", action='store_true')
    parser.add_argument("--dataset-path", help="Test dataset to use with evaluation", default="src/tests/evaluation_dataset.jsonl", action='store_true')
    parser.add_argument("--deployment-name", help="deployment name to use when deploying the flow", type=str)
    parser.add_argument("--build-index", help="Build an index with the default docs", action='store_true')
    args = parser.parse_args()
    
    if args.implementation:
        if args.implementation == "promptflow":
            from copilot_promptflow.chat import chat_completion
        elif args.implementation == "semantickernel":
            from copilot_semantickernel.chat import chat_completion
        elif args.implementation == "langchain":
            from copilot_langchain.chat import chat_completion
        elif args.implementation == "aisdk":
            from copilot_aisdk.chat import chat_completion

    if args.build_index:
        build_cogsearch_index("contoso_product_index", "data/3-product_info")
    elif args.evaluate:
        results = run_evaluation(chat_completion, name=f"test-{args.implementation}-copilot", dataset_path=args.dataset_path)
        print(results)
    elif args.deploy:
        # TODO - how to handle changing the implementation?
        client = AIClient.from_config(DefaultAzureCredential())
        deployment_name = args.deployment_name if args.deployment_name else f"{client.project_name}-copilot"
        deploy_flow(deployment_name)
    else:
        question = "which tent is the most waterproof?"
        if args.question:
            question = args.question
            
        # Call the async chat function with a single question and print the response
        result = asyncio.run(
            chat_completion([{"role": "user", "content": question}])
        )
        print(result)
    