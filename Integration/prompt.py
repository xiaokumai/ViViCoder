#  Package your code in ```python ... ```.
 
INTEGRATION_PROMPT = '''
You are a software development expert responsible for taking the user’s original requirements, integrating the already-completed modules, and producing a final, deliverable code system. Your goals are:
 Integrate the "code" fields from each module, ensuring they work together smoothly based on their collaborative relationships.
 Using the interface function signatures specified in the user’s requirements, generate complete, deliverable code so the user can use the generated code via these function signatures.
 Package your code in ```python ... ```.

'''


INTEGRATION_PROMPT = '''
You are a programmer responsible for integrating modules and generating final deliverable code in **python**.
'''


INTEGRATION_INPUT = '''
## Original Requirement:
{raw}

## Modules Design:
{modules}

--------
**Important Instructions:**
- Do not add any explanation.
- The generated **python** code must be inside a triple backtick (```) code block.
'''


INTEGRATION_INPUT = '''
Original Requirement:
{raw}
Modules Design:
{modules}
'''

requirement = '''
Write a Python function to calculate and return the sum of all numbers in a given list. Your code should satisfy these tests:

assert sum_numbers([1, 2, 3, 4, 5]) == 15
'''

modules = '''
"modules": [
    {
    "id": "SumCalculator",
    "inputs": [
        {
        "name": "input_list",
        "data_type": "List[int]",
        "note": null
        }
    ],
    "outputs": [
        {
        "name": "sum",
        "data_type": "int",
        "note": null
        }
    ],
    "summary": [
        "Calculate the sum of numbers in a list"
    ],
    "function_signature": "def sum_numbers(input_list: List[int]) -> int",
    "dependencies": [],
    "code": "```python\nfrom typing import List\n\ndef sum_numbers(input_list: List[int]) -> int:\n    # Calculate the sum of numbers in the input_list using the sum() function\n    total_sum = sum(input_list)\n    return total_sum\n```"
    }
]
'''

output = '''
from typing import List

def sum_numbers(input_list: List[int]) -> int:
    """
    Calculate and return the sum of all numbers in a given list.

    Args:
        input_list: A list of integers.

    Returns:
        The sum of all integers in the list.
    """
    return sum(input_list)
'''

example = [
    {
        "raw": requirement,
        "modules": modules,
        "output": output
    }
]