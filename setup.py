from setuptools import find_packages, setup

setup(
    name="agent-output-contract",
    version="0.1.0",
    description="Validate coding-agent JSON outputs before automation trusts them as evidence.",
    packages=find_packages("src"),
    package_dir={"": "src"},
    python_requires=">=3.9",
    entry_points={
        "console_scripts": [
            "agent-output-contract=agent_output_contract.cli:main",
        ],
    },
)

