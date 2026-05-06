from setuptools import setup, find_packages
from pathlib import Path

readme = Path(__file__).parent / "README.md"
long_desc = readme.read_text() if readme.exists() else ""

setup(
    name="shortsmith",
    version="0.1.0",
    description="Open-source pipeline for stitching viral shorts and auto-posting to YouTube",
    long_description=long_desc,
    long_description_content_type="text/markdown",
    author="Melvin Morina",
    license="MIT",
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "shortsmith": ["templates/*.html", "static/*"],
    },
    install_requires=[
        "Pillow>=10.0",
        "PyYAML>=6.0",
        "google-api-python-client>=2.100",
        "google-auth-oauthlib>=1.0",
        "google-auth-httplib2>=0.1",
        "Flask>=3.0",
    ],
    entry_points={
        "console_scripts": [
            "shortsmith=shortsmith.cli:main",
        ],
    },
    python_requires=">=3.10",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Multimedia :: Video",
    ],
)
