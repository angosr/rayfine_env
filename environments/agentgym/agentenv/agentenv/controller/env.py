from abc import ABCMeta, abstractmethod

from .types import ActionFormat, ConversationMessage, StepOutput
from typing import Dict, Tuple


class BaseEnvClient(metaclass=ABCMeta):
    _conversation_start: Dict[ActionFormat, Tuple[ConversationMessage]]

    def __init__(self, action_format: ActionFormat = "react") -> None:
        self.action_format = ActionFormat(action_format)

    @abstractmethod
    def __len__(self) -> int:
        """
        Return the total size of the environment.
        """

    @abstractmethod
    def observe(self) -> str:
        """
        Parse env server response and give a text message to prompt the LLM.
        """

    @abstractmethod
    def step(self, action) -> StepOutput:
        """
        Parse model output from the action and call the env server.
        """

    @abstractmethod
    def reset(self, idx: int) -> None:
        """
        Reset the environment.
        """
