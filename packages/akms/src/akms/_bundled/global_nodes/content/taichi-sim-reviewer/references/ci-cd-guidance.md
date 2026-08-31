# CI/CD Guidance for Taichi Projects

Automated testing is crucial for maintaining code quality. This guide outlines how to set up CI/CD pipelines, focusing on GitHub Actions.

## 1. Goal of CI/CD
*   **Run Unit Tests**: Execute all Tier A and Tier B tests on every push.
*   **Run Integration Tests**: Execute Tier C tests on every PR or nightly.
*   **Linting**: Enforce code style (black, flake8, isort).
*   **Type Checking**: Optional but recommended (mypy).

## 2. Recommended GitHub Actions Workflow

Create a file `.github/workflows/test.yml`:

```yaml
name: Taichi Simulation Tests

on:
  push:
    branches: [ "main" ]
  pull_request:
    branches: [ "main" ]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12", "3.13"]

    steps:
    - uses: actions/checkout@v4

    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v5
      with:
        python-version: ${{ matrix.python-version }}

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install pytest taichi sympy

    - name: Run Tests
      run: |
        pytest tests/
```

## 3. Handling GPU Tests in CI
*   **GitHub Hosted Runners**: Standard runners only have CPUs. Taichi will run on CPU backend.
*   **Self-Hosted Runners**: If you need to test CUDA/Vulkan backends, you need self-hosted runners with GPUs.
*   **Mocking/Fallback**: Ensure your tests can gracefully degrade to CPU or skip if no GPU is found (unless GPU is strictly required).

```python
import taichi as ti
import pytest

@pytest.mark.skipif(not ti.has_gpu(), reason="No GPU detected")
def test_gpu_kernel():
    ti.init(arch=ti.gpu)
    ...
```

## 4. Pre-commit Hooks
Encourage developers to use pre-commit hooks to catch issues locally.
Create `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 24.8.0
    hooks:
      - id: black
  - repo: https://github.com/PyCQA/flake8
    rev: 7.0.0
    hooks:
      - id: flake8
```

## 5. Reviewing CI Configurations
When reviewing CI changes:
*   Ensure that tests are not skipped silently.
*   Check that the correct python versions are tested.
*   Verify that dependencies are pinned or reasonably constrained.
