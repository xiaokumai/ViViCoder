PYTHON_BUG_PROMPT = '''
You are a programmer who has received a Python solution that fails certain test cases.
Insert `ic()` debug statements from the `icecream` library at a small number of key
control-flow and state-transition points. `ic()` may be used either as a statement or
inside an expression. Do not change the algorithm or observable standard output.
'''


CPP_BUG_PROMPT = '''
You are a skilled C++ programmer who has received a solution that fails certain test
cases. Insert a small number of self-contained `std::cerr` debug statements at key
control-flow and state-transition points. Label every printed value. For containers,
print only relevant elements, indices, sizes, or a short explicit loop; do not assume a
non-standard stream operator. Do not change the algorithm and do not print debugging
information to `std::cout`.
'''


JAVA_BUG_PROMPT = '''
You are a skilled Java programmer who has received a solution that fails certain test
cases. Insert a small number of self-contained `System.err.println(...)` debug statements
at key control-flow and state-transition points. Label every printed value. Use standard
Java formatting such as `Arrays.toString` when needed. Do not change the algorithm and
do not print debugging information to `System.out`.
'''


BUG_INPUT = '''
## Problem
{prompt}

## Buggy Code
```{fence}
{code}
```

## Failing Test Cases
{test_log}

--------
**Important Instructions:**
- Do not refactor the code, change the algorithm, or modify required signatures/entry points.
- Add debug statements only at the few points most relevant to the failures.
- Keep the result valid, self-contained, and compilable/runnable as {lang}.
- Preserve judged standard output: C++ and Java traces must go to standard error.
- Return the complete instrumented code in a triple-backtick block tagged `{fence}`.
'''
