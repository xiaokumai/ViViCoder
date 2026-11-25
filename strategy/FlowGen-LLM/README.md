# FlowGen-LLM

## Results Folder

* results: experiment data for three RQs
    * RQ1: five full runs on Humaneval/Humaneval-ET/MBPP/MBPP-ET
    * RQ2: remove development activities experiments
    * RQ3: different model versions and different temperature
    * RQ4: the comparison between FlowGen and other state-of-the-art code generation techniques
    * file_postfix description:
        * _logs: log files (including the prompts/responses)
        * _evaluate.json: the evaluation result for each generated code
        * _pylint.json: the pylint report for each generated code
        * _results.jsonl: the generated
* the results folder are organized by RQs and the corresponding datasets and models 

**PS: Due to some limitations, the website can't show full content of the results, please download check the details**  

## Static Folder

* static: images and other resources
    * approach-Example: the example of the approach diagram
    * prompts_templates.md: the prompts templates for each model
    
### Approach-Example

Here is the example about FlowGen_Scrum:

![Example](./static/approach-Example.drawio.png)

### Prompts Templates

Here we list the prompts templates for each model, the exact prompts that sent to LLM are in the `logs` file.

[Prompts Templates](./static/prompts_templates.md)

## Code Folder

* code: the code for the FlowGen-LLM
    * Templates: the prompt templates file for each activity
    * utils: the implement code of each activity
    * workflow: configure call-chain of these activities
    * workspace: the logs files while running
    * conf.json: openai_key configuration
    * requirements.txt: the requirements for the FlowGen-LLM
    * main.py: the main entry of the FlowGen-LLM

Here is the overview of the framework:

![Framework](./static/code_overview.png)

### How to run the code

#### local env

* setup: 
    * install the requirements
    * configure the openai_key in the conf.json
* run:
    * cd ./code && python main.py

#### docker

image: `docker pull watch0/flowgen:latest`

```shell
cd /home/ubuntu/code
source myenv/bin/activate
python main.py
```