TEST_SYSTEM = '''
You are a software test engineer tasked with generating **3-5** edge test cases for a given problem. See the refined requirement for the problem and ensure the generated test cases should cover it.
'''


GEN_TOOL_INPUT = '''
You have access to the tool:
- python_interpreter: This is a tool that run python code and returns its stdout and stderr. It can be used to perform calculations.

--------
- Use the python_interpreter whenever calculation or quick verification is needed while generating test cases.
'''

TEST_INPUT = '''
## Problem
{prompt}

## Refined Requirement
{requirement}

-------
**Important Instructions:**
- You must output **only** valid JSON, nothing else — no explanations, no markdown formatting.
- The generated test cases **must strictly follow** the data types, value ranges, and constraints described in **## Problem**.
- Your response must strictly follow the structure and style of test cases as below:
{sample_io}
'''


TEST_REFINEMENT_SYSTEM = '''
You are a meticulous software test engineer. Your task is verify the correctness of some test cases for a given problem using logical simulation based on the provided **plan**. For any incorrect test case, you must remove it entirely from the final output.
'''



REFINE_TOOL_INPUT = '''
You have access to the tool:
- python_interpreter: This is a tool that run python code and returns its stdout and stderr. It can be used to perform calculations.

--------
- Use the python_interpreter whenever calculation or quick verification is needed while verifying test cases.
'''


TEST_REFINEMENT_INPUT = '''
## Problem
{prompt}

## Plan
{design}

## Test Cases
{test_cases}

**Expected Output:**

Your response must be structured as follows:

### Case Verification
For each test case:
- Verify that the test case input strictly follows the data specification described in ## Problem (types, ranges, constraints).
- Take a input and apply plan step by step to get the output. Do not generate code do it manually by applying reasoning.
- Compare the generated output with the case output to verify if it is correct or not.
- If the case is incorrect, state clearly that the case is invalid.

### Correct Test Cases
- Output the complete list of **only the valid test cases** (invalid ones must be removed).
- Package the remaining test cases inside a triple backtick (```) code block.
- The final test cases must be valid JSON and strictly follow the structure and style of test cases as shown below:
{sample_io}
'''



PBT_SYSTEM='''
You are an expert quality assurance engineer and Python programmer specializing in Property-Based Testing (PBT). Your task is to write robust property-based tests for a given Python code using the `hypothesis` library.
Unlike traditional example-based testing where you assert specific outputs for specific inputs, Property-Based Testing focuses on asserting "properties" or "invariants" (truths that must always hold for any valid input) rather than calculating exact expected outputs.
## hypothesis Usage
Here is how you should use the `hypothesis` library:
1. Import the necessary decorators and data generation strategies:
```python
from hypothesis import given, strategies as st
```
2. Basic usage: Use the @given decorator to feed generated data into your test functions.
```python
# Example 1: Testing Idempotence (doing it twice is the same as doing it once)
@given(st.lists(st.integers()))
def test_sort_idempotence(lst):
    sorted_lst = sorted(lst)
    assert sorted(sorted_lst) == sorted_lst

# Example 2: Testing Round-trip (action + reverse action = original state)
@given(st.text())
def test_encode_decode(s):
    assert decode(encode(s)) == s

# Example 3: Testing Invariants (e.g., output size, range, or mathematical properties)
@given(st.integers(), st.integers())
def test_addition_commutativity(x, y):
    assert add(x, y) == add(y, x)
```
3. You can use various strategies to generate data: st.integers(), st.floats(), st.text(), st.lists(), st.dictionaries(), st.booleans(), etc.

'''

PBT_INPUT = '''
## Problem
{prompt}

## Refined Requirements
{requirement}

## Public-Test-Verified Code
```python
{code}
```

--------
**Important Instructions:**
- Treat the refined requirements as the semantic source of truth for valid inputs, outputs, constraints, and invariants.
- Inspect the public-test-verified code to identify its callable interface and properties that can expose remaining edge-case defects.
- Write robust property-based tests using @given and appropriate strategies from hypothesis.strategies.
- Do not calculate exact expected outputs for specific inputs. Focus entirely on invariants, boundary limits, or relative relationships (e.g., output size vs input size, boolean toggles, idempotence).
- Make sure to include all necessary imports (from hypothesis import given, strategies as st).
- Assume the target function to test is in the same file/namespace (you can directly call the functions/classes defined in the Code to Test). You do not need to import the target function or implement it.
- Do not redefine or replace any function or class from the public-test-verified code.
- Name your test functions starting with `test_`.
- The generated **python** code must be inside a triple backtick (```) code block.
'''
