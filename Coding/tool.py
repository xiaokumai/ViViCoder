from smolagents import Tool

class PythonInterpreterTool(Tool):
    name = "python_interpreter"
    description = "This is a tool that run python code and returns its stdout and stderr. It can be used to detecting syntax or runtime errors, excuting small demos, and inspect program output."
    inputs = {
        "code": {
            "type": "string",
            "description": "The python code to run in interpreter",
        }
    }
    output_type = "string"
    
    def forward(self, code: str) -> str:
        import requests
        import json

        url = "http://localhost:8081/run_code"
        
                
        data = {
            "code": code,
            "language": "python",
            "run_timeout": 20,
        }

        res = requests.post(url, json=data).json()
        
        return f"Stdout:\n{res['run_result']['stdout']}\nStderr:\n{res['run_result']['stderr']}"
    
    
from langchain.tools import tool

@tool
def python_interpreter(code: str) -> str:
    """This is a tool that run python code and returns its stdout and stderr. It can be used to detecting syntax or runtime errors, excuting small demos, and inspect program output."""
    interpreter = PythonInterpreterTool()
    return interpreter(code)