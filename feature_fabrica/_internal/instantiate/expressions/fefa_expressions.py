import ast
import re
from collections import deque
from typing import Any

from hydra._internal.instantiate._instantiate2 import _is_target
from omegaconf import OmegaConf

import feature_fabrica.transform.registry as registry
from feature_fabrica._internal.instantiate.expressions.utils import (
    CLOSE_PARENTHESIS, FUNCTION_PATTERN, OPEN_PARENTHESIS, TOKEN_PATTERN,
    get_precedence, get_transformation, is_function, is_numeric, is_operator,
    is_valid_variable_name)


def tokenize(expression: str) -> list[str]:
    """Tokenize the feature-fabrica expression into numbers, variable names, operators, and functions.

    Supports decimal numbers and function calls with parameters.
    """
    tokens = re.findall(TOKEN_PATTERN, expression)
    return tokens

def _is_valid_expression(expression: str) -> bool:
    """Validate the feature-fabrica expression by checking for correct operator and operand placement, balanced
    parentheses, and valid tokens."""
    parentheses_counter = 0
    # Split the expression based on the operators
    split_expression = tokenize(expression)
    # Remove any empty strings that may result from the split
    split_expression = [token.strip() for token in split_expression if token.strip()]

    if not split_expression:
        return False

    needs_operand = True
    can_be_initital_data = True
    needs_operator = False
    # Iterate through each part of the split expression
    for token in split_expression:
        if not needs_operator and token == OPEN_PARENTHESIS:
            parentheses_counter += 1
            needs_operand = True
            continue
        elif (not needs_operand or can_be_initital_data) and token == CLOSE_PARENTHESIS:
            parentheses_counter -= 1
            needs_operand = False
            needs_operator = True
        elif needs_operand and (is_numeric(token) or is_valid_variable_name(token)):
            needs_operand = False
            needs_operator = True
        elif needs_operator and is_operator(token):
            needs_operator = False
            needs_operand = True
        elif needs_operator and is_function(token):
            needs_operator = True
            needs_operand = False
        else:
            return False
        can_be_initital_data = False
    # Check if all parentheses were closed
    return parentheses_counter == 0 and not needs_operand


def infix_fefa_expression_to_postfix(expression: str) -> list[str]:
    """Convert an infix feature-fabrica expression to postfix feature-fabrica."""
    # Tokenize the expression
    tokens = tokenize(expression)
    output = []
    operator_stack = deque() # type: ignore

    for token in tokens:
        if is_numeric(token) or is_valid_variable_name(token):  # Numeric or variable
            output.append(token)
        elif is_function(token):  # Function call like .log(...)
            output.append(token)
        elif token == OPEN_PARENTHESIS:
            operator_stack.append(token)
        elif token == CLOSE_PARENTHESIS:
            while operator_stack and operator_stack[-1] != OPEN_PARENTHESIS:
                output.append(operator_stack.pop())
            operator_stack.pop()  # Remove '('
        elif is_operator(token):
            while (operator_stack and operator_stack[-1] != OPEN_PARENTHESIS and
                   get_precedence(token) <= get_precedence(operator_stack[-1])):
                output.append(operator_stack.pop())
            operator_stack.append(token)

    # Pop any remaining operators
    while operator_stack:
        output.append(operator_stack.pop())

    return output

def split_function_call(expression: str) -> tuple[str, dict[str, Any]]: # type: ignore[return-value]
    match = re.match(FUNCTION_PATTERN, expression.strip())

    if match:
        function_name = match.group(1)  # Get the function name
        arguments_str = match.group(2).strip()  # Get the arguments as a string

        # Parse arguments using ast
        try:
            # Parse the function call arguments using ast
            parsed_args = ast.parse(f"f({arguments_str})").body[0].value.args # type: ignore[attr-defined]
            parsed_keywords = ast.parse(f"f({arguments_str})").body[0].value.keywords # type: ignore[attr-defined]

            # Check if there are any positional arguments
            if parsed_args and not parsed_keywords:
                raise ValueError("Positional arguments are not allowed.")

            # Convert the AST nodes back into readable Python objects for keyword arguments
            kwargs = {kw.arg: ast.literal_eval(kw.value) for kw in parsed_keywords}

            return function_name, kwargs  # Return only keyword arguments as a dictionary

        except Exception as e:
            raise e
    return ValueError(f"fanction call was not matched in {expression}") # type: ignore[return-value]

def _hydrate_fefa_expression(expression: str, validate_expression: bool = False) -> Any:
    if validate_expression and not _is_valid_expression(expression):
        raise ValueError("Invalid expression provided.")

    postfix_tokens = infix_fefa_expression_to_postfix(expression)
    ast = build_ast(postfix_tokens)

    return OmegaConf.create(ast)


def build_ast(postfix_tokens) -> dict:
    """Build an AST (abstract syntax tree) from postfix tokens."""
    stack = []
    count_individual_steps = 0

    for token in postfix_tokens:
        if is_numeric(token) or is_valid_variable_name(token):
            stack.append(token)
        elif is_function(token):
            count_individual_steps += _process_function_token(token, stack, count_individual_steps)
        elif is_operator(token):
            _process_operator_token(token, stack)
        else:
            raise ValueError(f"Unknown token: {token}")

    if len(stack) != 1:
        raise ValueError(f"Unexpected result after processing: {stack}")

    return stack[0]


def _process_function_token(token: str, stack: list, count_individual_steps: int) -> int:
    """Process a function token and update the AST stack."""
    fn_name, kwargs = split_function_call(token)
    fn_class = registry.TransformationRegistry.get_transformation_class_by_name(fn_name)

    _hydrated_fn_class = {
        "_target_": fn_class,
        **kwargs,
    }

    a = stack.pop() if stack else None
    if a is None:
        stack.append(_hydrated_fn_class)
        return 0
    elif isinstance(a, dict):
        if _is_target(a):
            stack.append({
                f"fn_{count_individual_steps}": a,
                f"fn_{count_individual_steps + 1}": _hydrated_fn_class,
            })
            return 2
        else:
            a[f"fn_{count_individual_steps}"] = _hydrated_fn_class
            stack.append(a)
            return 1
    else:
        if is_numeric(a) or not is_valid_variable_name(a):
            raise ValueError("Invalid operand for function.")

        importer_fn_class = registry.TransformationRegistry.get_transformation_class_by_name("import")
        _hydrated_importer_fn_class = {
            "_target_": importer_fn_class,
            "feature": a
        }
        stack.append({
            f"fn_{count_individual_steps}": _hydrated_importer_fn_class,
            f"fn_{count_individual_steps + 1}": _hydrated_fn_class,
        })
        return 2

def _pop_operand(stack: list) -> Any:
    """Pop an operand from the stack and ensure it's a valid type."""
    operand = stack.pop()
    if not isinstance(operand, dict) and is_numeric(operand):
        return float(operand)

    return operand

def _process_operator_token(token: str, stack: list):
    """Process an operator token and update the AST stack."""
    if len(stack) < 2:
        raise ValueError(f"Insufficient operands for operator '{token}'")

    b = _pop_operand(stack)
    a = _pop_operand(stack)
    cur_operand = get_transformation(token)

    if isinstance(a, dict):
        if not isinstance(b, dict):
            if _is_target(a) and cur_operand in a['_target_']:
                a['iterable'].append(b)
                stack.append(a)
            else:
                stack.append({
                    '_target_': f'feature_fabrica.transform.{cur_operand}',
                    'iterable': [
                        {
                            '_target_': 'feature_fabrica.models.PromiseValue',
                            'transformation': a
                        },
                        b
                    ]
                })
        else:
            # Both operands are dictionaries
            stack.append({
                '_target_': f'feature_fabrica.transform.{cur_operand}',
                'iterable': [
                    {"_target_": 'feature_fabrica.models.PromiseValue', 'transformation': a},
                    {"_target_": 'feature_fabrica.models.PromiseValue', 'transformation': b}
                ]
            })
    else:
        stack.append({
            '_target_': f'feature_fabrica.transform.{cur_operand}',
            'iterable': [a, b]
        })
