STSTEM_PROMPT = '''
You are a coding assistant.
'''


ANALOGICAL_PROMPT = '''
Your goal is to write {lang} code to solve competitive programming problems. Given a problem, explain the core concepts in it and provide other relevant problems. Then solve the original problem.

# Problem:
{prompt}

# Instruction: (Your response must include the following points sequentially)

## Algorithms:
Identify the core concepts or algorithms used to solve the problem.

## Tutorial:
Write a useful tutorial about these algorithms.

## Example Problems: 
Provide three examples of relevant competitive programming problems that involve these algorithms. For each problem, describe the problem, explain the solution in detail, and then write correct {lang} code.

## {lang} code to solve the original problem: 
Include the following points in your response: 
- Explanation of the solution: 
- {lang} code to solve the problem (inside a ```{fence}``` block):
'''
