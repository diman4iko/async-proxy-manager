from abc import abstractmethod, ABC
from typing import Optional, Any, Dict


class AbstractQueue(ABC):

    @abstractmethod
    async def add(self, item) -> None:
        pass

    @abstractmethod
    async def get(
            self,
            task_key: str = "default",
            last_used: float = 1.0,
            other_conditions: Optional[Dict[str, str]] | None = None,
    ) -> Any:
        pass

    @abstractmethod
    def release(self, item, task_key: str | None):
        pass
