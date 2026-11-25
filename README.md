## 📋 Prerequisites

Before starting, ensure you have the following requirements met:

- **Python 3.11**: This project is strictly designed for Python 3.11.
- **SandboxFusion**: You must install [Sandbox Fusion](https://bytedance.github.io/SandboxFusion/) and ensure the service is running and exposed on **port 8081**.

## 🛠️ Installation

1.  **Clone the repository** (if applicable) and navigate to the project directory.

2.  **Install Dependencies**
    Install the required Python packages using pip:

    ```bash
    pip install -r requirements.txt
    ```

## ⚙️ Configuration

### 1. Project Configuration (`config.yaml`)

Open the `config.yaml` file to set the runtime parameters according to your needs.

For the CodeContests benchmark, select the dataset alias matching the target language:

```yaml
dataset:
  name: "contests_cpp"  # contests_python, contests_cpp, or contests_java
language: "cpp"         # python, cpp, or java
```

Use `contests_java` with `language: "java"` for Java. Java solutions are generated
with a `public class Main` entry point; C++ solutions contain `main` and all three
languages use standard input/output.

The multilingual strategy paths are `ViViCoder`, `vanilla`, `Analogical`, `CodeSIM`,
and `MapCoder`. Other bundled strategies remain Python-only and are rejected early
when a C++ or Java run is configured.

### 2. Environment Variables (`.env`)

The project relies on environment variables defined in a `.env` file. A template has been provided as `vivi.env`.

1.  **Rename the template**:

    - **Linux/macOS**:
      ```bash
      mv vivi.env .env
      ```
    - **Windows**:
      ```cmd
      ren vivi.env .env
      ```

2.  **Edit the file**: Open `.env` and fill in the necessary environment variables (e.g., API keys, database URLs).

## 🚀 Usage

Once SandboxFusion is running on port 8081 and your configuration is set, start the application:

```bash
python run.py
```
