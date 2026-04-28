from setuptools import setup, find_packages

setup(
    name="graphify",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "networkx",
        "matplotlib",
        "tree-sitter>=0.21.0",
        "tree-sitter-python",
        "tree-sitter-javascript",
        "tree-sitter-typescript",
        "jinja2",
        "python-louvain",
    ],
)
