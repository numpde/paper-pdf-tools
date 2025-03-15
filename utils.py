# This is from OpenAI's blog (with minor mods)

import inspect

from typing import get_origin, get_args

def function_to_schema(func) -> dict:
    type_map = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
        type(None): "null",
    }

    try:
        signature = inspect.signature(func)
    except ValueError as e:
        raise ValueError(
            f"Failed to get signature for function {func.__name__}: {str(e)}"
        )

    parameters = {}
    for param in signature.parameters.values():
        annotation = param.annotation
        # Handle standard types
        if annotation in type_map:
            json_type = type_map[annotation]
            parameters[param.name] = {"type": json_type}
        # Handle generic types like list[str]
        elif get_origin(annotation) is list:
            args = get_args(annotation)
            if args and args[0] in type_map:
                item_type = type_map[args[0]]
            else:
                item_type = "string"  # default fallback
            parameters[param.name] = {
                "type": "array",
                "items": {"type": item_type}
            }
        else:
            raise KeyError(
                f"Unknown type annotation {annotation} for parameter {param.name}"
            )

    required = [
        param.name
        for param in signature.parameters.values()
        if param.default == inspect._empty
    ]

    return {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": (func.__doc__ or "").strip(),
            "parameters": {
                "type": "object",
                "properties": parameters,
                "required": required,
            },
        },
    }
