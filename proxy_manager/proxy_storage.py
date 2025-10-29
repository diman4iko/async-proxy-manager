from typing import Dict

from proxy_manager.types import ProxyData

MAX_ERROR_COUNT = 50


class ProxyStorage:
    def __init__(self):
        self.proxy_dict: Dict[ProxyData, dict] = {}

    def add_proxy_str(self, proxy: str, other_conditions: Dict[str, str] = None):
        """
        :param other_conditions: остальные условия не обязательно
        :param proxy: строка в стандартном формате
        :return: обьект прокси дата
        """
        parts = proxy.split(":")
        if len(parts) != 4:
            raise ValueError("Proxy str format ip:port:user:password")
        if len(parts[0].split(".")) != 4:
            raise ValueError("Proxy str format ip:port:user:password")
        if other_conditions is None:
            other_conditions = {}
        proxy_object = ProxyData(parts[0], int(parts[1]), parts[2], parts[3], other_conditions)

        self.proxy_dict[proxy_object] = {}
        self.proxy_dict[proxy_object]["error_sequence"] = 0
        return proxy_object

    def get_proxy_by_str(self, proxy_str: str):
        for proxy in self.proxy_dict.keys():
            if f"{proxy.ip}:{str(proxy.port)}:{proxy.username}:{proxy.password}" == proxy_str:
                return proxy
        raise ValueError("Proxy doesnt match in record")

    def update_proxy_status(self, proxy: ProxyData):
        self.proxy_dict[proxy]["error_sequence"] = 0

    def report_status(self, proxy: ProxyData, request_status: bool, task_key: str):
        """
        :param task_key: таска где юзался прокси для статы
        :param proxy:
        :param request_status: true - work false - not work
        :return:
        """
        try:
            if request_status:
                self.proxy_dict[proxy]["error_sequence"] = 0
                self.proxy_dict[proxy][f"{task_key}_success_request"] += 1
            else:
                self.proxy_dict[proxy]["error_sequence"] += 1
                self.proxy_dict[proxy][f"{task_key}_error_request"] += 1
        except KeyError:
            self.proxy_dict[proxy][f"{task_key}_success_request"] = 0
            self.proxy_dict[proxy][f"{task_key}_error_request"] = 0

    def get_proxy_error_count(self, proxy: ProxyData) -> int:
        try:
            return self.proxy_dict[proxy]["error_sequence"]
        except KeyError:
            self.proxy_dict[proxy]["error_sequence"] = 0
            return 0

    def get_all_proxy_with_statuses(self) -> dict:
        return self.proxy_dict

    def proxy_is_valid(self, proxy: ProxyData) -> bool:
        """
        :param proxy:
        :return: True if proxy valid false if not
        """
        if proxy not in self.proxy_dict:
            return False

        if self.proxy_dict[proxy]["error_sequence"] < MAX_ERROR_COUNT:
            return True
        else:
            return False
