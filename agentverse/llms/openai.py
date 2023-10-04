import logging
import json
import ast
import os
from typing import Dict, List, Optional, Union
from tenacity import retry, stop_after_attempt, wait_exponential

from pydantic import BaseModel, Field

from agentverse.llms.base import LLMResult
from agentverse.logging import logger
from agentverse.message import Message

from . import llm_registry
from .base import BaseChatModel, BaseCompletionModel, BaseModelArgs
from .utils.jsonrepair import JsonRepair

try:
    import openai
    from openai.error import OpenAIError
except ImportError:
    is_openai_available = False
    logging.warning("openai package is not installed")
else:
    openai.api_key = os.environ.get("OPENAI_API_KEY")
    openai.proxy = os.environ.get("http_proxy")
    if openai.proxy is None:
        openai.proxy = os.environ.get("HTTP_PROXY")
    if openai.api_key is None:
        logging.warning(
            "OpenAI API key is not set. Please set the environment variable OPENAI_API_KEY"
        )
        is_openai_available = False
    else:
        is_openai_available = True


class OpenAIChatArgs(BaseModelArgs):
    model: str = Field(default="gpt-3.5-turbo")
    max_tokens: int = Field(default=2048)
    temperature: float = Field(default=1.0)
    top_p: int = Field(default=1)
    n: int = Field(default=1)
    stop: Optional[Union[str, List]] = Field(default=None)
    presence_penalty: int = Field(default=0)
    frequency_penalty: int = Field(default=0)


# class OpenAICompletionArgs(OpenAIChatArgs):
#     model: str = Field(default="text-davinci-003")
#     suffix: str = Field(default="")
#     best_of: int = Field(default=1)


# @llm_registry.register("text-davinci-003")
# class OpenAICompletion(BaseCompletionModel):
#     args: OpenAICompletionArgs = Field(default_factory=OpenAICompletionArgs)

#     def __init__(self, max_retry: int = 3, **kwargs):
#         args = OpenAICompletionArgs()
#         args = args.dict()
#         for k, v in args.items():
#             args[k] = kwargs.pop(k, v)
#         if len(kwargs) > 0:
#             logging.warning(f"Unused arguments: {kwargs}")
#         super().__init__(args=args, max_retry=max_retry)

#     def generate_response(self, prompt: str) -> LLMResult:
#         response = openai.Completion.create(prompt=prompt, **self.args.dict())
#         return LLMResult(
#             content=response["choices"][0]["text"],
#             send_tokens=response["usage"]["prompt_tokens"],
#             recv_tokens=response["usage"]["completion_tokens"],
#             total_tokens=response["usage"]["total_tokens"],
#         )

#     async def agenerate_response(self, prompt: str) -> LLMResult:
#         response = await openai.Completion.acreate(prompt=prompt, **self.args.dict())
#         return LLMResult(
#             content=response["choices"][0]["text"],
#             send_tokens=response["usage"]["prompt_tokens"],
#             recv_tokens=response["usage"]["completion_tokens"],
#             total_tokens=response["usage"]["total_tokens"],
#         )


@llm_registry.register("gpt-3.5-turbo")
@llm_registry.register("gpt-4")
class OpenAIChat(BaseChatModel):
    args: OpenAIChatArgs = Field(default_factory=OpenAIChatArgs)

    def __init__(self, max_retry: int = 3, **kwargs):
        args = OpenAIChatArgs()
        args = args.dict()

        for k, v in args.items():
            args[k] = kwargs.pop(k, v)
        if len(kwargs) > 0:
            logging.warning(f"Unused arguments: {kwargs}")
        super().__init__(args=args, max_retry=max_retry)

    # def _construct_messages(self, history: List[Message]):
    #     return history + [{"role": "user", "content": query}]

    @retry(
        stop=stop_after_attempt(20),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True,
    )
    def generate_response(
        self,
        prepend_prompt: str = "",
        history: List[dict] = [],
        append_prompt: str = "",
        functions: List[dict] = [],
    ) -> LLMResult:
        # logger.debug(prepend_prompt)
        # logger.debug(history)
        # logger.debug(append_prompt)
        messages = self.construct_messages(prepend_prompt, history, append_prompt)
        logger.log_prompt(messages)

        try:
            # Execute function call
            if functions != []:
                response = openai.ChatCompletion.create(
                    messages=messages,
                    functions=functions,
                    # function_call="auto",
                    # function_call={"name": "run_code"},
                    # stream=True,
                    **self.args.dict(),
                )
                if response["choices"][0]["message"].get("function_call") is not None:
                    return LLMResult(
                        content=response["choices"][0]["message"].get("content", ""),
                        function_name=response["choices"][0]["message"][
                            "function_call"
                        ]["name"],
                        function_arguments=ast.literal_eval(
                            response["choices"][0]["message"]["function_call"][
                                "arguments"
                            ]
                        ),
                        send_tokens=response["usage"]["prompt_tokens"],
                        recv_tokens=response["usage"]["completion_tokens"],
                        total_tokens=response["usage"]["total_tokens"],
                    )
                else:
                    return LLMResult(
                        content=response["choices"][0]["message"]["content"],
                        send_tokens=response["usage"]["prompt_tokens"],
                        recv_tokens=response["usage"]["completion_tokens"],
                        total_tokens=response["usage"]["total_tokens"],
                    )

            else:
                response = openai.ChatCompletion.create(
                    messages=messages,
                    **self.args.dict(),
                )
                return LLMResult(
                    content=response["choices"][0]["message"]["content"],
                    send_tokens=response["usage"]["prompt_tokens"],
                    recv_tokens=response["usage"]["completion_tokens"],
                    total_tokens=response["usage"]["total_tokens"],
                )
        except (OpenAIError, KeyboardInterrupt, json.decoder.JSONDecodeError) as error:
            raise

    @retry(
        stop=stop_after_attempt(20),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True,
    )
    async def agenerate_response(
        self,
        prepend_prompt: str = "",
        history: List[dict] = [],
        append_prompt: str = "",
        functions: List[dict] = [],
    ) -> LLMResult:
        # logger.debug(prepend_prompt)
        # logger.debug(history)
        # logger.debug(append_prompt)
        messages = self.construct_messages(prepend_prompt, history, append_prompt)
        logger.log_prompt(messages)

        try:
            # Execute function call
            if functions != []:
                response = await openai.ChatCompletion.acreate(
                    messages=messages,
                    functions=functions,
                    # function_call="auto",
                    # function_call={"name": "run_code"},
                    # stream=True,
                    **self.args.dict(),
                )
                if response["choices"][0]["message"].get("function_call") is not None:
                    function_name = response["choices"][0]["message"]["function_call"][
                        "name"
                    ]
                    valid_function = False
                    if function_name.startswith("function."):
                        function_name = function_name.replace("function.", "")
                    elif function_name.startswith("functions."):
                        function_name = function_name.replace("functions.", "")
                    for function in functions:
                        if function["name"] == function_name:
                            valid_function = True
                            break
                    if not valid_function:
                        logger.warn(
                            f"The returned function name {function_name} is not in the list of valid functions. Retrying..."
                        )
                        raise ValueError(
                            f"The returned function name {function_name} is not in the list of valid functions."
                        )
                    try:
                        arguments = ast.literal_eval(
                            response["choices"][0]["message"]["function_call"][
                                "arguments"
                            ]
                        )
                    except:
                        try:
                            arguments = ast.literal_eval(
                                JsonRepair(
                                    response["choices"][0]["message"]["function_call"][
                                        "arguments"
                                    ]
                                ).repair()
                            )
                        except:
                            logger.warn(
                                "The returned argument in function call is not valid json. Retrying..."
                            )
                            raise ValueError(
                                "The returned argument in function call is not valid json."
                            )
                    return LLMResult(
                        function_name=function_name,
                        function_arguments=arguments,
                        send_tokens=response["usage"]["prompt_tokens"],
                        recv_tokens=response["usage"]["completion_tokens"],
                        total_tokens=response["usage"]["total_tokens"],
                    )

                else:
                    return LLMResult(
                        content=response["choices"][0]["message"]["content"],
                        send_tokens=response["usage"]["prompt_tokens"],
                        recv_tokens=response["usage"]["completion_tokens"],
                        total_tokens=response["usage"]["total_tokens"],
                    )

            else:
                response = await openai.ChatCompletion.acreate(
                    messages=messages,
                    **self.args.dict(),
                )
                return LLMResult(
                    content=response["choices"][0]["message"]["content"],
                    send_tokens=response["usage"]["prompt_tokens"],
                    recv_tokens=response["usage"]["completion_tokens"],
                    total_tokens=response["usage"]["total_tokens"],
                )
        except (OpenAIError, KeyboardInterrupt, json.decoder.JSONDecodeError) as error:
            raise

    def construct_messages(
        self, prepend_prompt: str, history: List[dict], append_prompt: str
    ):
        messages = []
        if prepend_prompt != "":
            messages.append({"role": "system", "content": prepend_prompt})
        if len(history) > 0:
            messages += history
        if append_prompt != "":
            messages.append({"role": "user", "content": append_prompt})
        return messages
