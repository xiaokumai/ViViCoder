REQUIREMENT_INPUT = '''
```python
{problem}
```

Write requirements for the problem. Package your response in ```plaintext ... ```.
'''


CODE_GEN_SYSTEM = '''
You are a coding assistant. Your task is to generate Python code based on the given problem description. The generated code should be meet the specified requirements.
'''

CODE_GEN_INPUT = '''
## Problem
{problem}

## Requirements
{requirements}

Write a python code for the problem. DO NOT generate any test cases or descriptions. Package your code in ```python ... ```.
'''

TEST_GENERATION = '''
You are a software test engineer tasked with generating edge test cases for a given problem. See the refined requirement for the problem and ensure the generated test cases should cover it.

## Problem
{prompt}

## Requirements
{requirements}

**Important Instructions:**
- The generated test cases **must strictly follow** the data types, value ranges, and constraints described in **## Problem**.
- You must output **only** valid JSON, nothing else — no explanations, no markdown formatting.
- Package the remaining test cases inside a triple backtick (```) code block.
- The final test cases must be valid JSON and strictly follow the structure and style of test cases as shown below:
{sample_io}
'''




DUBUG_SYSTEM = '''
You are a programmer who has received a solution of a problem written in **python** that fails to pass certain test cases. Your task is to modify the code in such a way so that it can pass all the test cases. Do not generate same code.
'''



DUBUG_INPUT = '''
## Problem
{prompt}

## Buggy Code
```python
{code}
```

## Failing Test Cases
{test_log}

**Expected Output:**

Your response must be structured as follows:

### Modified Code
```python
# Your corrected code, with comments explaining each correction.
```

--------
**Important Instructions:**
- Strictly follow the instructions.
- Do not add testing code for example assert statement in your code.
- Do not be overconfident that the generated code is correct. It is wrong.
- The modified **python** code must be enclosed within triple backticks (```).
{std_input_prompt}
'''
