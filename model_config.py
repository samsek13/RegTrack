"""
模型配置管理模块
用于管理不同模型的特定参数和兼容性设置
"""

from typing import Dict, Any, Optional


class ModelCompatibilityManager:
    """
    模型兼容性管理器
    用于处理不同模型对参数的支持情况
    """

    def __init__(self):
        # 定义不支持特定参数的模型配置
        self.model_compatibility = {
            "deepseek-ai/DeepSeek-V3": {
                "unsupported_params": ["enable_thinking"],
                "param_defaults": {}
            },
            "Qwen/Qwen2.5-72B-Instruct": {
                "unsupported_params": ["enable_thinking"],
                "param_defaults": {}
            },
            "Qwen/Qwen3-VL-32B-Thinking": {
                "unsupported_params": ["enable_thinking"],
                "param_defaults": {}
            },
            # 可以在这里添加更多模型配置
        }

    def get_model_extra_body(self, model_name: str, default_params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        获取适合指定模型的 extra_body 参数

        Args:
            model_name: 模型名称
            default_params: 默认参数字典

        Returns:
            适合该模型的参数字典，如果不适用则返回 None
        """
        if default_params is None:
            default_params = {}

        # 检查模型是否存在于兼容性配置中
        if model_name in self.model_compatibility:
            model_config = self.model_compatibility[model_name]
            unsupported_params = model_config.get("unsupported_params", [])

            # 过滤掉不支持的参数
            filtered_params = {
                key: value
                for key, value in default_params.items()
                if key not in unsupported_params
            }
        else:
            # 如果模型不在配置中，检查是否包含某些不支持该参数的关键字
            filtered_params = self._filter_by_keywords(model_name, default_params)

        # 如果过滤后的参数为空，返回 None
        return filtered_params if filtered_params else None

    def _filter_by_keywords(self, model_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        根据关键字过滤参数
        """
        # 可能有一些通用规则来判断模型是否支持某些参数
        # 例如，包含特定关键词的模型可能不支持某些参数
        unsupported_keywords = ["thinking"]  # 如果模型名包含'thinking'可能不支持enable_thinking参数

        for keyword in unsupported_keywords:
            if keyword.lower() in model_name.lower():
                # 如果模型名称包含不支持的关键词，过滤掉相应参数
                return {
                    key: value
                    for key, value in params.items()
                    if key != "enable_thinking"  # 特别过滤掉 enable_thinking 参数
                }

        # 如果没有匹配的关键词，返回原始参数
        return params

    def is_param_supported(self, model_name: str, param_name: str) -> bool:
        """
        检查指定模型是否支持特定参数

        Args:
            model_name: 模型名称
            param_name: 参数名称

        Returns:
            如果支持返回 True，否则返回 False
        """
        if model_name in self.model_compatibility:
            model_config = self.model_compatibility[model_name]
            unsupported_params = model_config.get("unsupported_params", [])
            return param_name not in unsupported_params

        # 如果模型未在配置中定义，可以根据关键字检查
        return self._is_param_supported_by_keywords(model_name, param_name)

    def _is_param_supported_by_keywords(self, model_name: str, param_name: str) -> bool:
        """
        根据关键字检查参数是否受支持
        """
        # 如果模型名包含 'thinking' 关键字，可能不支持 enable_thinking 参数
        if "thinking" in model_name.lower() and param_name == "enable_thinking":
            return False

        return True  # 默认支持


# 创建全局实例
model_compat_manager = ModelCompatibilityManager()


def get_model_extra_body_for_thinking(model_name: str, enable_thinking_value: bool = False) -> Optional[Dict[str, Any]]:
    """
    专门用于获取适合思考参数的 extra_body 配置

    Args:
        model_name: 模型名称
        enable_thinking_value: enable_thinking 参数的值

    Returns:
        适合该模型的参数字典，如果不适用则返回 None
    """
    default_params = {"enable_thinking": enable_thinking_value}
    return model_compat_manager.get_model_extra_body(model_name, default_params)