import setuptools

with open("README.md", "r", encoding="UTF-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="data_downloader",
    version="1.2",
    author="fanchegyan",
    author_email="fanchy14@lzu.edu.cn",
    description="Make downloading scientific data much easier",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Fanchengyan/data_downloader",
    packages=setuptools.find_packages(),
    install_requires=[
        "httpx >= 0.4.0",
        "requests",
        "tqdm",
        "setuptools",
        "beautifulsoup4",
        "nest_asyncio",
        "python-dateutil",
        "browser-cookie3",
        "hyp3_sdk",
        "pandas",
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
)
